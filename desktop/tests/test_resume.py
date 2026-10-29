import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from desktop.server import Hub
from desktop.session import (
    approve_strategy,
    default_state,
    load_state,
    mark_job,
    project_status,
    reset_project,
    save_state,
    write_brief,
    write_thread,
)

ROOT = Path(__file__).resolve().parents[2]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _write_turn(folder: Path, turn: dict) -> None:
    (folder / "edit" / "agent" / "turn.json").write_text(json.dumps(turn), encoding="utf-8")


def _project(tmp_path: Path, *, step: str) -> Path:
    """A footage folder left at `step`: brief, questions, strategy, or board."""
    clip = tmp_path / "C0103.MP4"
    clip.write_bytes(b"not a real movie")
    edit = tmp_path / "edit"
    (edit / "transcripts").mkdir(parents=True)
    (edit / "transcripts" / "C0103.json").write_text(
        json.dumps({"words": [{"type": "word", "text": "hi", "start": 1.0, "end": 1.4}]}),
        encoding="utf-8",
    )
    if step == "brief":
        return tmp_path
    write_brief(tmp_path, "Vlog chợ, khoảng một phút.")
    (edit / "takes_packed.md").write_text("[1.00-1.40] hi\n", encoding="utf-8")
    state = default_state()
    state["session_id"] = "ses_1"
    if step == "questions":
        _write_turn(tmp_path, {"kind": "questions", "questions": [{"id": "aspect", "prompt": "16:9?"}]})
    else:
        state["strategy"] = "Giữ câu chào."
        _write_turn(tmp_path, {"kind": "strategy", "strategy": state["strategy"]})
    if step == "board":
        approve_strategy(state)
        _write_turn(tmp_path, {"kind": "edl"})
        (edit / "edl.json").write_text(json.dumps({
            "version": 1,
            "sources": {"C0103": str(clip)},
            "ranges": [{"source": "C0103", "start": 0.95, "end": 1.48}],
            "total_duration_s": 0.53,
        }), encoding="utf-8")
    save_state(tmp_path, state)
    return tmp_path


def _touch_after(path: Path, reference: Path) -> None:
    later = reference.stat().st_mtime + 5
    os.utime(path, (later, later))


def test_status_reopens_at_the_step_the_user_left(tmp_path):
    statuses = {}
    for step in ("brief", "questions", "strategy", "board"):
        folder = tmp_path / step
        folder.mkdir()
        statuses[step] = project_status(_project(folder, step=step))
    assert {step: status["phase"] for step, status in statuses.items()} == {
        "brief": "brief",
        "questions": "questions",
        "strategy": "strategy",
        "board": "board",
    }, statuses["board"]["edl"]
    assert statuses["questions"]["turn"]["questions"][0]["id"] == "aspect"
    assert statuses["questions"]["transcripts"] == {"done": 1, "total": 1}
    assert statuses["board"]["edl"]["ranges"] == 1
    assert statuses["board"]["brief"] == "Vlog chợ, khoảng một phút."


def test_status_tracks_preview_and_final_freshness(tmp_path):
    folder = _project(tmp_path, step="board")
    edit = folder / "edit"
    preview = edit / "preview.mp4"
    preview.write_bytes(b"mp4")
    _touch_after(preview, edit / "edl.json")
    assert project_status(folder)["phase"] == "preview"

    _touch_after(edit / "edl.json", preview)
    status = project_status(folder)
    assert status["phase"] == "board"
    assert status["preview"] is None
    assert status["preview_stale"] is True

    final = edit / "final.mp4"
    final.write_bytes(b"mp4")
    _touch_after(final, edit / "edl.json")
    assert project_status(folder)["phase"] == "exported"


def test_interrupted_agent_reopens_on_the_last_good_storyboard(tmp_path):
    folder = _project(tmp_path, step="board")
    (folder / "edit" / "agent" / "turn.json").unlink()
    mark_job(folder, "agent_turn")
    status = project_status(folder)
    assert status["phase"] == "board"
    assert status["interrupted"]["cmd"] == "agent_turn"
    assert project_status(folder, running=True)["interrupted"] is None


