import pytest

from skipwatch import transcribe
from skipwatch.adapters.registry import adapter_for, all_platforms
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import IngestBundle, IngestContext, MediaInfo, Route, SourceInfo
from skipwatch.providers.registry import content_providers, transcription_backends


def bundle(captions=False):
    ctx = IngestContext(
        captions_available=captions, captions_path="captions/a.en.vtt" if captions else None
    )
    return IngestBundle(
        source=SourceInfo(kind="file", platform="local", path="/x.mp4"),
        context=ctx,
        route=Route(context="local", media="local"),
    )


class FakeCloud:
    name, cloud, auto_rank = "openai", True, None

    def __init__(self, available=True):
        self._available = available

    def available(self, bundle):
        return self._available

    def missing_hint(self):
        return "set OPENAI_API_KEY"


class FakeLocal:
    cloud = False

    def __init__(self, name, rank, available):
        self.name, self.auto_rank, self._available = name, rank, available

    def available(self, bundle):
        return self._available

    def missing_hint(self):
        return f"install {self.name}"


def with_captions(**extra):
    return lambda: {"captions": transcription_backends()["captions"], **extra}


def test_localfile_registers_itself():
    assert "local" in all_platforms() and adapter_for("local") is not None
    assert adapter_for("nope") is None


def test_captions_backend_registered_with_rank_zero():
    b = transcription_backends()["captions"]
    assert b.auto_rank == 0 and b.cloud is False
    assert b.missing_hint() == "no captions sidecar or platform captions"


def test_content_free_is_a_library_not_a_provider():
    assert all(p.name != "free" for p in content_providers())


def test_r_tr_2_auto_never_picks_a_cloud_backend(monkeypatch):
    monkeypatch.setattr(transcribe, "transcription_backends", with_captions(openai=FakeCloud()))
    with pytest.raises(SkipwatchError) as e:
        transcribe.select_backend("auto", bundle(captions=False))
    assert e.value.code == ExitCode.MISSING_DEPENDENCY
    assert transcribe.select_backend("openai", bundle()).name == "openai"  # explicit is allowed


def test_auto_picks_lowest_available_rank(monkeypatch):
    backends = with_captions(
        faster=FakeLocal("faster", 2, True), mlx=FakeLocal("mlx", 1, True), openai=FakeCloud()
    )
    monkeypatch.setattr(transcribe, "transcription_backends", backends)
    assert transcribe.select_backend("auto", bundle(captions=True)).name == "captions"
    assert transcribe.select_backend("auto", bundle(captions=False)).name == "mlx"


def test_auto_without_any_backend_names_the_platform_whisper_extra(monkeypatch):
    monkeypatch.setattr(transcribe, "transcription_backends", with_captions())
    for apple, extra in ((True, "--extra mlx"), (False, "--extra whisper")):
        monkeypatch.setattr(transcribe, "is_apple_silicon", lambda apple=apple: apple)
        with pytest.raises(SkipwatchError) as e:
            transcribe.select_backend("auto", bundle(captions=False))
        assert e.value.code == ExitCode.MISSING_DEPENDENCY and extra in e.value.message


def test_explicit_unavailable_backend_is_exit_8_with_its_hint(monkeypatch):
    monkeypatch.setattr(
        transcribe, "transcription_backends", with_captions(openai=FakeCloud(available=False))
    )
    with pytest.raises(SkipwatchError) as e:
        transcribe.select_backend("openai", bundle())
    assert e.value.code == ExitCode.MISSING_DEPENDENCY
    assert "backend openai is not available: set OPENAI_API_KEY" in e.value.message


def test_explicit_known_but_unregistered_backend_is_exit_8(monkeypatch):
    monkeypatch.setattr(transcribe, "transcription_backends", with_captions())
    with pytest.raises(SkipwatchError) as e:
        transcribe.select_backend("deepgram", bundle())
    assert e.value.code == ExitCode.MISSING_DEPENDENCY


