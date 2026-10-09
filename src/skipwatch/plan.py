"""Reader batches (spec 8.6 Plan): consecutive chunks of frames in time order."""

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import Batch, BatchesFile, FramesFile
from skipwatch.workdir import WorkDir, read_model, run_stage, write_model

DEFAULT_BATCH_SIZE = 20


def make_batches(frames: FramesFile, size: int = DEFAULT_BATCH_SIZE) -> BatchesFile:
    ordered = [f.id for f in sorted(frames.frames, key=lambda f: f.t)]
    chunks = [ordered[i : i + size] for i in range(0, len(ordered), size)]
    return BatchesFile(
        batches=[
            Batch(id=n, frame_ids=chunk, notes_path=f"notes/batch-{n:02d}.json")
            for n, chunk in enumerate(chunks, start=1)
        ]
    )


def run_plan(work: WorkDir, size: int = DEFAULT_BATCH_SIZE) -> BatchesFile:
    def stage() -> BatchesFile:
        frames_path = work.file("frames.json")
        if not frames_path.exists():
            raise SkipwatchError(ExitCode.NO_CONTENT, f"no frames.json in {work.path}")
        result = make_batches(read_model(frames_path, FramesFile), size)
        write_model(work.file("batches.json"), result)
        return result

    return run_stage(work, "plan", stage)
