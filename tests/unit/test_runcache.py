import json
import os
import shutil
from datetime import UTC, datetime, timedelta

import pytest

from skipwatch import runcache, transcribe
from skipwatch.adapters.base import IngestOptions
from skipwatch.config import load_config
from skipwatch.ingest import run_ingest
from skipwatch.models import (
    IngestBundle,
    IngestContext,
    MediaInfo,
    ProviderCall,
    Route,
    Segment,
    SourceInfo,
    Transcript,
)
from skipwatch.runcache import cache_key, lookup, store
from skipwatch.transcribe import run_transcribe
from skipwatch.workdir import WorkDir, read_model, write_model

URL = "https://vimeo.com/1"
T0 = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def url_bundle(url=URL, captions=False):
    ctx = IngestContext(
        captions_available=captions, captions_path="captions/a.en.vtt" if captions else None
    )
    return IngestBundle(
        source=SourceInfo(
            kind="video", platform="generic", url=url, canonical_url=url, duration_s=60
        ),
        context=ctx,
        media=MediaInfo(path="media/video.mp4", has_audio=True),
        route=Route(context="free", media="free"),
    )


def work_with_ingest(tmp_path, name, bundle=None):
    w = WorkDir(tmp_path / name)
    w.ensure()
    write_model(w.file("ingest.json"), bundle or url_bundle())
    return w


class CountingBackend:
    cloud = False

    def __init__(self, name, origin, rank):
        self.name, self.origin, self.auto_rank, self.calls = name, origin, rank, 0

    def available(self, bundle):
        return True

    def transcribe(self, work, model):
        self.calls += 1
        words = " ".join(["word"] * 40)
        return Transcript(
            origin=self.origin, model=model, segments=[Segment(start=0, end=30, text=words)]
        )

    def missing_hint(self):
        return ""


def treg_on_config(tmp_path):
    """Paid providers are opt-in (skill audit fix 15): these runs enable treg explicitly."""
    path = tmp_path / "treg-on.toml"
    path.write_text("[providers.treg]\nenabled = true\n", encoding="utf-8")
    return load_config(path)


@pytest.fixture
def clock(monkeypatch):
    now = {"t": T0}
    monkeypatch.setattr(runcache, "utcnow", lambda: now["t"])
    return now


def use_backends(monkeypatch, *backends):
    monkeypatch.setattr(transcribe, "transcription_backends", lambda: {b.name: b for b in backends})


def test_r_tr_3_transcript_reused_within_7_days(sw_home, tmp_path, monkeypatch, clock, capsys):
    faster = CountingBackend("faster", "faster-whisper", 2)
    use_backends(monkeypatch, faster)
    first = run_transcribe(work_with_ingest(tmp_path, "w1"), "auto", None)
    assert faster.calls == 1
    clock["t"] = T0 + timedelta(days=6, hours=23)
    w2 = work_with_ingest(tmp_path, "w2")
    second = run_transcribe(w2, "auto", None)
    assert faster.calls == 1  # the second run on a new work folder made 0 calls
    assert second == first == read_model(w2.file("transcript.json"), Transcript)
    assert (
        json.loads(w2.file("stages.json").read_text())["stages"]["transcribe"]["status"] == "done"
    )
    assert (
        "Transcribe: reused cached transcript (faster-whisper, 167h old)" in capsys.readouterr().err
    )


def test_r_tr_3_cache_ignored_after_7_days(sw_home, tmp_path, monkeypatch, clock):
    faster = CountingBackend("faster", "faster-whisper", 2)
    use_backends(monkeypatch, faster)
    run_transcribe(work_with_ingest(tmp_path, "w1"), "auto", None)
    clock["t"] = T0 + timedelta(days=8)
    run_transcribe(work_with_ingest(tmp_path, "w2"), "auto", None)
    assert faster.calls == 2
    # the stale entry was overwritten, so it is fresh again from the new time
    clock["t"] = T0 + timedelta(days=9)
    run_transcribe(work_with_ingest(tmp_path, "w3"), "auto", None)
    assert faster.calls == 2