def test_ingest_url_without_adapter_is_exit_2(tmp_path, monkeypatch):
    from skipwatch.adapters.base import IngestOptions
    from skipwatch.config import load_config
    from skipwatch.ingest import build_bundle
    from skipwatch.workdir import WorkDir

    monkeypatch.setattr("skipwatch.ingest.adapter_for", lambda p: None)
    w = WorkDir(tmp_path / "w")
    w.ensure()
    with pytest.raises(SkipwatchError) as e:
        build_bundle("https://vimeo.com/1", w, IngestOptions(), load_config(tmp_path / "n.toml"))
    assert e.value.code == ExitCode.UNSUPPORTED_SOURCE


def test_download_failed_without_providers_is_exit_3_listing_routes(tmp_path, monkeypatch):
    from skipwatch.adapters.base import DownloadFailed, IngestOptions
    from skipwatch.config import load_config
    from skipwatch.ingest import build_bundle
    from skipwatch.workdir import WorkDir

    class Failing:
        def build(self, detected, work, opts):
            raise DownloadFailed(["free.yt-dlp.download: HTTP Error 403"])

    monkeypatch.setattr("skipwatch.ingest.adapter_for", lambda p: Failing())
    w = WorkDir(tmp_path / "w")
    w.ensure()
    with pytest.raises(SkipwatchError) as e:
        build_bundle(
            "https://vimeo.com/1", w, IngestOptions(provider="free"), load_config(tmp_path / "n")
        )
    assert e.value.code == ExitCode.DOWNLOAD_FAILED
    assert "free.yt-dlp.download: HTTP Error 403" in e.value.message
    assert "--cookies-from-browser" in e.value.message


class FakeProvider:
    name = "treg"

    def __init__(self, available=True, media=None):
        self._available, self._media, self.enriched = available, media, 0

    def available(self):
        return self._available

    def enrich(self, bundle, work, opts):
        self.enriched += 1
        return bundle.model_copy(update={"context": IngestContext(post_text="from provider")})

    def fetch_media(self, bundle, work, opts):
        return self._media


def test_media_fallback_uses_provider_media_and_records_attempts(tmp_path, monkeypatch):
    from skipwatch.adapters.base import DownloadFailed, IngestOptions
    from skipwatch.config import load_config
    from skipwatch.ingest import build_bundle
    from skipwatch.workdir import WorkDir

    class Failing:
        def build(self, detected, work, opts):
            raise DownloadFailed(["free.yt-dlp.download: HTTP Error 403"])

    provider = FakeProvider(media=MediaInfo(path="media/video.mp4", has_audio=True))
    monkeypatch.setattr("skipwatch.ingest.adapter_for", lambda p: Failing())
    monkeypatch.setattr("skipwatch.ingest.content_providers", lambda: [provider])
    w = WorkDir(tmp_path / "w")
    w.ensure()
    b = build_bundle("https://vimeo.com/1", w, IngestOptions(), load_config(tmp_path / "n"))
    assert b.media is not None and b.media.path == "media/video.mp4"
    assert b.route.media == "treg"
    assert "free.yt-dlp.download: HTTP Error 403" in b.route.fallbacks
    assert provider.enriched == 1 and b.context.post_text == "from provider"


def test_no_media_retries_as_text_source(tmp_path, monkeypatch):
    from skipwatch.adapters.base import IngestOptions, NoMediaError
    from skipwatch.config import load_config
    from skipwatch.ingest import build_bundle
    from skipwatch.workdir import WorkDir

    text_bundle = IngestBundle(
        source=SourceInfo(kind="text", platform="x"), route=Route(context="free")
    )

    class NoVideo:
        def build(self, detected, work, opts):
            raise NoMediaError(detected.value, "No video could be found in this tweet")

    class Text:
        def build(self, detected, work, opts):
            return text_bundle

    adapters = {"x": NoVideo(), "text": Text()}
    monkeypatch.setattr("skipwatch.ingest.adapter_for", adapters.get)
    w = WorkDir(tmp_path / "w")
    w.ensure()
    opts = IngestOptions(provider="free")
    cfg = load_config(tmp_path / "n")
    assert build_bundle("https://x.com/a/status/1", w, opts, cfg) == text_bundle
    del adapters["text"]
    with pytest.raises(SkipwatchError) as e:
        build_bundle("https://x.com/a/status/1", w, opts, cfg)
    assert e.value.code == ExitCode.NO_CONTENT and "has no video" in e.value.message


