import json
import subprocess
import sys
from pathlib import Path

from desktop.scan import repo_changes, snapshot, unexpected_writes
from desktop.server import Hub
from desktop.session import (
    TurnError,
    apply_turn_side_effects,
    approve_strategy,
    default_state,
    load_turn,
    parse_turn,
    readiness,
    save_state,
    write_answers,
)


def test_questions_turn_and_strategy_gate(tmp_path):
    turn = parse_turn({
        "kind": "questions",
        "questions": [{"id": "aspect", "prompt": "16:9 hay 9:16?"}],
    })
    assert turn["questions"][0]["id"] == "aspect"
    (tmp_path / "edit" / "agent").mkdir(parents=True)
    (tmp_path / "edit" / "agent" / "turn.json").write_text(
        json.dumps({"kind": "edl"}),
        encoding="utf-8",
    )
    state = default_state()
    blocked = readiness(tmp_path, state, [])
    assert blocked["ok"] is False
    assert blocked["error"] == "strategy_required"
    assert blocked["storyboard_ready"] is False

    state["strategy"] = "Keep the second take."
    approve_strategy(state)
    assert state["strategy_approved"] is True
    try:
        approve_strategy(default_state())
    except TurnError:
        pass
    else:
        raise AssertionError("empty strategy should not approve")


def test_strategy_turn_clears_approval():
    state = default_state()
    state["strategy_approved"] = True
    apply_turn_side_effects(state, parse_turn({"kind": "strategy", "strategy": "Rewrite it shorter."}))
    assert state["strategy_approved"] is False
    assert state["strategy"] == "Rewrite it shorter."


def test_unexpected_writes_ignore_edit_dir(tmp_path):
    before = snapshot(tmp_path)
    (tmp_path / "edit").mkdir()
    (tmp_path / "edit" / "edl.json").write_text("{}", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("touched", encoding="utf-8")
    bad = unexpected_writes(before, snapshot(tmp_path))
    assert bad == ["notes.txt"]


def test_repo_change_detects_helper_edit(tmp_path):
    helper = tmp_path / "helpers"
    helper.mkdir()
    target = helper / "render.py"
    target.write_text("a = 1\n", encoding="utf-8")
    before = {"helpers": target.stat().st_mtime_ns}
    # repo_snapshot uses real layout; the diff helper is what the server stores.
    after = dict(before)
    target.write_text("a = 2\n", encoding="utf-8")
    after[str(target)] = target.stat().st_mtime_ns
    assert repo_changes(before, after)


def test_answers_round_trip(tmp_path):
    path = write_answers(tmp_path, [{"id": "pace", "prompt": "Nhip?", "answer": "nhanh"}])
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved[0]["answer"] == "nhanh"


def test_cached_ingest_does_not_leak_key(tmp_path):
    clip = tmp_path / "C0103.MP4"
    clip.write_bytes(b"fake")
    transcripts = tmp_path / "edit" / "transcripts"
    transcripts.mkdir(parents=True)
    (transcripts / "C0103.json").write_text(
        json.dumps({"words": [{"type": "word", "text": "Hello", "start": 1.0, "end": 1.4}]}),
        encoding="utf-8",
    )
    secret = "super-secret-eleven-key"
    events = []
    hub = Hub(Path(__file__).resolve().parents[2], emit=events.append)
    hub.ingest({"id": "ingest", "folder": str(tmp_path), "api_key": secret})
    blob = json.dumps(events)
    assert secret not in blob
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert secret not in path.read_text(encoding="utf-8", errors="ignore")
    assert (tmp_path / "edit" / "takes_packed.md").is_file()
    result = events[-1]
    assert result["ok"] is True
    assert result["data"]["cached"] == 1
    assert result["data"]["transcribed"] == 0


def test_ping_stdio():
    proc = subprocess.Popen(
        [sys.executable, "-m", "desktop.server"],
        cwd=Path(__file__).resolve().parents[2],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdin and proc.stdout
    proc.stdin.write(json.dumps({"id": "1", "cmd": "ping"}) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    proc.kill()
    msg = json.loads(line)
    assert msg["ok"] is True
    assert msg["data"]["pong"] is True


def test_session_key_is_used_and_not_echoed():
    from desktop.server import Hub

    events = []
    hub = Hub(Path(__file__).resolve().parents[2], emit=events.append)
    secret = "eleven-test-secret-value"
    hub.remember_key({"id": "k", "api_key": secret})
    assert hub.transcribe_key({}) == secret
    assert secret not in json.dumps(events)
    hub.forget_key({"id": "c"})
    assert hub.transcribe_key({}) == ""


def test_load_turn_questions_fixture(tmp_path):
    (tmp_path / "edit" / "agent").mkdir(parents=True)
    (tmp_path / "edit" / "agent" / "turn.json").write_text(
        json.dumps({"kind": "questions", "questions": [{"id": "q1", "prompt": "Giữ câu nào?"}]}),
        encoding="utf-8",
    )
    turn = load_turn(tmp_path)
    state = default_state()
    save_state(tmp_path, state)
    payload = readiness(tmp_path, state, [])
    assert payload["turn"]["kind"] == "questions"
    assert payload["storyboard_ready"] is False
    assert turn["questions"][0]["prompt"] == "Giữ câu nào?"
