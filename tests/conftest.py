import socket

import pytest


class NetworkBlocked(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    def guard(*args, **kwargs):
        raise NetworkBlocked("unit tests must not open sockets")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)
    monkeypatch.setattr(socket, "create_connection", guard)


@pytest.fixture
def sw_home(tmp_path, monkeypatch):
    home = tmp_path / "swhome"
    monkeypatch.setenv("SKIPWATCH_HOME", str(home))
    return home
