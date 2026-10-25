"""Argv builders and session-id parsers for the local CLIs.

Flags were checked against the CLIs on this machine:

- claude -p --output-format stream-json --permission-mode acceptEdits --resume
- codex exec --json --sandbox workspace-write --skip-git-repo-check -C DIR [resume ID]
- agent -p --force --trust --workspace DIR --output-format stream-json --resume
- grok -p --cwd DIR --output-format streaming-json --always-approve --no-auto-update -r
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

SECRET_ENV = ("ELEVENLABS_API_KEY", "XI_API_KEY")
PROVIDERS = ("claude", "codex", "grok", "cursor")


def agent_env(base: Mapping[str, str]) -> dict[str, str]:
    return {key: value for key, value in base.items() if key not in SECRET_ENV}


def build_argv(
    provider: str,
    *,
    binary: str,
    prompt: str,
    footage: Path,
    session_id: str | None,
) -> list[str]:
    folder = str(footage)
    if provider == "claude":
        argv = [
            binary, "-p",
            "--output-format", "stream-json",
            "--permission-mode", "acceptEdits",
        ]
        if session_id:
            argv += ["--resume", session_id]
        argv.append(prompt)
        return argv
    if provider == "codex":
        argv = [
            binary, "exec",
            "--json",
            "--sandbox", "workspace-write",
            "--skip-git-repo-check",
            "-C", folder,
        ]
        if session_id:
            argv += ["resume", session_id]
        argv.append(prompt)
        return argv
    if provider == "cursor":
        argv = [
            binary, "-p",
            "--force",
            "--trust",
            "--workspace", folder,
            "--output-format", "stream-json",
        ]
        if session_id:
            argv += ["--resume", session_id]
        argv.append(prompt)
        return argv
    if provider == "grok":
        argv = [
            binary,
            "--no-auto-update",
            "-p", prompt,
            "--cwd", folder,
            "--output-format", "streaming-json",
            "--always-approve",
        ]
        if session_id:
            argv += ["-r", session_id]
        return argv
    raise ValueError(f"unknown provider: {provider}")


def parse_session_id(provider: str, line: str) -> str | None:
    text = line.strip()
    if not text.startswith("{"):
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    if provider == "codex" and obj.get("type") == "thread.started":
        thread_id = obj.get("thread_id")
        if isinstance(thread_id, str) and thread_id:
            return thread_id
        return None
    keys = ["session_id", "sessionId"]
    if provider == "cursor":
        keys.append("chatId")
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def same_file(left: Path | None, right: Path | None) -> bool:
    if left is None or right is None:
        return False
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return str(left) == str(right)


def classify_agent_binary(
    name: str,
    version_text: str,
    path: Path,
    grok_path: Path | None,
) -> str | None:
    """Tell Grok's `agent` symlink apart from the Cursor `agent` CLI."""
    lowered = version_text.lower()
    if "grok" in lowered or same_file(path, grok_path):
        if name in {"grok", "agent"}:
            return "grok"
        return None
    if name == "cursor-agent" or "cursor" in lowered:
        return "cursor"
    if name == "agent":
        return "cursor"
    if name == "grok":
        return "grok"
    return None
