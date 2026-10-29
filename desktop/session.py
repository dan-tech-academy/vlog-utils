"""Prompt, turn.json, and the strategy gate. The app owns state.json."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from desktop.edl_validate import validate_edl
from desktop.media import list_videos, transcript_file


class TurnError(ValueError):
    pass


def agent_dir(folder: Path) -> Path:
    return folder / "edit" / "agent"


def default_state() -> dict:
    return {
        "strategy_approved": False,
        "strategy": "",
        "session_id": None,
        "provider": None,
        "ignore_writes": False,
        "unexpected_writes": [],
    }


def load_state(folder: Path) -> dict:
    path = agent_dir(folder) / "state.json"
    state = default_state()
    if not path.is_file():
        return state
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return state
    if isinstance(data, dict):
        state.update({key: data.get(key, state[key]) for key in state})
    return state


def save_state(folder: Path, state: dict) -> None:
    path = agent_dir(folder) / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def write_brief(folder: Path, prompt: str) -> Path:
    path = agent_dir(folder) / "brief.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prompt.strip() + "\n", encoding="utf-8")
    return path


def write_answers(folder: Path, answers: list[dict]) -> Path:
    path = agent_dir(folder) / "answers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = []
    for item in answers:
        if not isinstance(item, dict):
            continue
        qid = str(item.get("id") or "").strip()
        text = str(item.get("answer") or item.get("text") or "").strip()
        prompt = str(item.get("prompt") or "").strip()
        if qid:
            clean.append({"id": qid, "prompt": prompt, "answer": text})
    path.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_thread(folder: Path, thread) -> Path:
    if not isinstance(thread, (dict, list)):
        raise ValueError("thread phải là object hoặc list")
    path = agent_dir(folder) / "thread.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Saved often and the app can quit mid-write; never leave a truncated file behind.
    tmp = path.with_name("thread.json.tmp")
    tmp.write_text(json.dumps(thread, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


def mark_job(folder: Path, cmd: str, mode: str | None = None) -> None:
    path = agent_dir(folder) / "job.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cmd": cmd, "mode": mode, "started_at": time.time()}), encoding="utf-8")


def clear_job(folder: Path) -> None:
    (agent_dir(folder) / "job.json").unlink(missing_ok=True)


ARCHIVED = (
    "agent/state.json",
    "agent/turn.json",
    "agent/answers.json",
    "agent/brief.md",
    "agent/prompt.md",
    "agent/thread.json",
    "agent/job.json",
    "edl.json",
    "edl.render.json",
    "preview.mp4",
    "final.mp4",
    "storyboard",
)


def reset_project(folder: Path) -> Path | None:
    """Move the previous attempt into edit/archive/<stamp>/. Transcripts stay put."""
    edit = folder / "edit"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = edit / "archive" / stamp
    suffix = 1
    while dest.exists():
        suffix += 1
        dest = edit / "archive" / f"{stamp}-{suffix}"
    moved = False
    for rel in ARCHIVED:
        src = edit / rel
        if not src.exists():
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        src.replace(target)
        moved = True
    return dest if moved else None


def _fresh(output: Path, edl_path: Path) -> bool:
    if not output.is_file():
        return False
    return not edl_path.is_file() or output.stat().st_mtime >= edl_path.stat().st_mtime


def _phase(*, brief: str, packed: bool, state: dict, turn: dict | None, edl_ok: bool,
           preview: bool, final: bool) -> str:
    if not brief:
        return "brief"
    if not packed:
        return "analyze"
    if state.get("unexpected_writes") and not state.get("ignore_writes"):
        return "blocked"
    kind = turn["kind"] if turn else None
    if kind == "questions":
        return "questions"
    if state.get("strategy_approved") and kind in {"edl", None}:
        if not edl_ok:
            return "agent"
        if final:
            return "exported"
        return "preview" if preview else "board"
    if kind == "strategy" or state.get("strategy"):
        return "strategy"
    return "agent"


def project_status(folder: Path, *, running: bool = False) -> dict:
    """Everything the app needs to reopen a folder at the step the user left it."""
    edit = folder / "edit"
    agent = agent_dir(folder)
    brief_path = agent / "brief.md"
    brief = brief_path.read_text(encoding="utf-8").strip() if brief_path.is_file() else ""
    state = load_state(folder)
    try:
        turn = load_turn(folder)
    except TurnError:
        turn = None
    job = None if running else _read_json(agent / "job.json")
    interrupted = job if isinstance(job, dict) else None

    edl_path = edit / "edl.json"
    edl_info = None
    if edl_path.is_file():
        edl = _read_json(edl_path)
        if isinstance(edl, dict):
            validation = validate_edl(edl, edit, probe=False)
            ranges = edl.get("ranges") if isinstance(edl.get("ranges"), list) else []
            edl_info = {
                "ok": validation.ok,
                "ranges": len(ranges),
                "total_duration_s": edl.get("total_duration_s"),
                "errors": validation.errors,
                "updated_at": edl_path.stat().st_mtime,
            }
        else:
            edl_info = {"ok": False, "ranges": 0, "errors": ["edl.json không đọc được"],
                        "updated_at": edl_path.stat().st_mtime}

    outputs = {}
    for mode in ("preview", "final"):
        path = edit / f"{mode}.mp4"
        cut_short = interrupted is not None and interrupted.get("cmd") == "render" and interrupted.get("mode") == mode
        outputs[mode] = str(path) if _fresh(path, edl_path) and not cut_short else None

    videos = list_videos(folder)
    answers = _read_json(agent / "answers.json")
    blocked = bool(state.get("unexpected_writes")) and not state.get("ignore_writes")
    return {
        "phase": _phase(
            brief=brief,
            packed=(edit / "takes_packed.md").is_file(),
            state=state,
            turn=turn,
            edl_ok=bool(edl_info and edl_info["ok"]),
            preview=outputs["preview"] is not None,
            final=outputs["final"] is not None,
        ),
        "brief": brief,
        "answers": answers if isinstance(answers, list) else [],
        "turn": turn,
        "strategy": state.get("strategy") or "",
        "strategy_approved": bool(state.get("strategy_approved")),
        "unexpected_writes": list(state.get("unexpected_writes") or []) if blocked else [],
        "edl": edl_info,
        "preview": outputs["preview"],
        "preview_stale": outputs["preview"] is None and (edit / "preview.mp4").is_file(),
        "final": outputs["final"],
        "thread": _read_json(agent / "thread.json"),
        "interrupted": interrupted,
        "transcripts": {
            "done": sum(1 for video in videos if transcript_file(edit, video).is_file()),
            "total": len(videos),
        },
    }


def install_protocol(folder: Path, source: Path) -> None:
    dest = agent_dir(folder) / "protocol.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def build_prompt(state: dict, note: str) -> str:
    approved = "true" if state.get("strategy_approved") else "false"
    extra = note.strip() or "(none)"
    return (
        "Edit the footage in the working directory.\n"
        "Read edit/agent/protocol.md, edit/agent/brief.md, edit/takes_packed.md, "
        "and edit/agent/answers.json if that file exists.\n"
        f"strategy_approved: {approved}\n"
        "If strategy_approved is false, do not write edl.json. "
        "Your reply must be one JSON object: "
        '{"kind":"questions","questions":[{"id":"...","prompt":"..."}]} '
        "or "
        '{"kind":"strategy","strategy":"one paragraph"}. '
        "Also write that same object to edit/agent/turn.json.\n"
        "If strategy_approved is true, write edit/edl.json and reply "
        '{"kind":"edl"}.\n'
        "Do not run render.py. Do not transcribe. Do not write outside edit/.\n"
        f"User note: {extra}\n"
    )


def parse_turn(data: dict) -> dict:
    kind = data.get("kind")
    if kind == "questions":
        raw = data.get("questions")
        if not isinstance(raw, list) or not raw:
            raise TurnError("turn.json questions trống")
        questions = []
        for item in raw:
            if not isinstance(item, dict):
                raise TurnError("câu hỏi không hợp lệ")
            qid = item.get("id")
            prompt = item.get("prompt")
            if not isinstance(qid, str) or not qid.strip():
                raise TurnError("câu hỏi thiếu id")
            if not isinstance(prompt, str) or not prompt.strip():
                raise TurnError("câu hỏi thiếu prompt")
            questions.append({"id": qid.strip(), "prompt": prompt.strip()})
        return {"kind": "questions", "questions": questions}
    if kind == "strategy":
        text = data.get("strategy")
        if not isinstance(text, str) or not text.strip():
            raise TurnError("strategy trống")
        return {"kind": "strategy", "strategy": text.strip()}
    if kind == "edl":
        return {"kind": "edl"}
    raise TurnError("turn.json kind không hợp lệ")


def load_turn(folder: Path) -> dict:
    path = agent_dir(folder) / "turn.json"
    if not path.is_file():
        raise TurnError("Agent không trả về câu hỏi hay chiến lược.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TurnError("turn.json không phải JSON") from exc
    if not isinstance(data, dict):
        raise TurnError("turn.json không phải object")
    return parse_turn(data)


def apply_turn_side_effects(state: dict, turn: dict) -> None:
    if turn["kind"] == "strategy":
        state["strategy_approved"] = False
        state["strategy"] = turn["strategy"]


def approve_strategy(state: dict) -> None:
    if not str(state.get("strategy") or "").strip():
        raise TurnError("Chưa có chiến lược để duyệt")
    state["strategy_approved"] = True


def readiness(
    folder: Path,
    state: dict,
    unexpected: list[str],
    *,
    ignore_writes: bool = False,
) -> dict:
    try:
        turn = load_turn(folder)
    except TurnError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "storyboard_ready": False,
            "unexpected_writes": unexpected,
            "blocked": bool(unexpected),
        }

    if turn["kind"] == "edl" and not state.get("strategy_approved"):
        return {
            "ok": False,
            "error": "strategy_required",
            "turn": turn,
            "storyboard_ready": False,
            "unexpected_writes": unexpected,
            "blocked": bool(unexpected),
        }

    validation = None
    if turn["kind"] == "edl":
        edl_path = folder / "edit" / "edl.json"
        if not edl_path.is_file():
            return {
                "ok": False,
                "error": "Agent không ghi được các đoạn cắt.",
                "turn": turn,
                "storyboard_ready": False,
                "unexpected_writes": unexpected,
                "blocked": bool(unexpected),
            }
        try:
            edl = json.loads(edl_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "ok": False,
                "error": "edl.json không đọc được",
                "turn": turn,
                "storyboard_ready": False,
                "unexpected_writes": unexpected,
                "blocked": bool(unexpected),
            }
        validation = validate_edl(edl, folder / "edit")

    blocked = bool(unexpected) and not ignore_writes
    valid = validation.ok if validation is not None else False
    ready = turn["kind"] == "edl" and bool(state.get("strategy_approved")) and valid and not blocked
    payload = {
        "ok": True,
        "turn": turn,
        "storyboard_ready": ready,
        "unexpected_writes": unexpected,
        "blocked": blocked,
        "strategy_approved": bool(state.get("strategy_approved")),
        "strategy": state.get("strategy") or "",
    }
    if validation is not None:
        payload["validation"] = validation.to_dict()
        if not validation.ok:
            payload["ok"] = False
            payload["error"] = "\n".join(validation.errors)
    return payload
