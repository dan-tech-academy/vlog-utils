"""Prompt, turn.json, and the strategy gate. The app owns state.json."""

from __future__ import annotations

import json
from pathlib import Path

from desktop.edl_validate import validate_edl


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
