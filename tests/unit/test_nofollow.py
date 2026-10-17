"""open_nofollow refuses a symlink at the last component on every OS (Windows has no
O_NOFOLLOW, and there a plain O_EXCL open creates a dangling link's target)."""

import os
from pathlib import Path

import pytest

from skipwatch.nofollow import open_nofollow

SECRET = b"keep\n"


def link(at: Path, target: Path) -> None:
    try:
        at.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"cannot create symlinks here: {exc}")


@pytest.fixture
def victim(tmp_path) -> Path:
    path = tmp_path / "victim"
    path.write_bytes(SECRET)
    return path


@pytest.mark.parametrize(
    "flags",
    [
        os.O_RDONLY,
        os.O_WRONLY | os.O_APPEND,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        os.O_RDWR,
    ],
)
def test_a_link_to_a_file_is_refused_and_the_file_is_untouched(tmp_path, victim, flags):
    lnk = tmp_path / "lnk"
    link(lnk, victim)
    with pytest.raises(OSError):
        os.close(open_nofollow(lnk, flags))
    assert victim.read_bytes() == SECRET


def test_a_dangling_link_is_present_for_exclusive_create(tmp_path):
    lnk = tmp_path / "lnk"
    target = tmp_path / "nosuch"
    link(lnk, target)
    with pytest.raises(OSError):
        os.close(open_nofollow(lnk, os.O_WRONLY | os.O_CREAT | os.O_EXCL))
    with pytest.raises(OSError):
        os.close(open_nofollow(lnk, os.O_WRONLY | os.O_CREAT | os.O_TRUNC))
    assert not os.path.lexists(target)


def test_a_plain_file_opens_with_each_flag(tmp_path, victim):
    with os.fdopen(open_nofollow(victim, os.O_RDONLY), "rb") as stream:
        assert stream.read() == SECRET
    with os.fdopen(open_nofollow(victim, os.O_WRONLY | os.O_APPEND), "ab") as stream:
        stream.write(b"more\n")
    assert victim.read_bytes() == SECRET + b"more\n"
    with os.fdopen(open_nofollow(victim, os.O_WRONLY | os.O_CREAT | os.O_TRUNC), "wb") as stream:
        stream.write(b"new\n")
    assert victim.read_bytes() == b"new\n"
    fresh = tmp_path / "fresh"
    os.close(open_nofollow(fresh, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    assert fresh.read_bytes() == b""
    with pytest.raises(FileExistsError):
        open_nofollow(fresh, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    with pytest.raises(FileNotFoundError):
        open_nofollow(tmp_path / "missing", os.O_RDONLY)
