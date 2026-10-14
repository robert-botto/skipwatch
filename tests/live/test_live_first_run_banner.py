"""Live: a headless `/skipwatch doctor` on a fresh home prints the first-run banner.

Runs only with SKIPWATCH_LIVE=1 (tests/conftest.py), and costs one real Claude Code session.
On 2026-10-14 a real first run read first-run-banner.md, called the katakana rain "corrupted
or garbled text" and skipped it; this is the end-to-end check for that. It loads the plugin
from this checkout (`--plugin-dir`), in `--permission-mode default`, with a throwaway
SKIPWATCH_HOME. CLAUDE_CONFIG_DIR is a throwaway too when ANTHROPIC_API_KEY or
CLAUDE_CODE_OAUTH_TOKEN can sign in without it; otherwise the session keeps the signed-in
config and turns off an installed skipwatch plugin, so only this checkout answers.
SKIPWATCH_BANNER_MODEL picks the model (for example haiku); unset, the CLI default runs.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from skipwatch import firstrun

pytestmark = pytest.mark.live

ROOT = Path(__file__).resolve().parents[2]
LOGO = [
    "╔═╗╦╔═╦╔═╗╦ ╦╔═╗╔╦╗╔═╗╦ ╦",
    "╚═╗╠╩╗║╠═╝║║║╠═╣ ║ ║  ╠═╣",
    "╚═╝╩ ╩╩╩  ╚╩╝╩ ╩ ╩ ╚═╝╩ ╩",
]
TAGLINE = "never send a human to watch a tutorial."
INSTALLED_PLUGIN = "skipwatch@skipwatch"


def claude_command(config_is_throwaway: bool) -> list[str]:
    claude = shutil.which("claude")
    if claude is None:
        pytest.skip("claude CLI not found")
    command = [claude, "-p", "/skipwatch doctor", "--plugin-dir", str(ROOT)]
    command += ["--permission-mode", "default", "--max-turns", "8", "--no-session-persistence"]
    command += ["--allowedTools", "Bash(*/scripts/skipwatch *)", "Read"]
    command += ["--output-format", "stream-json", "--verbose"]
    if model := os.environ.get("SKIPWATCH_BANNER_MODEL"):
        command += ["--model", model]
    if not config_is_throwaway:
        command += ["--settings", json.dumps({"enabledPlugins": {INSTALLED_PLUGIN: False}})]
    return command


def session(tmp_path: Path) -> tuple[list[str], list[str]]:
    """Every assistant text block and every Bash command of one headless session."""
    env = dict(os.environ, SKIPWATCH_HOME=str(tmp_path / "swhome"), SKIPWATCH_TREG_DISABLED="1")
    throwaway = bool(env.get("ANTHROPIC_API_KEY") or env.get("CLAUDE_CODE_OAUTH_TOKEN"))
    if throwaway:
        env["CLAUDE_CONFIG_DIR"] = str(tmp_path / "claude-config")
    r = subprocess.run(
        claude_command(throwaway),
        cwd=tmp_path,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )
    texts: list[str] = []
    bash: list[str] = []
    for line in r.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") != "assistant":
            continue
        for block in event.get("message", {}).get("content", []):
            if block.get("type") == "text":
                texts.append(block["text"])
            elif block.get("type") == "tool_use" and block.get("name") == "Bash":
                bash.append(block.get("input", {}).get("command", ""))
    assert texts or bash, f"no session events (exit {r.returncode}): {r.stderr[-2000:]}"
    return texts, bash


def test_live_first_run_prints_the_banner(tmp_path):
    texts, bash = session(tmp_path)
    # doctor ran from this checkout and used up the home's first run
    assert any(str(ROOT / "scripts" / "skipwatch") in c and " doctor" in c for c in bash), bash
    assert (tmp_path / "swhome" / firstrun.MARKER).exists()
    reply = "\n".join(texts)
    for row in LOGO:
        assert row in reply, reply
    assert TAGLINE in reply, reply
