"""Locate ffmpeg and the four local agent CLIs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from desktop.agents import classify_agent_binary

AGENT_ORDER = (
    ("claude", "Claude"),
    ("codex", "Codex"),
    ("grok", "Grok"),
    ("cursor", "Cursor"),
)


def _run(argv: list[str], timeout: float = 8) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def parse_claude_status(stdout: str) -> bool | None:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and "loggedIn" in data:
        return bool(data["loggedIn"])
    return None


def parse_codex_status(text: str, code: int) -> bool | None:
    lowered = text.lower()
    if "logged out" in lowered or "not logged" in lowered:
        return False
    if "logged in" in lowered:
        return True
    if code == 0:
        return True
    return False


def parse_cursor_status(text: str) -> bool | None:
    lowered = text.lower()
    if "not logged" in lowered or "not authenticated" in lowered:
        return False
    if "logged in" in lowered or "authenticated" in lowered:
        return True
    return None


def grok_logged_in(auth_path: Path | None = None) -> bool:
    path = auth_path or (Path.home() / ".grok" / "auth.json")
    try:
        return path.is_file() and path.stat().st_size > 2
    except OSError:
        return False


def python_deps_ok() -> bool:
    try:
        import requests  # noqa: F401
        import PIL  # noqa: F401
    except Exception:
        return False
    return True


EXTRA_BIN_DIRS = (
    "/opt/homebrew/bin",
    "/usr/local/bin",
)


def find_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    home = Path.home()
    for directory in (
        *EXTRA_BIN_DIRS,
        home / ".local" / "bin",
        home / ".grok" / "bin",
        home / ".cargo" / "bin",
    ):
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _tool(which, name: str) -> dict:
    found = which(name)
    return {"found": bool(found), "path": found}


def collect_agents(
    *,
    which=shutil.which,
    version_of=None,
    login_of=None,
    grok_auth: Path | None = None,
    include_login: bool = True,
) -> list[dict]:
    if version_of is None:
        def version_of(path: str) -> str:
            _code, out, err = _run([path, "--version"], timeout=5)
            return f"{out}\n{err}"

    if login_of is None:
        def login_of(provider: str, path: str) -> bool | None:
            return _login(provider, path, grok_auth)

    grok_bin = which("grok")
    grok_path = Path(grok_bin) if grok_bin else None
    agent_bin = which("agent")
    cursor_agent_bin = which("cursor-agent")
    classified: dict[str, tuple[str, str]] = {}
    cursor_blocked_by_grok = False

    candidates = [
        ("claude", which("claude")),
        ("codex", which("codex")),
        ("grok", grok_bin),
        ("cursor-agent", cursor_agent_bin),
        ("agent", agent_bin),
    ]
    for name, found in candidates:
        if not found:
            continue
        version = version_of(found) if include_login else ""
        identity = classify_agent_binary(name, version, Path(found), grok_path)
        if name == "agent" and identity == "grok":
            cursor_blocked_by_grok = True
        if identity == "grok" and "grok" not in classified:
            classified["grok"] = (found, "")
        elif identity == "cursor" and "cursor" not in classified:
            classified["cursor"] = (found, "")
        elif identity is None and name in {"claude", "codex"}:
            classified[name] = (found, "")
        elif name in {"claude", "codex"} and name not in classified:
            classified[name] = (found, "")

    # claude/codex are not classified by classify_agent_binary unless name matches.
    for provider, binary_name in (("claude", "claude"), ("codex", "codex")):
        found = which(binary_name)
        if found and provider not in classified:
            classified[provider] = (found, "")

    agents = []
    for provider, label in AGENT_ORDER:
        found = classified.get(provider)
        if not found:
            detail = ""
            if provider == "cursor" and cursor_blocked_by_grok:
                detail = "Lệnh agent trên PATH là Grok, không phải Cursor CLI."
            agents.append({
                "id": provider,
                "label": label,
                "found": False,
                "path": None,
                "logged_in": None,
                "detail": detail,
            })
            continue
        path = found[0]
        logged = login_of(provider, path) if include_login else None
        if logged is True:
            detail = "đã đăng nhập"
        elif logged is False:
            detail = "chưa đăng nhập"
        else:
            detail = ""
        agents.append({
            "id": provider,
            "label": label,
            "found": True,
            "path": path,
            "logged_in": logged,
            "detail": detail,
        })
    return agents


def _login(provider: str, path: str, grok_auth: Path | None) -> bool | None:
    if provider == "claude":
        _code, out, _err = _run([path, "auth", "status", "--json"])
        return parse_claude_status(out)
    if provider == "codex":
        code, out, err = _run([path, "login", "status"])
        return parse_codex_status(f"{out}\n{err}", code)
    if provider == "grok":
        return grok_logged_in(grok_auth)
    if provider == "cursor":
        code, out, err = _run([path, "status"])
        parsed = parse_cursor_status(f"{out}\n{err}")
        if parsed is not None:
            return parsed
        return True if code == 0 else None
    return None


def binary_for(provider: str, agents: list[dict] | None = None) -> str:
    rows = agents if agents is not None else collect_agents(include_login=False)
    for row in rows:
        if row["id"] == provider and row["found"] and row["path"]:
            return row["path"]
    raise RuntimeError(f"{provider} không có trên PATH")


def check_deps(*, include_login: bool = True) -> dict:
    return {
        "ffmpeg": _tool(find_tool, "ffmpeg"),
        "ffprobe": _tool(find_tool, "ffprobe"),
        "uv": _tool(find_tool, "uv"),
        "python_deps": python_deps_ok(),
        "agents": collect_agents(which=find_tool, include_login=include_login),
    }
