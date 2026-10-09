import ast
import socket
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "skipwatch"
NETWORK_MODULES = {"socket", "urllib.request", "http.client"}
NETWORK_ROOTS = {"requests", "httpx", "yt_dlp", "urllib3", "aiohttp", "ssl"}
FORBIDDEN = {"anthropic", "claude_agent_sdk", "claude_code_sdk"}
# media.py may trigger the one-time static-ffmpeg download (plan issue 8), and nothing else.
STATIC_FFMPEG_ALLOWED = Path("media.py")


def _imports(path: Path) -> set[str]:
    """Every module a file imports. `from a import b` yields both `a` and `a.b`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def _network_violations(rel: Path, imports: set[str]) -> set[str]:
    """Network imports `rel` (relative to src/skipwatch) is not allowed to make (R-ARCH-1)."""
    allowed_network = rel.parts[0] == "providers"
    bad = set()
    for name in imports:
        root = name.split(".")[0]
        if root == "static_ffmpeg":
            if rel != STATIC_FFMPEG_ALLOWED:
                bad.add(name)
        elif not allowed_network and (name in NETWORK_MODULES or root in NETWORK_ROOTS):
            bad.add(name)
    return bad


def test_r_arch_1_no_model_sdk_imports():
    for path in SRC.rglob("*.py"):
        bad = {n for n in _imports(path) if n.split(".")[0] in FORBIDDEN}
        assert not bad, f"{path} imports {bad}"


def test_r_arch_1_network_only_in_providers():
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC)
        bad = _network_violations(rel, _imports(path))
        assert not bad, f"{rel} imports network module {bad}"


@pytest.mark.parametrize(
    "source",
    [
        "import socket",
        "import urllib.request",
        "from urllib import request",
        "from http import client",
        "import http.client",
        "import requests",
        "import httpx",
        "from yt_dlp import YoutubeDL",
        "import urllib3",
        "import aiohttp",
        "import ssl",
        "import static_ffmpeg",
        "from static_ffmpeg import run",
    ],
)
def test_r_arch_1_network_scan_catches(tmp_path, source):
    path = tmp_path / "mod.py"
    path.write_text(source + "\n", encoding="utf-8")
    assert _network_violations(Path("ingest.py"), _imports(path))


def test_r_arch_1_static_ffmpeg_only_in_media(tmp_path):
    path = tmp_path / "mod.py"
    path.write_text("import static_ffmpeg\n", encoding="utf-8")
    assert not _network_violations(Path("media.py"), _imports(path))
    assert _network_violations(Path("providers/x.py"), _imports(path))


def test_r_arch_1_providers_may_use_network(tmp_path):
    path = tmp_path / "mod.py"
    path.write_text("from urllib import request\nimport ssl\n", encoding="utf-8")
    assert not _network_violations(Path("providers/x.py"), _imports(path))


def test_r_arch_1_plain_urllib_parse_is_fine(tmp_path):
    path = tmp_path / "mod.py"
    path.write_text("from urllib.parse import urlparse\nimport http\n", encoding="utf-8")
    assert not _network_violations(Path("ingest.py"), _imports(path))


def test_socket_guard_blocks_connections():
    from tests.conftest import NetworkBlocked

    with pytest.raises(NetworkBlocked):
        socket.create_connection(("example.com", 80))


def test_socket_guard_blocks_dns():
    from tests.conftest import NetworkBlocked

    with pytest.raises(NetworkBlocked):
        socket.getaddrinfo("example.com", 80)
