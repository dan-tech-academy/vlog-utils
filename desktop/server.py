"""Stdio JSON-lines sidecar. One job at a time; ping and cancel stay responsive."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
from datetime import date
from pathlib import Path

from desktop.agents import agent_env, build_argv, parse_session_id
from desktop.deps import binary_for, check_deps
from desktop.edl_validate import load_word_entries, probe_duration, validate_edl
from desktop.media import list_videos, transcript_file
from desktop.scan import repo_changes, repo_snapshot, snapshot, unexpected_writes
from desktop.turn_recover import (
    agent_failure_message,
    assistant_text,
    extract_edl,
    materialize_turn,
)
from desktop.session import (
    TurnError,
    agent_dir,
    apply_turn_side_effects,
    approve_strategy,
    build_prompt,
    clear_job,
    install_protocol,
    load_state,
    load_turn,
    mark_job,
    project_status,
    readiness,
    reset_project,
    save_state,
    write_answers,
    write_brief,
    write_thread,
)

REPO = Path(__file__).resolve().parents[1]
PROTOCOL = REPO / "desktop" / "AGENT_PROTOCOL.md"
HELPERS = REPO / "helpers"
TRACKED_JOBS = {"ingest", "agent_turn", "render"}


def repo_root() -> Path:
    return REPO


class Hub:
    def __init__(self, repo: Path, emit=None):
        self.repo = repo
        self._emit_fn = emit or (lambda _msg: None)
        self._write_lock = threading.Lock()
        self._proc_lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self.cancel_event = threading.Event()
        self.busy = False
        self.session_key = ""
        self.closing = False
        self.job_folder: Path | None = None

    def emit(self, msg: dict) -> None:
        with self._write_lock:
            self._emit_fn(msg)

    def _result(self, req_id, ok: bool, data=None, error: str | None = None) -> None:
        msg: dict = {"id": req_id, "type": "result", "ok": ok}
        if data is not None:
            msg["data"] = data
        if error:
            msg["error"] = error
        self.emit(msg)

    def _log(self, req_id, line: str) -> None:
        if len(line) > 500:
            line = line[:500] + "…"
        self.emit({"id": req_id, "type": "log", "data": {"line": line}})

    def _progress(self, req_id, phase: str, done: int, total: int) -> None:
        self.emit({
            "id": req_id,
            "type": "progress",
            "data": {"phase": phase, "done": done, "total": total},
        })

    def _kill(self) -> None:
        with self._proc_lock:
            proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except OSError:
                pass

    def request_cancel(self, msg: dict) -> None:
        with self._proc_lock:
            running = self.busy
        if not running:
            self._result(msg.get("id"), True, data={"idle": True})
            return
        self.cancel_event.set()
        self._kill()
        self._result(msg.get("id"), True, data={"cancelling": True})

    def try_start(self, msg: dict) -> bool:
        with self._proc_lock:
            if self.busy:
                return False
            self.busy = True
            self.cancel_event.clear()
        threading.Thread(target=self._run_job, args=(msg,), daemon=True).start()
        return True

    def _run_job(self, msg: dict) -> None:
        folder = None
        try:
            if msg.get("cmd") in TRACKED_JOBS:
                folder = self._folder(msg.get("folder"))
                self.job_folder = folder
                mark_job(folder, str(msg["cmd"]), msg.get("mode"))
            self.dispatch(msg)
        except Exception as exc:
            self._result(msg.get("id"), False, error=str(exc))
        finally:
            # A job killed because the app quit keeps its marker so the next launch can report it.
            if folder is not None and not self.closing:
                clear_job(folder)
            self.job_folder = None
            with self._proc_lock:
                self.busy = False
            self.cancel_event.clear()

    def shutdown(self) -> None:
        self.closing = True
        self.cancel_event.set()
        self._kill()

    def status(self, msg: dict) -> None:
        folder = self._folder(msg.get("folder"))
        running = self.busy and self.job_folder == folder
        self._result(msg.get("id"), True, data=project_status(folder, running=running))

    def save_thread(self, msg: dict) -> None:
        path = write_thread(self._folder(msg.get("folder")), msg.get("thread"))
        self._result(msg.get("id"), True, data={"path": str(path)})

    def dispatch(self, msg: dict) -> None:
        cmd = msg.get("cmd")
        req_id = msg.get("id")
        if cmd == "check_deps":
            self._result(req_id, True, data=check_deps(include_login=bool(msg.get("include_login"))))
            return
        if cmd == "inventory":
            self._result(req_id, True, data={"videos": self.inventory(msg)})
            return
        if cmd == "save_brief":
            path = write_brief(self._folder(msg.get("folder")), str(msg.get("prompt") or ""))
            self._result(req_id, True, data={"path": str(path)})
            return
        if cmd == "ingest":
            self.ingest(msg)
            return
        if cmd == "save_answers":
            path = write_answers(self._folder(msg.get("folder")), msg.get("answers") or [])
            self._result(req_id, True, data={"path": str(path)})
            return
        if cmd == "approve_strategy":
            self.approve(msg)
            return
        if cmd == "agent_turn":
            self.agent_turn(msg)
            return
        if cmd == "dismiss_writes":
            self.dismiss_writes(msg)
            return
        if cmd == "validate_edl":
            self._result(req_id, True, data=self.validate(msg))
            return
        if cmd == "storyboard":
            self._result(req_id, True, data=self.storyboard(msg))
            return
        if cmd == "save_ranges":
            self.save_ranges(msg)
            return
        if cmd == "clips":
            self.clips(msg)
            return
        if cmd == "render":
            self.render(msg)
            return
        if cmd == "reset_project":
            archive = reset_project(self._folder(msg.get("folder")))
            self._result(req_id, True, data={"archive": str(archive) if archive else None})
            return
        self._result(req_id, False, error=f"lệnh không rõ: {cmd}")

    def _folder(self, value) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Thiếu folder")
        path = Path(value).expanduser().resolve()
        if not path.is_dir():
            raise ValueError(f"Không phải thư mục: {value}")
        return path

    def inventory(self, msg: dict) -> list[dict]:
        folder = self._folder(msg.get("folder"))
        edit = folder / "edit"
        rows = []
        for video in list_videos(folder):
            duration = probe_duration(video)
            poster = edit / "storyboard" / f"src_{video.stem}.jpg"
            if not poster.is_file():
                self._still(video, min(1.0, (duration or 0) / 2), poster)
            rows.append({
                "name": video.name,
                "path": str(video.resolve()),
                "size": video.stat().st_size,
                "cached": transcript_file(edit, video).is_file(),
                "duration": duration,
                "poster": str(poster) if poster.is_file() else None,
            })
        return rows

    def _ffmpeg(self, args: list[str], lines: list[str]) -> int:
        argv = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", *args]
        try:
            return self.spawn(argv, cwd=self.repo, env=os.environ.copy(), on_line=lines.append)
        except OSError as exc:
            lines.append(str(exc))
            return 127

    def _still(self, source: Path, at: float, dest: Path) -> bool:
        dest.parent.mkdir(parents=True, exist_ok=True)
        code = self._ffmpeg(
            ["-ss", f"{at:.3f}", "-i", str(source), "-frames:v", "1", "-vf", "scale=-2:540", str(dest)],
            [],
        )
        return code == 0 and dest.is_file()

    def spawn(self, argv: list[str], *, cwd: Path, env: dict, on_line) -> int:
        # stdin is the app's command pipe; ffmpeg and agent CLIs would read from it otherwise.
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        with self._proc_lock:
            self._proc = proc
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                if self.cancel_event.is_set():
                    self._kill()
                    break
                on_line(line.rstrip("\n"))
            return proc.wait()
        finally:
            with self._proc_lock:
                if self._proc is proc:
                    self._proc = None

    def remember_key(self, msg: dict) -> None:
        key = str(msg.get("api_key") or "").strip()
        if not key:
            self._result(msg.get("id"), False, error="Key trống.")
            return
        self.session_key = key
        self._result(msg.get("id"), True, data={"saved": True})

    def forget_key(self, msg: dict) -> None:
        self.session_key = ""
        self._result(msg.get("id"), True, data={"cleared": True})

    def transcribe_key(self, msg: dict) -> str:
        supplied = str(msg.get("api_key") or "").strip()
        return supplied or self.session_key

    def ingest(self, msg: dict) -> None:
        req_id = msg.get("id")
        folder = self._folder(msg.get("folder"))
        videos = list_videos(folder)
        if not videos:
            self._result(req_id, False, error="Không có footage trong folder.")
            return
        edit = folder / "edit"
        pending = [video for video in videos if not transcript_file(edit, video).is_file()]
        api_key = self.transcribe_key(msg)
        if pending and not api_key:
            self._result(
                req_id,
                False,
                error="Chưa có ElevenLabs API key. Mở Cài đặt, dán key rồi chạy lại.",
            )
            return

        stop = threading.Event()

        def poll() -> None:
            total = len(videos)
            while not stop.is_set():
                done = sum(1 for video in videos if transcript_file(edit, video).is_file())
                self._progress(req_id, "transcribe", done, total)
                stop.wait(0.4)

        poller = threading.Thread(target=poll, daemon=True)
        poller.start()
        lines: list[str] = []
        env = os.environ.copy()
        if api_key:
            env["ELEVENLABS_API_KEY"] = api_key
        try:
            code = self.spawn(
                [sys.executable, str(HELPERS / "transcribe_batch.py"), str(folder)],
                cwd=folder,
                env=env,
                on_line=lambda line: self._collect(req_id, lines, line),
            )
        finally:
            stop.set()
            poller.join(timeout=1)
        if self.cancel_event.is_set():
            self._result(req_id, False, error="đã hủy")
            return
        if code != 0:
            self._result(req_id, False, error=_tail(lines) or f"transcribe thoát {code}")
            return

        self._progress(req_id, "pack", 0, 1)
        code = self.spawn(
            [sys.executable, str(HELPERS / "pack_transcripts.py"), "--edit-dir", str(edit)],
            cwd=folder,
            env=agent_env(os.environ),
            on_line=lambda line: self._collect(req_id, lines, line),
        )
        if self.cancel_event.is_set():
            self._result(req_id, False, error="đã hủy")
            return
        if code != 0:
            self._result(req_id, False, error=_tail(lines) or f"pack thoát {code}")
            return
        self._progress(req_id, "pack", 1, 1)
        cached = len(videos) - len(pending)
        self._result(req_id, True, data={
            "videos": len(videos),
            "cached": cached,
            "transcribed": len(pending),
            "packed": str(edit / "takes_packed.md"),
        })

    def approve(self, msg: dict) -> None:
        folder = self._folder(msg.get("folder"))
        state = load_state(folder)
        approve_strategy(state)
        save_state(folder, state)
        self._result(msg.get("id"), True, data={"strategy_approved": True, "strategy": state["strategy"]})

    def agent_turn(self, msg: dict) -> None:
        req_id = msg.get("id")
        folder = self._folder(msg.get("folder"))
        provider = str(msg.get("provider") or "")
        note = str(msg.get("note") or "")
        brief = agent_dir(folder) / "brief.md"
        if not brief.is_file() or not brief.read_text(encoding="utf-8").strip():
            self._result(req_id, False, error="Chưa có prompt. Viết brief trước khi gọi agent.")
            return
        if not (folder / "edit" / "takes_packed.md").is_file():
            self._result(req_id, False, error="Chưa có takes_packed.md. Chạy transcribe trước.")
            return

        state = load_state(folder)
        if msg.get("reset_strategy"):
            state["strategy_approved"] = False
        state["ignore_writes"] = False
        state["provider"] = provider
        binary = binary_for(provider)
        install_protocol(folder, PROTOCOL)
        prompt = build_prompt(state, note)
        (agent_dir(folder) / "prompt.md").write_text(prompt, encoding="utf-8")
        turn_path = agent_dir(folder) / "turn.json"
        turn_path.unlink(missing_ok=True)
        before = snapshot(folder)
        repo_before = repo_snapshot(self.repo)
        session_holder = {"id": state.get("session_id")}
        lines: list[str] = []

        def on_line(line: str) -> None:
            found = parse_session_id(provider, line)
            if found:
                session_holder["id"] = found
            self._collect(req_id, lines, line)

        def once(session_id: str | None, text: str) -> int:
            argv = build_argv(
                provider,
                binary=binary,
                prompt=text,
                footage=folder,
                session_id=session_id,
            )
            self._log(req_id, f"$ {provider}")
            return self.spawn(argv, cwd=folder, env=agent_env(os.environ), on_line=on_line)

        self._progress(req_id, "agent", 0, 1)
        code = once(state.get("session_id") if isinstance(state.get("session_id"), str) else None, prompt)
        approved = bool(state.get("strategy_approved"))
        if not materialize_turn(turn_path, lines, strategy_approved=approved) and not self.cancel_event.is_set():
            self._log(req_id, "Agent chưa trả JSON, chạy lại một lần.")
            retry = (
                "Reply with only one JSON object and write it to edit/agent/turn.json. "
                'Use {"kind":"questions","questions":[{"id":"q","prompt":"..."}]} '
                'or {"kind":"strategy","strategy":"one paragraph"}. '
                "No other files."
            )
            code = once(None, retry)
            materialize_turn(turn_path, lines, strategy_approved=approved)
        if self.cancel_event.is_set():
            self._result(req_id, False, error="đã hủy")
            return
        if not turn_path.is_file():
            self._result(req_id, False, error=agent_failure_message(code, lines))
            return

        unexpected = unexpected_writes(before, snapshot(folder))
        unexpected += [f"repo:{path}" for path in repo_changes(repo_before, repo_snapshot(self.repo))]
        state["session_id"] = session_holder["id"]
        state["unexpected_writes"] = unexpected
        if turn_path.is_file():
            try:
                turn = load_turn(folder)
            except TurnError:
                turn = None
            if turn and turn["kind"] == "edl" and not state.get("strategy_approved"):
                text = assistant_text(lines).strip()
                if len(text) < 20 or '"kind"' in text[:200]:
                    text = "Agent muốn cắt ngay. Duyệt nếu hướng này ổn, hoặc bấm viết lại."
                turn = {"kind": "strategy", "strategy": text}
                turn_path.write_text(json.dumps(turn, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if turn and turn["kind"] == "edl" and state.get("strategy_approved"):
                edl_path = folder / "edit" / "edl.json"
                if not edl_path.is_file():
                    recovered = extract_edl(lines)
                    if recovered:
                        edl_path.write_text(json.dumps(recovered, indent=2) + "\n", encoding="utf-8")
            if turn:
                try:
                    apply_turn_side_effects(state, load_turn(folder))
                except TurnError:
                    pass
        save_state(folder, state)
        payload = readiness(folder, state, unexpected, ignore_writes=False)
        self._progress(req_id, "agent", 1, 1)
        if payload.get("ok"):
            self._result(req_id, True, data=payload)
        else:
            self._result(req_id, False, data=payload, error=payload.get("error") or f"agent thoát {code}")

    def dismiss_writes(self, msg: dict) -> None:
        folder = self._folder(msg.get("folder"))
        state = load_state(folder)
        state["ignore_writes"] = True
        save_state(folder, state)
        unexpected = list(state.get("unexpected_writes") or [])
        payload = readiness(folder, state, unexpected, ignore_writes=True)
        if payload.get("ok"):
            self._result(msg.get("id"), True, data=payload)
        else:
            self._result(msg.get("id"), False, data=payload, error=payload.get("error"))

    def validate(self, msg: dict) -> dict:
        folder = self._folder(msg.get("folder"))
        edl_path = folder / "edit" / "edl.json"
        if not edl_path.is_file():
            return {"ok": False, "errors": ["Chưa có edl.json"], "warnings": []}
        edl = json.loads(edl_path.read_text(encoding="utf-8"))
        return validate_edl(edl, folder / "edit").to_dict()

    def storyboard(self, msg: dict) -> dict:
        folder = self._folder(msg.get("folder"))
        edl_path = folder / "edit" / "edl.json"
        if not edl_path.is_file():
            raise ValueError("Chưa có edl.json")
        edl = json.loads(edl_path.read_text(encoding="utf-8"))
        edit = folder / "edit"
        validation = validate_edl(edl, edit)
        words: dict[str, list[dict]] = {}
        durations: dict[str, float] = {}
        sources = edl.get("sources") if isinstance(edl.get("sources"), dict) else {}
        for key, raw in sources.items():
            words[str(key)] = load_word_entries(edit, str(key))
            path = _source_path(edit, raw)
            if path.is_file():
                duration = probe_duration(path)
                if duration is not None:
                    durations[str(key)] = duration
        state = load_state(folder)
        return {
            "edl": edl,
            "validation": validation.to_dict(),
            "words": words,
            "durations": durations,
            "strategy": state.get("strategy") or "",
            "preview_ready": (edit / "preview.mp4").is_file(),
        }

    def save_ranges(self, msg: dict) -> None:
        req_id = msg.get("id")
        folder = self._folder(msg.get("folder"))
        edl_path = folder / "edit" / "edl.json"
        if not edl_path.is_file():
            self._result(req_id, False, error="Chưa có edl.json")
            return
        original = edl_path.read_text(encoding="utf-8")
        edl = json.loads(original)
        ranges = _clean_ranges(msg.get("ranges"))
        edl["ranges"] = ranges
        edl["total_duration_s"] = round(sum(item["end"] - item["start"] for item in ranges), 3)
        validation = validate_edl(edl, folder / "edit")
        if not validation.ok:
            self._result(req_id, False, data={"validation": validation.to_dict()}, error="\n".join(validation.errors))
            return
        edl_path.write_text(json.dumps(edl, indent=2), encoding="utf-8")
        self._result(req_id, True, data={"edl": edl, "validation": validation.to_dict()})

    def clips(self, msg: dict) -> None:
        """One small proxy per storyboard card. Unchanged ranges reuse their clip."""
        req_id = msg.get("id")
        folder = self._folder(msg.get("folder"))
        edit = folder / "edit"
        edl_path = edit / "edl.json"
        if not edl_path.is_file():
            self._result(req_id, False, error="Chưa có edl.json")
            return
        edl = json.loads(edl_path.read_text(encoding="utf-8"))
        out_dir = edit / "storyboard"
        out_dir.mkdir(parents=True, exist_ok=True)
        sources = edl.get("sources") if isinstance(edl.get("sources"), dict) else {}
        ranges = edl.get("ranges") if isinstance(edl.get("ranges"), list) else []
        keep: set[str] = set()
        items = []
        failures: list[str] = []
        for index, raw in enumerate(ranges):
            if self.cancel_event.is_set():
                self._result(req_id, False, error="đã hủy")
                return
            self._progress(req_id, "clips", index, len(ranges))
            raw = raw if isinstance(raw, dict) else {}
            start = float(raw.get("start") or 0)
            end = float(raw.get("end") or 0)
            item = {"index": index, "source": raw.get("source"), "start": start, "end": end, "clip": None, "poster": None}
            raw_source = sources.get(raw.get("source"))
            if raw_source:
                source = _source_path(edit, raw_source)
                stem = f"clip_{_clip_hash(source, start, end)}"
                clip = out_dir / f"{stem}.mp4"
                poster = out_dir / f"{stem}.jpg"
                keep.update({clip.name, poster.name})
                if not poster.is_file():
                    self._still(source, start, poster)
                if not clip.is_file() and end > start:
                    lines: list[str] = []
                    part = out_dir / f"{stem}.part.mp4"
                    code = self._ffmpeg([
                        "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(source),
                        "-map", "0:v:0", "-map", "0:a:0?", "-vf", "scale=-2:540",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(part),
                    ], lines)
                    if code == 0 and part.is_file():
                        part.replace(clip)
                    else:
                        part.unlink(missing_ok=True)
                        failures.append(f"cảnh {index + 1}: {_tail(lines) or f'ffmpeg thoát {code}'}")
                item["clip"] = str(clip) if clip.is_file() else None
                item["poster"] = str(poster) if poster.is_file() else None
            items.append(item)
            self.emit({"id": req_id, "type": "clip", "data": item})
        for stale in out_dir.glob("clip_*"):
            if stale.name not in keep:
                stale.unlink(missing_ok=True)
        self._progress(req_id, "clips", len(ranges), len(ranges))
        self._result(req_id, True, data={"clips": items, "failures": failures})

    def render(self, msg: dict) -> None:
        req_id = msg.get("id")
        folder = self._folder(msg.get("folder"))
        mode = msg.get("mode")
        if mode not in {"preview", "final"}:
            self._result(req_id, False, error="mode phải là preview hoặc final")
            return
        edit = folder / "edit"
        edl_path = edit / "edl.json"
        if not edl_path.is_file():
            self._result(req_id, False, error="Chưa có edl.json")
            return
        edl = json.loads(edl_path.read_text(encoding="utf-8"))
        validation = validate_edl(edl, edit)
        if not validation.ok:
            self._result(req_id, False, data={"validation": validation.to_dict()}, error="\n".join(validation.errors))
            return
        render_path = edit / "edl.render.json"
        render_path.write_text(json.dumps(validation.render_edl, indent=2), encoding="utf-8")
        out = edit / ("preview.mp4" if mode == "preview" else "final.mp4")
        argv = [
            sys.executable,
            str(HELPERS / "render.py"),
            str(render_path),
            "-o", str(out),
            "--build-subtitles",
        ]
        if mode == "preview":
            argv.append("--preview")
        lines: list[str] = []
        self._progress(req_id, "render", 0, 1)
        code = self.spawn(
            argv,
            cwd=folder,
            env=agent_env(os.environ),
            on_line=lambda line: self._collect(req_id, lines, line),
        )
        if self.cancel_event.is_set():
            self._result(req_id, False, error="đã hủy")
            return
        if code != 0 or not out.is_file():
            self._result(req_id, False, error=_tail(lines) or f"render thoát {code}")
            return
        if mode == "final":
            state = load_state(folder)
            _append_project(edit, str(state.get("strategy") or ""), len(edl.get("ranges") or []))
        self._progress(req_id, "render", 1, 1)
        self._result(req_id, True, data={"output": str(out), "mode": mode, "warnings": validation.warnings})

    def _collect(self, req_id, lines: list[str], line: str) -> None:
        lines.append(line)
        if len(lines) > 200:
            del lines[:50]
        self._log(req_id, line)


def _tail(lines: list[str]) -> str:
    text = "\n".join(lines[-40:]).strip()
    return text


def _source_path(edit: Path, raw) -> Path:
    path = Path(str(raw))
    return path if path.is_absolute() else (edit / path).resolve()


def _clip_hash(source: Path, start: float, end: float) -> str:
    return hashlib.sha1(f"{source}|{start:.3f}|{end:.3f}".encode()).hexdigest()[:12]


def _clean_ranges(raw) -> list[dict]:
    if not isinstance(raw, list):
        raise ValueError("ranges phải là list")
    clean = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("range không hợp lệ")
        source = item.get("source")
        if not isinstance(source, str) or not source:
            raise ValueError("range thiếu source")
        start = float(item["start"])
        end = float(item["end"])
        row = {"source": source, "start": start, "end": end}
        for key in ("beat", "quote", "reason"):
            if isinstance(item.get(key), str):
                row[key] = item[key]
        clean.append(row)
    return clean


def _append_project(edit_dir: Path, strategy: str, range_count: int) -> None:
    path = edit_dir / "project.md"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    import re
    number = len(re.findall(r"(?m)^## Session ", existing)) + 1
    body = (
        f"## Session {number} — {date.today().isoformat()}\n\n"
        f"**Strategy:** {strategy or 'Approved from the desktop storyboard.'}\n"
        f"**Decisions:** {range_count} ranges rendered to final.mp4 from the storyboard.\n"
        "**Reasoning log:** User approved the storyboard in the desktop app.\n"
        "**Outstanding:** none\n"
    )
    if existing and not existing.endswith("\n"):
        existing += "\n"
    if existing:
        existing += "\n"
    path.write_text(existing + body, encoding="utf-8")


def serve(hub: Hub | None = None) -> None:
    hub = hub or Hub(repo_root())

    def emit(msg: dict) -> None:
        sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    hub._emit_fn = emit

    def stop(_signum, _frame):
        hub.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue
        cmd = msg.get("cmd")
        if cmd == "ping":
            hub._result(msg.get("id"), True, data={"pong": True})
            continue
        if cmd == "set_session_key":
            hub.remember_key(msg)
            continue
        if cmd == "clear_session_key":
            hub.forget_key(msg)
            continue
        if cmd == "cancel":
            hub.request_cancel(msg)
            continue
        if cmd in {"project_status", "save_thread"}:
            handler = hub.status if cmd == "project_status" else hub.save_thread
            try:
                handler(msg)
            except (OSError, ValueError) as exc:
                hub._result(msg.get("id"), False, error=str(exc))
            continue
        if not hub.try_start(msg):
            hub._result(msg.get("id"), False, error="busy")

    # stdin closes when the app exits, even on a crash or force quit. Children run in their
    # own session, so they would outlive us unless killed here.
    hub.shutdown()


if __name__ == "__main__":
    serve()
