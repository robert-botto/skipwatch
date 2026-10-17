"""open_nofollow refuses a symlink at the last component on every OS (Windows has no
O_NOFOLLOW, and there a plain O_EXCL open creates a dangling link's target)."""

import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from skipwatch import nofollow
from skipwatch.nofollow import check_flags, is_link, open_nofollow

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


SUPPORTED = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_TRUNC | os.O_APPEND
UNSUPPORTED_BIT = next(1 << n for n in range(31) if not (1 << n) & SUPPORTED)


@pytest.mark.parametrize(
    "flags", [os.O_WRONLY | os.O_RDWR, os.O_RDONLY | UNSUPPORTED_BIT, os.O_WRONLY | UNSUPPORTED_BIT]
)
def test_an_unsupported_flag_is_a_value_error_and_nothing_is_created(tmp_path, flags):
    with pytest.raises(ValueError):
        check_flags(flags)
    with pytest.raises(ValueError):
        open_nofollow(tmp_path / "x", flags | os.O_CREAT)
    assert not os.path.lexists(tmp_path / "x")


def _st(tag: int, attributes: int = stat.FILE_ATTRIBUTE_REPARSE_POINT) -> SimpleNamespace:
    return SimpleNamespace(st_file_attributes=attributes, st_reparse_tag=tag)


SYMLINK, JUNCTION = 0xA000000C, 0xA0000003  # IO_REPARSE_TAG_SYMLINK, _MOUNT_POINT
ONEDRIVE, DEDUP = 0x9000001A, 0x80000013  # IO_REPARSE_TAG_CLOUD_6, _DEDUP


@pytest.mark.parametrize(
    ("st", "refused"),
    [
        (_st(SYMLINK), True),
        (_st(JUNCTION), True),
        (_st(ONEDRIVE), False),  # a OneDrive placeholder is an ordinary file to open
        (_st(DEDUP), False),
        (_st(0, attributes=0), False),
        (SimpleNamespace(), False),  # a POSIX stat result has neither field
    ],
)
def test_only_a_name_surrogate_reparse_point_is_a_link(st, refused):
    assert is_link(st) is refused  # pyright: ignore[reportArgumentType]


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows open path checks the tag")
@pytest.mark.parametrize(("tag", "refused"), [(SYMLINK, True), (ONEDRIVE, False)])
def test_windows_open_refuses_by_the_tag_of_the_handle(tmp_path, victim, monkeypatch, tag, refused):
    real_fstat = os.fstat

    def fstat(fd):
        st = real_fstat(fd)
        return SimpleNamespace(
            st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
            st_reparse_tag=tag,
            st_size=st.st_size,
        )

    monkeypatch.setattr(nofollow.os, "fstat", fstat)
    if refused:
        with pytest.raises(OSError, match="symlink or junction"):
            open_nofollow(victim, os.O_RDONLY)
    else:
        os.close(open_nofollow(victim, os.O_RDONLY))
