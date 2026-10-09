"""faster-whisper backend (8.4): `small` int8 by default, `--model large-v3-turbo` for
--thorough. Weights download from Hugging Face on first use (plan issue 12).

It gets a float32 array of the engine's 16 kHz WAV, not a path: faster-whisper 1.2.1 decodes
paths with `av.open(..., metadata_errors=...)`, a keyword av 18 removed.
Leading silence is trimmed first and added back to every time.
"""

import importlib.util
import os

from skipwatch.audio import load_trimmed
from skipwatch.doctor import extra_command
from skipwatch.models import IngestBundle, Transcript
from skipwatch.providers.whisper_common import (
    download_failed,
    has_media,
    make_segment,
    or_silence,
    wav_for,
)
from skipwatch.workdir import WorkDir

DEFAULT_MODEL = "small"


def _installed() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


class FasterWhisperBackend:
    name = "faster"
    cloud = False
    auto_rank: int | None = 2

    def available(self, bundle: IngestBundle) -> bool:
        return _installed() and has_media(bundle)

    def missing_hint(self) -> str:
        return extra_command(os.environ.get("CLAUDE_PLUGIN_ROOT"), "whisper")

    def transcribe(self, work: WorkDir, model: str | None) -> Transcript:
        # Lazy: the extra may be absent.
        from faster_whisper import WhisperModel  # pyright: ignore[reportMissingImports]

        wav = wav_for(work)
        name = model or DEFAULT_MODEL
        try:
            whisper = WhisperModel(name, device="auto", compute_type="int8")
        except Exception as exc:  # offline, sandboxed or interrupted download
            raise download_failed(name) from exc
        samples, offset = load_trimmed(wav)
        raw, info = whisper.transcribe(samples, word_timestamps=True, vad_filter=True)
        segments = [
            make_segment(
                s.start, s.end, s.text, ((w.word, w.start, w.end) for w in s.words or []), offset
            )
            for s in raw
        ]
        return Transcript(
            origin="faster-whisper",
            model=name,
            language=info.language,
            segments=or_silence(segments, wav),
        )


BACKENDS = (FasterWhisperBackend(),)
