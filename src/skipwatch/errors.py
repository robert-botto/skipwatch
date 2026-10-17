from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    CHECK_FAILED = 1
    UNSUPPORTED_SOURCE = 2
    DOWNLOAD_FAILED = 3
    PRIVATE_CONTENT = 4
    SAFETY_FLAGS = 5
    TARGET_EXISTS = 6
    NO_CONTENT = 7
    MISSING_DEPENDENCY = 8
    PACK_INTEGRITY = 9
    USAGE = 64
    INTERNAL_ERROR = 70  # an engine bug, not a user error (EX_SOFTWARE in sysexits.h)


# 0.1.0 reads videos only: a URL with no video or audio exits 7 with this, at probe and ingest.
VIDEO_ONLY = (
    "SkipWatch 0.1.0 reads videos only. This page has no video or audio. Article support is "
    "planned for a later release."
)


class SkipwatchError(Exception):
    def __init__(self, code: ExitCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
