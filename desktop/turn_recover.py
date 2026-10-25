"""Build turn.json from an agent reply when the CLI did not write the file."""

from __future__ import annotations

import json
import re
from pathlib import Path

from desktop.session import TurnError, parse_turn

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def coerce_turn(data: dict) -> dict:
    kind = data.get("kind")
    strategy = str(data.get("strategy") or "").strip()
    questions = data.get("questions") if isinstance(data.get("questions"), list) else []
    if kind == "questions" and not questions and strategy:
        return {"kind": "strategy", "strategy": strategy}
    if kind == "strategy":
        return {"kind": "strategy", "strategy": strategy}
    if kind == "questions":
        return {"kind": "questions", "questions": questions}
    if kind == "edl":
        return {"kind": "edl"}
    return data


def _loads(text: str) -> dict | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _turn_from_data(data: dict) -> dict | None:
    if "kind" in data:
        try:
            return parse_turn(coerce_turn(data))
        except TurnError:
            return None
    for key in ("result", "text"):
        value = data.get(key)
        if isinstance(value, str):
            found = turn_from_text(value)
            if found:
                return found
        elif isinstance(value, dict):
            found = _turn_from_data(value)
            if found:
                return found
    message = data.get("message")
    if isinstance(message, dict):
        found = _turn_from_data(message)
        if found:
            return found
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    found = turn_from_text(block["text"])
                    if found:
                        return found
    item = data.get("item")
    if isinstance(item, dict):
        return _turn_from_data(item)
    return None


def turn_from_text(text: str) -> dict | None:
    stripped = text.strip()
    direct = _loads(stripped)
    if direct and "kind" in direct:
        try:
            return parse_turn(coerce_turn(direct))
        except TurnError:
            return None
    for match in _FENCE.finditer(text):
        data = _loads(match.group(1))
        if data and "kind" in data:
            try:
                return parse_turn(coerce_turn(data))
            except TurnError:
                continue
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        data = _loads(text[start:end + 1])
        if data and "kind" in data:
            try:
                return parse_turn(coerce_turn(data))
            except TurnError:
                return None
    return None


def extract_turn(lines: list[str]) -> dict | None:
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith("{"):
            data = _loads(stripped)
            if data:
                found = _turn_from_data(data)
                if found:
                    return found
        found = turn_from_text(line)
        if found:
            return found
    return None


def _text_of(data: dict) -> str:
    for key in ("result", "text"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    message = data.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list):
            parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and isinstance(block.get("text"), str)
            ]
            joined = "\n".join(part for part in parts if part.strip())
            if joined.strip():
                return joined.strip()
        found = _text_of(message)
        if found:
            return found
    item = data.get("item")
    if isinstance(item, dict):
        return _text_of(item)
    return ""


def assistant_text(lines: list[str]) -> str:
    chunks: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("$"):
            continue
        if stripped.startswith("{"):
            data = _loads(stripped)
            if data:
                text = _text_of(data)
                if text:
                    chunks.append(text)
                continue
        chunks.append(stripped)
    for chunk in reversed(chunks):
        if len(chunk) >= 20:
            return chunk
    return chunks[-1] if chunks else ""


def materialize_turn(turn_path: Path, lines: list[str], *, strategy_approved: bool) -> bool:
    if turn_path.is_file():
        try:
            saved = json.loads(turn_path.read_text(encoding="utf-8"))
            parse_turn(coerce_turn(saved) if isinstance(saved, dict) else {})
            return True
        except (OSError, json.JSONDecodeError, TurnError):
            turn_path.unlink(missing_ok=True)
    turn = extract_turn(lines)
    if turn is None and not strategy_approved:
        text = assistant_text(lines).strip()
        if len(text) >= 20 and '"kind"' not in text[:200]:
            try:
                turn = parse_turn({"kind": "strategy", "strategy": text[:4000]})
            except TurnError:
                turn = None
    if turn is None:
        return False
    turn_path.parent.mkdir(parents=True, exist_ok=True)
    turn_path.write_text(json.dumps(turn, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def extract_edl(lines: list[str]) -> dict | None:
    for line in reversed(lines):
        found = _edl_in_text(line)
        if found:
            return found
        data = _loads(line.strip()) if line.strip().startswith("{") else None
        if not data:
            continue
        for key in ("result", "text"):
            value = data.get(key)
            if isinstance(value, str):
                found = _edl_in_text(value)
                if found:
                    return found
    return None


def _edl_in_text(text: str) -> dict | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    data = _loads(text[start:end + 1])
    if not data:
        return None
    if isinstance(data.get("sources"), dict) and isinstance(data.get("ranges"), list):
        return data
    return None


def agent_failure_message(code: int, lines: list[str]) -> str:
    text = assistant_text(lines).strip()
    message = "Agent chạy xong nhưng không đưa ra câu hỏi hay chiến lược."
    if code not in (0, None):
        message += f" Mã thoát {code}."
    if text:
        message += "\n\n" + text[:1200]
    return message
