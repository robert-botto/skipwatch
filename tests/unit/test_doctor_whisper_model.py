"""Doctor's whisper-model line: a Hugging Face cache path check, never a download (issue 12)."""

from datetime import date

from skipwatch import doctor
from skipwatch.providers.whisper_common import hf_cached

BASE = dict(
    uv="0.9.29", python="3.12.12", ffmpeg="8.0.1", ffmpeg_source="system", ytdlp="2026.08.19",
    node=None, deno=None, whisper_mlx=False, whisper_faster=False, apple_silicon=True,
)  # fmt: skip


def cache_repo(hub, repo: str, with_snapshot: bool = True):
    folder = hub / f"models--{repo.replace('/', '--')}"
    (folder / "snapshots" / "abc123").mkdir(parents=True)  # created before any file lands
    if with_snapshot:
        (folder / "snapshots" / "abc123" / "config.json").write_text("{}")


def test_hf_cached_reads_the_cache_folder_only(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    assert not hf_cached("Systran/faster-whisper-small")
    cache_repo(tmp_path, "Systran/faster-whisper-small", with_snapshot=False)
    assert not hf_cached("Systran/faster-whisper-small")  # an interrupted download
    cache_repo(tmp_path, "mlx-community/whisper-large-v3-turbo")
    assert hf_cached("mlx-community/whisper-large-v3-turbo")


def test_hf_home_is_honoured(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    cache_repo(tmp_path / "hub", "Systran/faster-whisper-small")
    assert hf_cached("Systran/faster-whisper-small")


def line(p) -> str:
    report = doctor.build_report(p, date(2026, 10, 9), None)
    return next(x for x in doctor.render_table(report) if "whisper-model" in x)


def test_doctor_names_the_model_auto_would_use(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    mlx = doctor.Probe(**(BASE | dict(whisper_mlx=True, whisper_faster=True)))
    mlx = doctor.with_whisper_model(mlx)
    assert line(mlx) == "  whisper-model: large-v3-turbo (not downloaded, about 1.6 GB)"
    cache_repo(tmp_path, "mlx-community/whisper-large-v3-turbo")
    assert line(doctor.with_whisper_model(mlx)) == "  whisper-model: large-v3-turbo (cached)"
    faster = doctor.Probe(**(BASE | dict(whisper_faster=True, apple_silicon=False)))
    assert line(doctor.with_whisper_model(faster)) == (
        "  whisper-model: small (not downloaded, about 500 MB)"
    )


def test_no_whisper_backend_means_no_model_line():
    p = doctor.with_whisper_model(doctor.Probe(**BASE))
    report = doctor.build_report(p, date(2026, 10, 9), None)
    assert not any(c.name == "whisper-model" for c in report.components)


def test_probe_machine_fills_the_model_without_network(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    p = doctor.probe_machine()  # the autouse socket guard fails this on any network call
    if p.whisper_mlx or p.whisper_faster:
        assert p.whisper_model is not None and p.whisper_model_cached is False
    else:
        assert p.whisper_model is None
