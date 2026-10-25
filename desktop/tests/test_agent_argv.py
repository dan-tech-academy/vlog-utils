from pathlib import Path

from desktop.agents import (
    agent_env,
    build_argv,
    classify_agent_binary,
    parse_session_id,
)
from desktop.deps import collect_agents, parse_claude_status
from desktop.session import build_prompt


FOOTAGE = Path("/tmp/footage")
SECRET = "sk-test-eleven-secret"


def _joined(provider: str, session: str | None = None) -> str:
    argv = build_argv(
        provider,
        binary=provider,
        prompt="edit the footage",
        footage=FOOTAGE,
        session_id=session,
    )
    return "\n".join(argv)


def test_argv_has_sandbox_flags_and_no_key():
    claude = _joined("claude", "ses_1")
    assert "--permission-mode\nacceptEdits" in claude
    assert "--resume\nses_1" in claude
    assert "--output-format\nstream-json" in claude
    assert str(FOOTAGE) not in claude

    codex = _joined("codex", "thread_1")
    assert "--sandbox\nworkspace-write" in codex
    assert "--skip-git-repo-check" in codex
    assert "--json" in codex
    assert "\nresume\nthread_1\n" in codex

    cursor = _joined("cursor", "chat_1")
    assert "--force" in cursor
    assert "--trust" in cursor
    assert f"--workspace\n{FOOTAGE}" in cursor
    assert "--resume\nchat_1" in cursor

    grok = _joined("grok", "grok_1")
    assert "--always-approve" in grok
    assert "--no-auto-update" in grok
    assert "--output-format\nstreaming-json" in grok
    assert f"--cwd\n{FOOTAGE}" in grok
    assert "\n-r\ngrok_1" in grok

    for provider in ("claude", "codex", "cursor", "grok"):
        assert SECRET not in _joined(provider, "id")
        assert "ELEVENLABS_API_KEY" not in _joined(provider)


def test_agent_env_strips_elevenlabs_key():
    env = agent_env({"PATH": "/usr/bin", "ELEVENLABS_API_KEY": SECRET, "XI_API_KEY": SECRET})
    assert env == {"PATH": "/usr/bin"}
    assert SECRET not in build_prompt({"strategy_approved": False}, "keep the joke")


def test_session_parsers():
    assert parse_session_id("codex", '{"type":"thread.started","thread_id":"abc"}') == "abc"
    assert parse_session_id("claude", '{"type":"system","session_id":"ses_1"}') == "ses_1"
    assert parse_session_id("cursor", '{"chatId":"c1"}') == "c1"
    assert parse_session_id("grok", '{"session_id":"g1"}') == "g1"
    assert parse_session_id("codex", "not json") is None


def test_grok_agent_binary_is_not_cursor(tmp_path):
    grok = tmp_path / "grok"
    agent = tmp_path / "agent"
    grok.write_text("g")
    agent.write_text("a")
    assert classify_agent_binary("agent", "grok 1.0.70", agent, grok) == "grok"
    assert classify_agent_binary("agent", "Cursor Agent 1.0", agent, None) == "cursor"


def test_collect_agents_does_not_count_grok_as_cursor():
    binaries = {
        "claude": "/usr/bin/claude",
        "codex": "/usr/bin/codex",
        "grok": "/opt/grok",
        "agent": "/opt/grok",
        "cursor-agent": None,
    }

    def which(name):
        return binaries.get(name)

    def version_of(path):
        if path == "/opt/grok":
            return "grok 1.0.70"
        if "claude" in path:
            return "2.1.304 (Claude Code)"
        return "codex-cli 0.162.0"

    rows = collect_agents(
        which=which,
        version_of=version_of,
        login_of=lambda _provider, _path: True,
        include_login=True,
    )
    by_id = {row["id"]: row for row in rows}
    assert by_id["claude"]["found"] is True
    assert by_id["codex"]["found"] is True
    assert by_id["grok"]["found"] is True
    assert by_id["grok"]["path"] == "/opt/grok"
    assert by_id["cursor"]["found"] is False
    assert "Grok" in by_id["cursor"]["detail"]


def test_parse_claude_status_ignores_email():
    payload = '{"loggedIn": true, "email": "person@example.com", "authMethod": "claude.ai"}'
    assert parse_claude_status(payload) is True
    assert parse_claude_status('{"loggedIn": false}') is False
    assert parse_claude_status("nope") is None