def test_interrupted_render_does_not_count_as_a_preview(tmp_path):
    folder = _project(tmp_path, step="board")
    preview = folder / "edit" / "preview.mp4"
    preview.write_bytes(b"half written")
    _touch_after(preview, folder / "edit" / "edl.json")
    mark_job(folder, "render", "preview")
    status = project_status(folder)
    assert status["phase"] == "board"
    assert status["preview"] is None


def test_interrupted_first_cut_asks_to_rerun_the_agent(tmp_path):
    folder = _project(tmp_path, step="strategy")
    state = load_state(folder)
    approve_strategy(state)
    save_state(folder, state)
    (folder / "edit" / "agent" / "turn.json").unlink()
    assert project_status(folder)["phase"] == "agent"


def test_reset_archives_the_attempt_and_keeps_transcripts(tmp_path):
    folder = _project(tmp_path, step="board")
    write_thread(folder, [{"k": "user", "text": "Vlog chợ"}])
    (folder / "edit" / "final.mp4").write_bytes(b"mp4")
    archive = reset_project(folder)
    assert archive is not None and archive.parent == folder / "edit" / "archive"
    assert (archive / "edl.json").is_file()
    assert (archive / "final.mp4").is_file()
    assert (archive / "agent" / "state.json").is_file()
    assert (archive / "agent" / "thread.json").is_file()
    assert (folder / "edit" / "transcripts" / "C0103.json").is_file()
    assert (folder / "edit" / "takes_packed.md").is_file()
    assert not (folder / "edit" / "edl.json").exists()
    assert load_state(folder) == default_state()
    status = project_status(folder)
    assert status["phase"] == "brief"
    assert status["thread"] is None
    assert reset_project(folder) is None


def test_thread_round_trip(tmp_path):
    write_thread(tmp_path, {"items": [{"k": "batch", "items": [{"num": "03", "text": "Ngắn lại"}]}]})
    assert project_status(tmp_path)["thread"]["items"][0]["items"][0]["text"] == "Ngắn lại"
    try:
        write_thread(tmp_path, "not json")
    except ValueError:
        pass
    else:
        raise AssertionError("thread must be an object or a list")


def test_job_marker_survives_only_when_the_app_quits(tmp_path):
    events = []
    hub = Hub(ROOT, emit=events.append)
    marker = tmp_path / "edit" / "agent" / "job.json"

    hub._run_job({"id": "r1", "cmd": "render", "folder": str(tmp_path), "mode": "preview"})
    assert events[-1]["ok"] is False
    assert not marker.exists()

    hub.closing = True
    hub._run_job({"id": "r2", "cmd": "render", "folder": str(tmp_path), "mode": "preview"})
    assert json.loads(marker.read_text())["mode"] == "preview"


def test_closing_stdin_kills_running_job_and_status_stays_responsive(tmp_path):
    pid_file = tmp_path / "child.pid"
    script = (
        "from pathlib import Path\n"
        "from desktop import server\n"
        "def dispatch(self, msg):\n"
        f"    self.spawn(['/bin/sh', '-c', 'echo $$ > {pid_file}; exec /bin/sleep 30'],\n"
        "               cwd=Path('.'), env={}, on_line=lambda line: None)\n"
        "server.Hub.dispatch = dispatch\n"
        "server.serve()\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdin and proc.stdout
    child = None
    try:
        proc.stdin.write(json.dumps({"id": "1", "cmd": "slow"}) + "\n")
        proc.stdin.flush()
        deadline = time.time() + 5
        while not (pid_file.is_file() and pid_file.read_text().strip()):
            assert time.time() < deadline, "job never started"
            time.sleep(0.05)
        child = int(pid_file.read_text())

        proc.stdin.write(json.dumps({"id": "2", "cmd": "project_status", "folder": str(tmp_path)}) + "\n")
        proc.stdin.flush()
        reply = json.loads(proc.stdout.readline())
        assert reply["id"] == "2" and reply["ok"] is True
        assert reply["data"]["phase"] == "brief"

        proc.stdin.close()
        proc.wait(timeout=5)
        deadline = time.time() + 3
        while _alive(child) and time.time() < deadline:
            time.sleep(0.05)
        assert not _alive(child), "job outlived the sidecar after the app closed"
    finally:
        if proc.poll() is None:
            proc.kill()
        if child and _alive(child):
            os.kill(child, signal.SIGKILL)