def test_provider_treg_requested_but_missing_is_exit_8(tmp_path, monkeypatch):
    from skipwatch.adapters.base import IngestOptions
    from skipwatch.config import load_config
    from skipwatch.ingest import enabled_providers

    cfg = load_config(tmp_path / "n.toml")
    monkeypatch.setattr("skipwatch.ingest.content_providers", lambda: [])
    with pytest.raises(SkipwatchError) as e:
        enabled_providers(IngestOptions(provider="treg"), cfg)
    assert e.value.code == ExitCode.MISSING_DEPENDENCY and "treg login" in e.value.message
    monkeypatch.setattr(
        "skipwatch.ingest.content_providers", lambda: [FakeProvider(available=False)]
    )
    with pytest.raises(SkipwatchError):
        enabled_providers(IngestOptions(provider="treg"), cfg)


def test_enabled_providers_free_auto_and_config_off(tmp_path, monkeypatch):
    from skipwatch.adapters.base import IngestOptions
    from skipwatch.ingest import enabled_providers
    from skipwatch.models import Config

    up, down = FakeProvider(), FakeProvider(available=False)
    monkeypatch.setattr("skipwatch.ingest.content_providers", lambda: [up])
    assert enabled_providers(IngestOptions(provider="free"), Config()) == []
    assert enabled_providers(IngestOptions(provider="auto"), Config()) == [up]
    off = Config.model_validate({"providers": {"treg": {"enabled": False}}})
    assert enabled_providers(IngestOptions(provider="auto"), off) == []
    monkeypatch.setattr("skipwatch.ingest.content_providers", lambda: [down])
    assert enabled_providers(IngestOptions(provider="auto"), Config()) == []


# ---- review fixes: local never consults providers, resilient and named registries ----


@pytest.fixture
def fresh_registries():
    from skipwatch.adapters import registry as adapter_registry
    from skipwatch.providers import registry as provider_registry

    caches = (
        adapter_registry._adapters,
        provider_registry._backends,
        provider_registry._content_providers,
        provider_registry._export_providers,
    )
    for c in caches:
        c.cache_clear()
    yield
    for c in caches:
        c.cache_clear()


@pytest.fixture
def extra_package_dir(tmp_path, monkeypatch, fresh_registries):
    """Add tmp_path to a package's search path so test modules look like real plugins."""
    import sys

    added: list[str] = []

    def add(package, files: dict[str, str]):
        for name, body in files.items():
            (tmp_path / f"{name}.py").write_text(body, encoding="utf-8")
            added.append(f"{package.__name__}.{name}")
        monkeypatch.setattr(package, "__path__", [*package.__path__, str(tmp_path)])

    yield add
    for name in added:
        sys.modules.pop(name, None)


def test_local_ingest_never_consults_content_providers(tmp_path, monkeypatch):
    from skipwatch.adapters.base import IngestOptions
    from skipwatch.ingest import build_bundle
    from skipwatch.models import Config
    from skipwatch.workdir import WorkDir

    class Touchy(FakeProvider):
        def available(self):
            raise AssertionError("a local ingest must not consult providers")

    class Local:
        def build(self, detected, work, opts):
            return bundle()

    monkeypatch.setattr("skipwatch.ingest.content_providers", lambda: [Touchy()])
    monkeypatch.setattr("skipwatch.ingest.adapter_for", lambda p: Local())
    video = tmp_path / "a.mp4"
    video.write_bytes(b"x")
    w = WorkDir(tmp_path / "w")
    w.ensure()
    for provider in ("auto", "treg"):
        b = build_bundle(str(video), w, IngestOptions(provider=provider), Config())
        assert b.source.platform == "local" and b.provider_calls == []


def test_missing_whisper_libraries_leave_captions_working(tmp_path, monkeypatch, fresh_registries):
    import sys

    from skipwatch.providers.registry import transcription_backends as backends
    from skipwatch.workdir import WorkDir, write_model

    for lib in ("faster_whisper", "mlx_whisper", "mlx"):
        monkeypatch.setitem(sys.modules, lib, None)  # import raises ImportError
    w = WorkDir(tmp_path / "w")
    w.ensure()
    (w.path / "captions").mkdir()
    (w.path / "captions" / "a.en.vtt").write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nhello there\n", encoding="utf-8"
    )
    write_model(w.file("ingest.json"), bundle(captions=True))
    captions = backends()["captions"]
    assert captions.available(bundle(captions=True))
    assert captions.transcribe(w, None).segments[0].text == "hello there"


