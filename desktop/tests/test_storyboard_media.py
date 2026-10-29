import json
import subprocess
from pathlib import Path

import pytest

from desktop.server import Hub

ROOT = Path(__file__).resolve().parents[2]


def _ffmpeg_works() -> bool:
    try:
        return subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode == 0
    except OSError:
        return False


needs_ffmpeg = pytest.mark.skipif(not _ffmpeg_works(), reason="ffmpeg không chạy được trên máy này")


def _words():
    return [
        {"type": "word", "text": "Xin", "start": 0.5, "end": 0.8},
        {"type": "spacing", "text": " ", "start": 0.8, "end": 0.9},
        {"type": "word", "text": "chào", "start": 0.9, "end": 1.3},
        {"type": "word", "text": "Đà", "start": 2.0, "end": 2.2},
        {"type": "word", "text": "Lạt", "start": 2.25, "end": 2.6},
    ]


def _folder(tmp_path: Path, *, video: bool) -> Path:
    clip = tmp_path / "C0101.MP4"
    if video:
        subprocess.run([
            "ffmpeg", "-nostdin", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=3",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(clip),
        ], check=True)
    else:
        clip.write_bytes(b"not a real movie")
    edit = tmp_path / "edit"
    (edit / "transcripts").mkdir(parents=True)
    (edit / "transcripts" / "C0101.json").write_text(json.dumps({"words": _words()}), encoding="utf-8")
    _write_edl(tmp_path, [(0.45, 1.38), (1.95, 2.68)])
    return tmp_path


def _write_edl(folder: Path, spans) -> None:
    (folder / "edit" / "edl.json").write_text(json.dumps({
        "version": 1,
        "sources": {"C0101": str(folder / "C0101.MP4")},
        "ranges": [{"source": "C0101", "start": start, "end": end} for start, end in spans],
    }), encoding="utf-8")


def _run(hub: Hub, events: list, cmd: str, folder: Path) -> dict:
    hub.dispatch({"id": cmd, "cmd": cmd, "folder": str(folder)})
    return [event for event in events if event.get("type") == "result"][-1]


def test_storyboard_words_carry_their_text(tmp_path):
    folder = _folder(tmp_path, video=False)
    events: list = []
    data = Hub(ROOT, emit=events.append).storyboard({"folder": str(folder)})
    assert [word["text"] for word in data["words"]["C0101"]] == ["Xin", "chào", "Đà", "Lạt"]
    assert data["words"]["C0101"][1] == {"start": 0.9, "end": 1.3, "text": "chào"}


@needs_ffmpeg
def test_clips_are_reused_per_range_and_stale_ones_removed(tmp_path):
    folder = _folder(tmp_path, video=True)
    events: list = []
    hub = Hub(ROOT, emit=events.append)

    first = _run(hub, events, "clips", folder)
    assert first["ok"] is True, first
    clips = first["data"]["clips"]
    assert [item["index"] for item in clips] == [0, 1]
    assert all(item["clip"] and Path(item["clip"]).is_file() for item in clips)
    assert all(item["poster"] and Path(item["poster"]).is_file() for item in clips)
    assert [event["data"]["index"] for event in events if event.get("type") == "clip"] == [0, 1]
    kept = Path(clips[0]["clip"])
    stamp = kept.stat().st_mtime_ns

    _write_edl(folder, [(0.45, 1.38), (1.95, 2.3)])
    second = _run(hub, events, "clips", folder)["data"]["clips"]
    assert second[0]["clip"] == str(kept)
    assert kept.stat().st_mtime_ns == stamp
    assert second[1]["clip"] != clips[1]["clip"]
    assert not Path(clips[1]["clip"]).exists()
    assert not Path(clips[1]["poster"]).exists()
    names = sorted(path.name for path in (folder / "edit" / "storyboard").glob("clip_*"))
    assert len(names) == 4


@needs_ffmpeg
def test_inventory_reports_duration_and_poster(tmp_path):
    folder = _folder(tmp_path, video=True)
    events: list = []
    hub = Hub(ROOT, emit=events.append)
    rows = hub.inventory({"folder": str(folder)})
    assert rows[0]["name"] == "C0101.MP4"
    assert rows[0]["cached"] is True
    assert rows[0]["poster"] and Path(rows[0]["poster"]).is_file()
    if rows[0]["duration"] is not None:
        assert abs(rows[0]["duration"] - 3.0) < 0.2


def test_inventory_survives_without_ffmpeg(tmp_path, monkeypatch):
    folder = _folder(tmp_path, video=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    rows = Hub(ROOT, emit=lambda _msg: None).inventory({"folder": str(folder)})
    assert rows[0]["poster"] is None
    assert rows[0]["duration"] is None
