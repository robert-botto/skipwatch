"""mlx-whisper backend for Apple Silicon (8.4): `large-v3-turbo` by default.

mlx-whisper decodes a path with an `ffmpeg` on PATH, so it gets a float32 array of the
engine's own 16 kHz WAV instead (plan issue 13). Leading silence is trimmed first and added
back to every time: without VAD, Whisper pins the first word to 0.0 s.
"""

import importlib.util
import os
from typing import Any

from skipwatch.audio import load_trimmed
from skipwatch.doctor import extra_command, is_apple_silicon
from skipwatch.models import IngestBundle, Transcript
from skipwatch.providers.whisper_common import (
    download_failed,
    has_media,
    make_segment,
    or_silence,
    wav_for,
)
from skipwatch.workdir import WorkDir

DEFAULT_MODEL = "large-v3-turbo"
TURBO_REPO = "mlx-community/whisper-large-v3-turbo"


def _installed() -> bool:
    return importlib.util.find_spec("mlx_whisper") is not None


def repo_for(model: str) -> str:
    """A Hugging Face repo as given; turbo has its own repo; other sizes are `-mlx` repos."""
    if "/" in model:
        return model
    if model in ("large-v3-turbo", "turbo"):
        return TURBO_REPO
    return f"mlx-community/whisper-{model}-mlx"


class MlxWhisperBackend:
    name = "mlx"
    cloud = False
    auto_rank: int | None = 1

    def available(self, bundle: IngestBundle) -> bool:
        return is_apple_silicon() and _installed() and has_media(bundle)

    def missing_hint(self) -> str:
        if not is_apple_silicon():
            return "mlx-whisper needs Apple Silicon; use --backend faster"
        return extra_command(os.environ.get("CLAUDE_PLUGIN_ROOT"), "mlx")

    def transcribe(self, work: WorkDir, model: str | None) -> Transcript:
        # Lazy: the extra may be absent. huggingface_hub comes with mlx-whisper.
        import mlx_whisper  # pyright: ignore[reportMissingImports]
        from huggingface_hub import snapshot_download  # pyright: ignore[reportMissingImports]

        wav = wav_for(work)
        name = model or DEFAULT_MODEL
        try:  # resolve the weights first, so a failed download is told apart from a bad run
            local = snapshot_download(repo_for(name))
        except Exception as exc:  # offline, sandboxed or interrupted download
            raise download_failed(name) from exc
        samples, offset = load_trimmed(wav)
        result: dict[str, Any] = mlx_whisper.transcribe(  # its stub says dict[str, str | list]
            samples, path_or_hf_repo=str(local), word_timestamps=True
        )
        segments = [
            make_segment(
                s["start"],
                s["end"],
                s["text"],
                ((w["word"], w["start"], w["end"]) for w in s.get("words") or []),
                offset,
            )
            for s in result.get("segments", [])
        ]
        return Transcript(
            origin="mlx-whisper",
            model=name,
            language=result.get("language"),
            segments=or_silence(segments, wav),
        )


BACKENDS = (MlxWhisperBackend(),)
