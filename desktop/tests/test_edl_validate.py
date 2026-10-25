import json
from pathlib import Path

from desktop.edl_validate import validate_edl


def _word(start, end, text="hi"):
    return {"type": "word", "text": text, "start": start, "end": end}


def _fixture(tmp_path: Path, words, ranges, *, overlays=None, duration=10.0, source_name="C0103.MP4"):
    source = tmp_path / source_name
    source.write_bytes(b"not a real movie")
    edit = tmp_path / "edit"
    (edit / "transcripts").mkdir(parents=True)
    (edit / "transcripts" / f"{source.stem}.json").write_text(
        json.dumps({"words": words}),
        encoding="utf-8",
    )
    edl = {
        "version": 1,
        "sources": {source.stem: str(source)},
        "ranges": ranges,
    }
    if overlays is not None:
        edl["overlays"] = overlays
    return edit, edl, {source.stem: duration}


def test_legal_pad_passes(tmp_path):
    edit, edl, durations = _fixture(
        tmp_path,
        [_word(1.0, 1.4)],
        [{"source": "C0103", "start": 0.95, "end": 1.48}],
    )
    result = validate_edl(edl, edit, durations=durations, probe=False)
    assert result.ok, result.errors


def test_cut_inside_word_is_blocked(tmp_path):
    edit, edl, durations = _fixture(
        tmp_path,
        [_word(1.0, 1.4)],
        [{"source": "C0103", "start": 1.2, "end": 1.48}],
    )
    result = validate_edl(edl, edit, durations=durations, probe=False)
    assert not result.ok
    assert any("giữa một từ" in error for error in result.errors)


def test_tight_pad_is_blocked(tmp_path):
    edit, edl, durations = _fixture(
        tmp_path,
        [_word(1.0, 1.4)],
        [{"source": "C0103", "start": 1.0, "end": 1.48}],
    )
    result = validate_edl(edl, edit, durations=durations, probe=False)
    assert not result.ok
    assert any("Đệm đầu" in error for error in result.errors)


def test_loose_pad_is_blocked(tmp_path):
    edit, edl, durations = _fixture(
        tmp_path,
        [_word(1.0, 1.4)],
        [{"source": "C0103", "start": 0.5, "end": 1.48}],
    )
    result = validate_edl(edl, edit, durations=durations, probe=False)
    assert not result.ok
    assert any("Đệm đầu" in error for error in result.errors)


def test_missing_source(tmp_path):
    edit = tmp_path / "edit"
    edit.mkdir()
    edl = {
        "sources": {"C0103": str(tmp_path / "missing.MP4")},
        "ranges": [{"source": "C0103", "start": 0.95, "end": 1.48}],
    }
    result = validate_edl(edl, edit, durations={"C0103": 10}, probe=False)
    assert not result.ok
    assert any("Không thấy file nguồn" in error for error in result.errors)


def test_missing_overlay_is_warning_and_stripped(tmp_path):
    edit, edl, durations = _fixture(
        tmp_path,
        [_word(1.0, 1.4)],
        [{"source": "C0103", "start": 0.95, "end": 1.48}],
        overlays=[{"file": "animations/missing.mp4", "start_in_output": 0, "duration": 1}],
    )
    result = validate_edl(edl, edit, durations=durations, probe=False)
    assert result.ok, result.errors
    assert result.warnings
    assert result.render_edl["overlays"] == []


def test_short_tail_at_eof_is_allowed(tmp_path):
    edit, edl, durations = _fixture(
        tmp_path,
        [_word(9.98, 9.99)],
        [{"source": "C0103", "start": 9.93, "end": 10.0}],
        duration=10.0,
    )
    result = validate_edl(edl, edit, durations=durations, probe=False)
    assert result.ok, result.errors


def test_save_ranges_rejects_inside_word_without_writing(tmp_path):
    from desktop.server import Hub

    edit, edl, _durations = _fixture(
        tmp_path,
        [_word(1.0, 1.4)],
        [{"source": "C0103", "start": 0.95, "end": 1.48}],
    )
    edl_path = edit / "edl.json"
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    before = edl_path.read_text(encoding="utf-8")
    events = []
    hub = Hub(Path(__file__).resolve().parents[2], emit=events.append)
    hub.save_ranges({
        "id": "1",
        "folder": str(tmp_path),
        "ranges": [{"source": "C0103", "start": 1.2, "end": 1.48}],
    })
    assert edl_path.read_text(encoding="utf-8") == before
    result = events[-1]
    assert result["ok"] is False
    assert "giữa một từ" in result["error"]