def test_explicit_backend_mismatch_ignores_cache(sw_home, tmp_path, monkeypatch, clock):
    captions = CountingBackend("captions", "captions", 0)
    faster = CountingBackend("faster", "faster-whisper", 2)
    use_backends(monkeypatch, captions, faster)
    run_transcribe(work_with_ingest(tmp_path, "w1"), "captions", None)
    t = run_transcribe(work_with_ingest(tmp_path, "w2"), "faster", None)
    assert faster.calls == 1 and t.origin == "faster-whisper"
    run_transcribe(work_with_ingest(tmp_path, "w3"), "faster", None)  # now cached for faster
    assert faster.calls == 1 and captions.calls == 1


def test_explicit_model_mismatch_ignores_cache(sw_home, tmp_path, monkeypatch, clock):
    faster = CountingBackend("faster", "faster-whisper", 2)
    use_backends(monkeypatch, faster)
    run_transcribe(work_with_ingest(tmp_path, "w1"), "faster", "small")
    run_transcribe(work_with_ingest(tmp_path, "w2"), "faster", "large-v3-turbo")
    run_transcribe(work_with_ingest(tmp_path, "w3"), "faster", None)  # no model asked: any
    assert faster.calls == 2


def test_cache_key_local_file_changes_with_mtime(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"0123")
    src = SourceInfo(kind="file", platform="local", path=str(clip))
    before = cache_key(src)
    assert before is not None and len(before) == 16 and before == cache_key(src)
    os.utime(clip, ns=(1_000_000_000, 1_000_000_000))
    assert cache_key(src) != before
    assert (
        cache_key(SourceInfo(kind="file", platform="local", path=str(tmp_path / "gone.mp4")))
        is None
    )


def test_cache_key_prefers_canonical_url():
    a = SourceInfo(
        kind="video",
        platform="youtube",
        url="https://youtu.be/x",
        canonical_url="https://www.youtube.com/watch?v=x",
    )
    b = SourceInfo(
        kind="video",
        platform="youtube",
        url="https://youtube.com/watch?v=x&t=3",
        canonical_url="https://www.youtube.com/watch?v=x",
    )
    assert (
        cache_key(a)
        == cache_key(b)
        != cache_key(SourceInfo(kind="video", platform="youtube", url="https://youtu.be/x"))
    )


