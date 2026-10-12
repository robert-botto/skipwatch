from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from skipwatch.commands.workfiles import home_work_or_pack_folder
from skipwatch.output import emit_json, progress
from skipwatch.runner import run_command
from skipwatch.transcribe import run_transcribe
from skipwatch.workdir import WorkDir


class Backend(StrEnum):
    auto = "auto"
    captions = "captions"
    mlx = "mlx"
    faster = "faster"
    openai = "openai"
    groq = "groq"
    deepgram = "deepgram"


def _transcribe(work: Path, backend: str, model: str | None, json_out: bool) -> int:
    progress(f"Transcribing with backend {backend}")
    transcript = run_transcribe(WorkDir(home_work_or_pack_folder(work)), backend, model)
    silent = " (silent: leaning on frames)" if transcript.silent else ""
    progress(f"Transcribed {len(transcript.segments)} segments from {transcript.origin}{silent}")
    if json_out:
        emit_json(transcript)
    return 0


def register(app: typer.Typer) -> None:
    @app.command("transcribe")
    def _cmd(
        work: Annotated[Path, typer.Option("--work", help="The work folder for this run.")],
        backend: Annotated[
            Backend, typer.Option("--backend", help="Cloud backends only when named explicitly.")
        ] = Backend.auto,
        model: Annotated[str | None, typer.Option("--model", help="Whisper model name.")] = None,
        json_out: Annotated[bool, typer.Option("--json", help="Print transcript.json.")] = False,
    ):
        """Write a timed transcript.json from captions or a Whisper backend."""
        run_command(lambda: _transcribe(work, backend.value, model, json_out))
