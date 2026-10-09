import ast
import socket
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "skipwatch"
NETWORK_MODULES = {"socket", "urllib.request", "http.client", "requests", "httpx", "yt_dlp"}
FORBIDDEN = {"anthropic", "claude_agent_sdk", "claude_code_sdk"}
# media.py may trigger the one-time static-ffmpeg download (plan issue 8).
NETWORK_ALLOWED = {"providers", "media.py"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_r_arch_1_no_model_sdk_imports():
    for path in SRC.rglob("*.py"):
        bad = {n for n in _imports(path) if n.split(".")[0] in FORBIDDEN}
        assert not bad, f"{path} imports {bad}"


def test_r_arch_1_network_only_in_providers():
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC)
        if rel.parts[0] in NETWORK_ALLOWED:
            continue
        bad = {
            n
            for n in _imports(path)
            if n in NETWORK_MODULES or n.split(".")[0] in {"requests", "httpx", "yt_dlp"}
        }
        assert not bad, f"{rel} imports network module {bad}"


def test_socket_guard_blocks_connections():
    from tests.conftest import NetworkBlocked

    with pytest.raises(NetworkBlocked):
        socket.create_connection(("example.com", 80))