def test_broken_backend_module_is_skipped_and_reported_once(extra_package_dir, capsys, monkeypatch):
    from skipwatch import providers
    from skipwatch.providers.registry import transcription_backends as backends

    extra_package_dir(
        providers,
        {
            "transcribe_zz_broken": "import skipwatch_no_such_module_xyz\n",
            "transcribe_zz_extra": (
                "class B:\n    name, cloud, auto_rank = 'extra', False, 5\nBACKENDS = (B(),)\n"
            ),
        },
    )
    first = backends()
    assert "captions" in first and "extra" in first
    backends()
    err = capsys.readouterr().err
    assert err.count("transcribe_zz_broken") == 1 and "skipwatch_no_such_module_xyz" in err


def test_new_adapter_module_is_discovered(extra_package_dir):
    from skipwatch import adapters

    extra_package_dir(adapters, {"zz_newplat": "PLATFORMS = ('newplat',)\nADAPTER = object()\n"})
    assert "newplat" in all_platforms() and adapter_for("newplat") is not None
    assert adapter_for("local") is not None


def test_duplicate_platform_names_both_modules(extra_package_dir):
    from skipwatch import adapters

    extra_package_dir(adapters, {"zz_dup": "PLATFORMS = ('local',)\nADAPTER = object()\n"})
    with pytest.raises(RuntimeError) as e:
        adapter_for("local")
    assert "localfile" in str(e.value) and "zz_dup" in str(e.value)


def test_backend_module_raising_at_import_is_skipped(extra_package_dir, capsys):
    from skipwatch import providers
    from skipwatch.providers.registry import transcription_backends as backends

    extra_package_dir(
        providers, {"transcribe_zz_raises": "raise RuntimeError('no GPU driver here')\n"}
    )
    assert "captions" in backends()
    err = capsys.readouterr().err
    assert err.count("transcribe_zz_raises") == 1 and "no GPU driver here" in err


# ---- M5-A: export providers are a third family discovered from providers/export_*.py ----


def test_export_registry_discovers_export_modules(monkeypatch, fresh_registries):
    import types

    from skipwatch.providers import registry

    class P:
        def __init__(self, name):
            self.name = name

        def enabled(self, cfg):
            return False

        def export(self, skill_dir, manifest, cfg): ...

    fake_b = types.ModuleType("skipwatch.providers.export_b")
    fake_b.PROVIDER = P("notes")  # pyright: ignore[reportAttributeAccessIssue]
    fake_a = types.ModuleType("skipwatch.providers.export_a")
    fake_a.PROVIDER = P("mem0")  # pyright: ignore[reportAttributeAccessIssue]
    no_provider = types.ModuleType("skipwatch.providers.export_helpers")
    modules = {"export_": [fake_b, fake_a, no_provider]}
    monkeypatch.setattr(registry, "_modules", lambda prefix: modules.get(prefix, []))
    assert list(registry.export_providers()) == ["mem0", "notes"]


def test_export_registry_empty_before_m6(fresh_registries):
    from skipwatch.providers.registry import export_providers

    assert export_providers() == {}


def test_export_module_file_is_discovered_and_duplicates_refused(extra_package_dir):
    from skipwatch import providers
    from skipwatch.providers.registry import export_providers

    body = "class P:\n    name = 'zz'\nPROVIDER = P()\n"
    extra_package_dir(providers, {"export_zz_one": body})
    assert list(export_providers()) == ["zz"]
    from skipwatch.providers import registry

    registry._export_providers.cache_clear()
    extra_package_dir(providers, {"export_zz_two": body})
    with pytest.raises(RuntimeError) as e:
        export_providers()
    assert "zz" in str(e.value)


def test_project_constants_shared_by_pack_share_and_docs():
    from skipwatch.project import PACK_SUFFIX, REPO_URL

    assert REPO_URL == "https://github.com/robert-botto/skipwatch"
    assert PACK_SUFFIX == ".skillpack.zip"