def test_store_keeps_earlier_files_and_lookup_needs_the_name(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text("A")
    b.write_text("B")
    store(tmp_path, "k" * 16, URL, {"ingest.json": a}, T0)
    assert lookup(tmp_path, "k" * 16, "transcript.json", T0) is None
    entry = store(tmp_path, "k" * 16, URL, {"transcript.json": b}, T0 + timedelta(days=1))
    assert entry.files == ["ingest.json", "transcript.json"]
    assert entry.created_at == "2026-10-09T12:00:00Z"  # never extended by a later store
    hit = lookup(tmp_path, "k" * 16, "ingest.json", T0 + timedelta(days=2))
    assert hit is not None and hit.read_text() == "A"


def test_lookup_ignores_corrupt_or_missing_entry(tmp_path):
    folder = tmp_path / "cache" / ("k" * 16)
    folder.mkdir(parents=True)
    (folder / "ingest.json").write_text("{}")
    assert lookup(tmp_path, "k" * 16, "ingest.json", T0) is None  # no entry.json
    (folder / "entry.json").write_text("not json")
    assert lookup(tmp_path, "k" * 16, "ingest.json", T0) is None


def test_corrupt_cached_transcript_is_a_miss(sw_home, tmp_path, monkeypatch, clock):
    faster = CountingBackend("faster", "faster-whisper", 2)
    use_backends(monkeypatch, faster)
    run_transcribe(work_with_ingest(tmp_path, "w1"), "auto", None)
    key = cache_key(url_bundle().source)
    (sw_home / "cache" / str(key) / "transcript.json").write_text("{broken")
    run_transcribe(work_with_ingest(tmp_path, "w2"), "auto", None)
    assert faster.calls == 2


# ---- ingest hook ----
class CountingAdapter:
    def __init__(self):
        self.downloads = 0

    def build(self, detected, work, opts):
        self.downloads += 1
        cookies = opts.cookies_from_browser is not None
        return url_bundle(detected.value).model_copy(update={"fetched_with_cookies": cookies})


class CountingProvider:
    name = "treg"

    def __init__(self, ok=True, post_text="from provider"):
        self.enriched, self.ok, self.post_text = 0, ok, post_text

    def available(self):
        return True

    def enrich(self, bundle, work, opts):
        self.enriched += 1
        call = ProviderCall(provider="treg", op="thread", ok=self.ok, cost_usd=0.01)
        ctx = bundle.context.model_copy(update={"post_text": self.post_text, "thread": ["t1"]})
        return bundle.model_copy(update={"context": ctx, "provider_calls": [call]})

    def fetch_media(self, bundle, work, opts):
        return None


def ingest_twice(sw_home, tmp_path, monkeypatch, providers):
    adapter = CountingAdapter()
    monkeypatch.setattr("skipwatch.ingest.adapter_for", lambda p: adapter)
    monkeypatch.setattr("skipwatch.ingest.content_providers", lambda: providers)
    cfg = treg_on_config(tmp_path)
    first = run_ingest(URL, WorkDir(tmp_path / "w1"), IngestOptions(), cfg=cfg)
    second = run_ingest(URL, WorkDir(tmp_path / "w2"), IngestOptions(), cfg=cfg)
    return adapter, first, second


def test_ingest_cache_skips_enrichment_but_not_media(sw_home, tmp_path, monkeypatch, clock):
    provider = CountingProvider()
    adapter, first, second = ingest_twice(sw_home, tmp_path, monkeypatch, [provider])
    assert provider.enriched == 1  # treg is not called again for the same URL
    assert adapter.downloads == 2  # media is never cached
    assert first.from_cache is False and second.from_cache is True
    assert second.context.post_text == "from provider" and second.context.thread == ["t1"]
    assert second.provider_calls == first.provider_calls
    on_disk = read_model(tmp_path / "w2" / "ingest.json", IngestBundle)
    assert on_disk.from_cache is True and on_disk.media == first.media
    calls = json.loads((tmp_path / "w1" / "calls.json").read_text())["calls"]
    assert calls[0]["provider"] == "treg"


def test_ingest_cache_keeps_this_runs_captions(sw_home, tmp_path, monkeypatch, clock):
    provider = CountingProvider()
    adapter = CountingAdapter()
    monkeypatch.setattr("skipwatch.ingest.adapter_for", lambda p: adapter)
    monkeypatch.setattr("skipwatch.ingest.content_providers", lambda: [provider])
    cfg = treg_on_config(tmp_path)
    old = url_bundle(URL, captions=True)
    old_ctx = old.context.model_copy(update={"captions_path": "captions/old.en.vtt"})
    adapter.build = lambda d, w, o: old.model_copy(update={"context": old_ctx})
    run_ingest(URL, WorkDir(tmp_path / "w1"), IngestOptions(), cfg=cfg)
    adapter.build = lambda d, w, o: url_bundle(d.value, captions=True)
    second = run_ingest(URL, WorkDir(tmp_path / "w2"), IngestOptions(), cfg=cfg)
    assert second.from_cache and second.context.captions_path == "captions/a.en.vtt"


def test_ingest_cache_missed_when_a_provider_was_not_used_before(
    sw_home, tmp_path, monkeypatch, clock
):
    adapter = CountingAdapter()
    provider = CountingProvider()
    monkeypatch.setattr("skipwatch.ingest.adapter_for", lambda p: adapter)
    monkeypatch.setattr("skipwatch.ingest.content_providers", lambda: [provider])
    cfg = treg_on_config(tmp_path)
    run_ingest(URL, WorkDir(tmp_path / "w1"), IngestOptions(provider="free"), cfg=cfg)
    second = run_ingest(URL, WorkDir(tmp_path / "w2"), IngestOptions(), cfg=cfg)
    assert provider.enriched == 1 and second.from_cache is False  # treg now enabled: ask it


def test_ingest_cache_ignored_after_7_days(sw_home, tmp_path, monkeypatch, clock):
    provider = CountingProvider()
    adapter = CountingAdapter()
    monkeypatch.setattr("skipwatch.ingest.adapter_for", lambda p: adapter)
    monkeypatch.setattr("skipwatch.ingest.content_providers", lambda: [provider])
    cfg = treg_on_config(tmp_path)
    run_ingest(URL, WorkDir(tmp_path / "w1"), IngestOptions(), cfg=cfg)
    clock["t"] = T0 + timedelta(days=8)
    second = run_ingest(URL, WorkDir(tmp_path / "w2"), IngestOptions(), cfg=cfg)
    assert provider.enriched == 2 and second.from_cache is False


def test_rerun_on_the_same_work_folder_is_idempotent(sw_home, tmp_path, monkeypatch, clock):
    faster = CountingBackend("faster", "faster-whisper", 2)
    use_backends(monkeypatch, faster)
    w = work_with_ingest(tmp_path, "w1")
    a = run_transcribe(w, "auto", None)
    b = run_transcribe(w, "auto", None)
    assert a == b and faster.calls == 1
    assert sorted(p.name for p in (sw_home / "cache").iterdir()) == [cache_key(url_bundle().source)]


def test_tests_never_touch_the_real_home():
    from pathlib import Path

    from skipwatch.config import skipwatch_home

    assert skipwatch_home() != Path.home() / ".skipwatch"
    assert not skipwatch_home().is_relative_to(Path.home() / ".skipwatch")


# ---- review fixes ----
def ingest_runs(tmp_path, monkeypatch, provider, *opts_list):
    adapter = CountingAdapter()
    monkeypatch.setattr("skipwatch.ingest.adapter_for", lambda p: adapter)
    monkeypatch.setattr("skipwatch.ingest.content_providers", lambda: [provider])
    cfg = treg_on_config(tmp_path)
    return [
        run_ingest(URL, WorkDir(tmp_path / f"w{i}"), opts, cfg=cfg)
        for i, opts in enumerate(opts_list)
    ]


COOKIES = IngestOptions(cookies_from_browser="firefox")


def test_cookie_fetched_ingest_never_reaches_a_cookieless_run(
    sw_home, tmp_path, monkeypatch, clock
):
    provider = CountingProvider(post_text="PRIVATE")
    first, second = ingest_runs(tmp_path, monkeypatch, provider, COOKIES, IngestOptions())
    assert first.fetched_with_cookies is True
    assert second.from_cache is False and provider.enriched == 2
    assert second.fetched_with_cookies is False


def test_cookieless_and_cookie_runs_never_share_an_entry(sw_home, tmp_path, monkeypatch, clock):
    provider = CountingProvider()
    _, second = ingest_runs(tmp_path, monkeypatch, provider, IngestOptions(), COOKIES)
    assert second.from_cache is False and provider.enriched == 2
    assert len(list((sw_home / "cache").iterdir())) == 2


def test_cookie_runs_reuse_their_own_entry_and_keep_the_flag(sw_home, tmp_path, monkeypatch, clock):
    provider = CountingProvider()
    _, second = ingest_runs(tmp_path, monkeypatch, provider, COOKIES, COOKIES)
    assert second.from_cache is True and provider.enriched == 1
    assert second.fetched_with_cookies is True


def test_cached_entry_with_cookies_is_a_miss_even_under_the_plain_key(
    sw_home, tmp_path, monkeypatch, clock
):
    # belt and braces: an entry flagged fetched_with_cookies is never served without cookies
    bundle = url_bundle().model_copy(
        update={
            "fetched_with_cookies": True,
            "provider_calls": [ProviderCall(provider="treg", op="thread", ok=True)],
        }
    )
    src = tmp_path / "ingest.json"
    write_model(src, bundle)
    store(sw_home, str(cache_key(bundle.source, providers=["treg"])), URL, {"ingest.json": src}, T0)
    assert runcache.cached_ingest(url_bundle(), ["treg"], cookies=False) is None
    store(sw_home, str(cache_key(bundle.source, True, ["treg"])), URL, {"ingest.json": src}, T0)
    hit = runcache.cached_ingest(url_bundle(), ["treg"], cookies=True)
    assert hit is not None and hit.fetched_with_cookies is True


def test_transcript_of_cookie_fetched_media_is_not_shared(sw_home, tmp_path, monkeypatch, clock):
    faster = CountingBackend("faster", "faster-whisper", 2)
    use_backends(monkeypatch, faster)
    private = url_bundle().model_copy(update={"fetched_with_cookies": True})
    run_transcribe(work_with_ingest(tmp_path, "w1", private), "auto", None)
    run_transcribe(work_with_ingest(tmp_path, "w2"), "auto", None)
    assert faster.calls == 2
    run_transcribe(work_with_ingest(tmp_path, "w3", private), "auto", None)
    assert faster.calls == 2


def test_failed_provider_call_is_neither_stored_nor_a_hit(sw_home, tmp_path, monkeypatch, clock):
    provider = CountingProvider(ok=False)
    _, second = ingest_runs(tmp_path, monkeypatch, provider, IngestOptions(), IngestOptions())
    assert second.from_cache is False and provider.enriched == 2
    assert not (sw_home / "cache").exists() or not any(
        "ingest.json" in p.name for p in (sw_home / "cache").rglob("*")
    )
    # an entry stored by someone else with only a failed call is still a miss
    bundle = url_bundle().model_copy(
        update={"provider_calls": [ProviderCall(provider="treg", op="thread", ok=False)]}
    )
    src = tmp_path / "ingest.json"
    write_model(src, bundle)
    store(sw_home, str(cache_key(bundle.source, providers=["treg"])), URL, {"ingest.json": src}, T0)
    assert runcache.cached_ingest(url_bundle(), ["treg"], cookies=False) is None


def test_cache_hit_writes_an_empty_calls_json(sw_home, tmp_path, monkeypatch, clock):
    provider = CountingProvider()
    first, second = ingest_runs(tmp_path, monkeypatch, provider, IngestOptions(), IngestOptions())
    calls = json.loads((tmp_path / "w0" / "calls.json").read_text())["calls"]
    assert len(calls) == 1 and calls[0]["cost_usd"] == 0.01
    assert second.from_cache is True
    assert json.loads((tmp_path / "w1" / "calls.json").read_text())["calls"] == []
    assert second.provider_calls == first.provider_calls  # the bundle keeps its history


def test_store_survives_a_leftover_temp_name(tmp_path):
    src = tmp_path / "a.json"
    src.write_text("old")
    store(tmp_path, "k" * 16, URL, {"ingest.json": src}, T0)
    folder = tmp_path / "cache" / ("k" * 16)
    (folder / "ingest.json.tmp").mkdir()  # another process mid-write, or one that died
    (folder / "entry.json.tmp").mkdir()
    src.write_text("A")
    store(tmp_path, "k" * 16, URL, {"ingest.json": src}, T0)
    hit = lookup(tmp_path, "k" * 16, "ingest.json", T0)
    assert hit is not None and hit.read_text() == "A"


def test_entry_removed_mid_lookup_is_not_a_crash(sw_home, tmp_path, monkeypatch, clock):
    import shutil

    faster = CountingBackend("faster", "faster-whisper", 2)
    use_backends(monkeypatch, faster)
    run_transcribe(work_with_ingest(tmp_path, "w1"), "auto", None)
    real = runcache._read_cached

    def then_clear(*args, **kwargs):
        result = real(*args, **kwargs)
        shutil.rmtree(sw_home / "cache")  # `cache --clear` from another shell
        return result

    monkeypatch.setattr(runcache, "_read_cached", then_clear)
    t = run_transcribe(work_with_ingest(tmp_path, "w2"), "auto", None)
    assert t.origin == "faster-whisper" and faster.calls == 1


# ---- a provider with nothing to add (M4: treg on a captioned YouTube video) ----
class NothingToAdd(CountingProvider):
    """Mirrors treg on a captioned YouTube video: enrich runs and makes no call."""

    def enrich(self, bundle, work, opts):
        self.enriched += 1
        return bundle


def test_provider_with_nothing_to_add_still_hits(sw_home, tmp_path, monkeypatch, clock):
    provider = NothingToAdd()
    first, second = ingest_runs(tmp_path, monkeypatch, provider, IngestOptions(), IngestOptions())
    assert first.provider_calls == [] and first.from_cache is False
    assert second.from_cache is True and provider.enriched == 1


def test_free_run_entry_never_serves_a_provider_run(sw_home, tmp_path, monkeypatch, clock):
    # nothing to add has no call either: only the provider set in the key tells them apart
    provider = NothingToAdd()
    first, second = ingest_runs(
        tmp_path, monkeypatch, provider, IngestOptions(provider="free"), IngestOptions()
    )
    assert second.from_cache is False and provider.enriched == 1
    third = run_ingest(
        URL, WorkDir(tmp_path / "w9"), IngestOptions(), cfg=treg_on_config(tmp_path)
    )
    assert third.from_cache is True and provider.enriched == 1


def test_captions_changed_since_the_cached_run_is_a_miss(sw_home, tmp_path, monkeypatch, clock):
    # treg asks for a YouTube transcript only when captions are missing
    provider = NothingToAdd()
    adapter = CountingAdapter()
    monkeypatch.setattr("skipwatch.ingest.adapter_for", lambda p: adapter)
    monkeypatch.setattr("skipwatch.ingest.content_providers", lambda: [provider])
    cfg = treg_on_config(tmp_path)
    adapter.build = lambda d, w, o: url_bundle(d.value, captions=True)
    run_ingest(URL, WorkDir(tmp_path / "w1"), IngestOptions(), cfg=cfg)
    adapter.build = lambda d, w, o: url_bundle(d.value, captions=False)
    second = run_ingest(URL, WorkDir(tmp_path / "w2"), IngestOptions(), cfg=cfg)
    assert second.from_cache is False and provider.enriched == 2


def test_link_fetch_failures_never_block_the_cache(sw_home, tmp_path, clock):
    """A dead link (link.get, link.resolve) is a content outcome; any other failed call is
    still a provider failure and a miss."""
    dead = ProviderCall(provider="free", op="link.get", ok=False, error="HTTP 404")
    unresolved = ProviderCall(provider="free", op="link.resolve", ok=False, error="HTTP 404")
    treg = ProviderCall(provider="treg", op="x.thread", ok=True)
    for calls, hit in (
        ([dead, unresolved, treg], True),
        ([treg.model_copy(update={"ok": False})], False),
    ):
        bundle = url_bundle().model_copy(update={"provider_calls": calls})
        src = tmp_path / "ingest.json"
        write_model(src, bundle)
        runcache.remember_ingest(bundle, src, False, ["treg"])
        got = runcache.cached_ingest(url_bundle(), ["treg"], cookies=False)
        assert (got is not None) is hit, calls
        shutil.rmtree(sw_home / "cache", ignore_errors=True)
