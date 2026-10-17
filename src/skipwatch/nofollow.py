"""os.open that never follows a symlink at the path's last component, on every OS.

POSIX has O_NOFOLLOW. Windows has no such flag, and its CreateFile follows a symlink (a
dangling one too, creating the target), so there the file is opened with
FILE_FLAG_OPEN_REPARSE_POINT, which opens a link itself rather than what it points to, and
the open is refused when the handle is a name surrogate: a symlink, junction or mount point.
Other reparse points (OneDrive placeholders, deduplicated files) are ordinary files and open.
Folders above the last component are followed on both, as O_NOFOLLOW does.
"""

import errno
import os
import stat
import sys
from pathlib import Path

_ACCESS_MASK = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
_SUPPORTED = _ACCESS_MASK | os.O_CREAT | os.O_EXCL | os.O_TRUNC | os.O_APPEND
_ACCESS_MODES = (os.O_RDONLY, os.O_WRONLY, os.O_RDWR)
# IsReparseTagNameSurrogate: the tag names another file or folder (symlink, junction, mount)
NAME_SURROGATE_BIT = 0x20000000


def check_flags(flags: int) -> int:
    """The access mode of flags; ValueError for a bit open_nofollow does not support, or for
    an access mode that is none of O_RDONLY, O_WRONLY and O_RDWR (O_WRONLY | O_RDWR)."""
    unsupported = flags & ~_SUPPORTED
    if unsupported:
        raise ValueError(f"open_nofollow does not support flag bits {unsupported:#x}")
    access = flags & _ACCESS_MASK
    if access not in _ACCESS_MODES:
        raise ValueError(f"open_nofollow: {access:#x} is not one access mode")
    return access


def is_link(st: os.stat_result) -> bool:
    """Whether a Windows fstat result is a name-surrogate reparse point."""
    attributes = getattr(st, "st_file_attributes", 0)
    tag = getattr(st, "st_reparse_tag", 0)
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT and tag & NAME_SURROGATE_BIT)


def _refuse(path: Path) -> OSError:
    return OSError(errno.ELOOP, "refusing to open a symlink or junction", str(path))


if sys.platform == "win32":
    import _winapi
    import msvcrt

    _GENERIC_READ = 0x80000000
    _GENERIC_WRITE = 0x40000000
    _FILE_SHARE_ALL = 0x1 | 0x2 | 0x4  # read, write, delete: as POSIX lets others in
    _CREATE_NEW = 1
    _OPEN_EXISTING = 3
    _OPEN_ALWAYS = 4
    _FILE_ATTRIBUTE_NORMAL = 0x80
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000

    def open_nofollow(path: Path, flags: int, mode: int = 0o666) -> int:
        """os.open(path, flags, mode), refused with ELOOP when path is a symlink or junction.
        Supports the access modes, O_CREAT, O_EXCL, O_TRUNC and O_APPEND (ValueError for any
        other bit); mode is ignored, as on Windows os.open uses it only for the read-only bit."""
        access = check_flags(flags)
        desired = {
            os.O_RDONLY: _GENERIC_READ,
            os.O_WRONLY: _GENERIC_WRITE,
            os.O_RDWR: _GENERIC_READ | _GENERIC_WRITE,
        }[access]
        if flags & os.O_CREAT and flags & os.O_EXCL:
            disposition = _CREATE_NEW  # a link at path counts as present: the open fails
        elif flags & os.O_CREAT:
            disposition = _OPEN_ALWAYS  # truncated below, once the handle is known not a link
        else:
            disposition = _OPEN_EXISTING
        handle = _winapi.CreateFile(
            str(path),
            desired,
            _FILE_SHARE_ALL,
            0,
            disposition,
            _FILE_ATTRIBUTE_NORMAL | _FILE_FLAG_OPEN_REPARSE_POINT,
            0,
        )
        try:
            fd = msvcrt.open_osfhandle(handle, access | (flags & os.O_APPEND))
        except OSError:
            _winapi.CloseHandle(handle)
            raise
        try:
            if is_link(os.fstat(fd)):
                raise _refuse(path)
            if flags & os.O_TRUNC:
                os.ftruncate(fd, 0)
        except OSError:
            os.close(fd)
            raise
        return fd

else:

    def open_nofollow(path: Path, flags: int, mode: int = 0o666) -> int:
        """os.open(path, flags | O_NOFOLLOW, mode): fails (ELOOP) when path is a symlink.
        The same flags as on Windows are supported (ValueError for any other bit)."""
        check_flags(flags)
        return os.open(path, flags | os.O_NOFOLLOW, mode)
