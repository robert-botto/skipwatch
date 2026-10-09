"""A text source has nothing to transcribe: exit 7, never exit 8 with install advice."""

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.errors import ExitCode
from skipwatch.models import IngestBundle, IngestContext, Route, SourceInfo
from skipwatch.workdir import WorkDir, write_model


@pytest.mark.parametrize("backend", ["auto", "mlx", "captions", "openai"])
def test_text_source_is_exit_7_before_any_backend(tmp_path, backend, sw_home):
    work = WorkDir(tmp_path / "w")
    work.ensure()
    bundle = IngestBundle(
        source=SourceInfo(kind="text", platform="generic", url="https://example.com/post"),
        context=IngestContext(post_text="words " * 300),
        route=Route(context="free"),
    )
    write_model(work.file("ingest.json"), bundle)
    r = CliRunner().invoke(app, ["transcribe", "--work", str(work.path), "--backend", backend])
    assert r.exit_code == ExitCode.NO_CONTENT, r.output
    assert "text source: nothing to transcribe" in r.output
    assert "install" not in r.output.casefold()
    assert not work.file("transcript.json").exists()
