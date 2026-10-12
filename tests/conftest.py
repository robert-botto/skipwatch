import os
import socket

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


@pytest.fixture(autouse=True)
def _no_real_treg(request, monkeypatch):
    """treg is a real, paid CLI on a Tier 3 machine: no non-live test may find it on PATH, so
    ingest under `auto` and doctor never run it. Tests that need treg pass a fake runner."""
    if request.node.get_closest_marker("live") is not None:
        return
    from skipwatch.providers import content_treg

    monkeypatch.setattr(content_treg, "_treg_path", lambda: None)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory, monkeypatch):
    """No test reads or writes the real ~/.skipwatch (ingest and transcribe store a run cache)."""
    monkeypatch.setenv("SKIPWATCH_HOME", str(tmp_path_factory.mktemp("default-swhome")))


@pytest.fixture
def sw_home(tmp_path, monkeypatch):
    home = tmp_path / "swhome"
    monkeypatch.setenv("SKIPWATCH_HOME", str(home))
    return home
