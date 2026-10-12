import os
import shutil
import socket
import tempfile
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

LIVE_OPT_IN = "SKIPWATCH_LIVE"


def pytest_collection_modifyitems(config, items):
    """Live tests touch the real network: skip them unless SKIPWATCH_LIVE=1.

    A marker expression alone (`-m live`, or a CI `-m` that replaces addopts) never enables them.
    """
    if os.environ.get(LIVE_OPT_IN) == "1":
        return
    skip = pytest.mark.skip(reason=f"live test: set {LIVE_OPT_IN}=1 to run it")
    for item in items:
        if item.get_closest_marker("live") is not None:
            item.add_marker(skip)


class NetworkBlocked(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _block_network(request, monkeypatch):
    if request.node.get_closest_marker("live") is not None:
        return  # reached only with SKIPWATCH_LIVE=1

    def guard(*args, **kwargs):
        raise NetworkBlocked("unit tests must not open sockets")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
    monkeypatch.setattr(socket, "getaddrinfo", guard)


TREG_DISABLED = "SKIPWATCH_TREG_DISABLED"
STUB_TREG = "#!/bin/sh\necho 'treg is disabled in tests' >&2\nexit 97\n"
STUB_TREG_CMD = "@echo treg is disabled in tests 1>&2\r\n@exit /b 97\r\n"
_STUB_DIR: str | None = None


def pytest_configure(config):
    """treg is a real, paid CLI on a Tier 3 machine: no non-live test may reach it, in this
    process or in a CLI subprocess. The guard goes on os.environ before any fixture of any
    scope runs (module fixtures such as the pipeline Engine snapshot os.environ):
    SKIPWATCH_TREG_DISABLED makes content_treg report treg missing, and a failing stub comes
    first on PATH for anything that looks treg up itself. Live tests drop both per test."""
    global _STUB_DIR
    _STUB_DIR = tempfile.mkdtemp(prefix="skipwatch-stub-treg-")
    stub = Path(_STUB_DIR)
    (stub / "treg").write_text(STUB_TREG, encoding="utf-8")
    (stub / "treg").chmod(0o755)
    (stub / "treg.cmd").write_text(STUB_TREG_CMD, encoding="utf-8")
    os.environ[TREG_DISABLED] = "1"
    os.environ["PATH"] = os.pathsep.join([_STUB_DIR, os.environ.get("PATH", "")])


def pytest_unconfigure(config):
    if _STUB_DIR is not None:
        shutil.rmtree(_STUB_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def _live_tests_see_the_real_treg(request, monkeypatch):
    if request.node.get_closest_marker("live") is None:
        return
    monkeypatch.delenv(TREG_DISABLED, raising=False)
    path = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p != _STUB_DIR]
    monkeypatch.setenv("PATH", os.pathsep.join(path))


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory, monkeypatch):
    """No test reads or writes the real ~/.skipwatch (ingest and transcribe store a run cache)."""
    monkeypatch.setenv("SKIPWATCH_HOME", str(tmp_path_factory.mktemp("default-swhome")))


@pytest.fixture
def sw_home(tmp_path, monkeypatch):
    home = tmp_path / "swhome"
    monkeypatch.setenv("SKIPWATCH_HOME", str(home))
    return home
