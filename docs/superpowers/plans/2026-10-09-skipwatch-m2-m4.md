# SkipWatch M2 + M3 + M4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take SkipWatch from "local file to skill" (M1) to every source the spec names: YouTube and any yt-dlp URL with local or cloud transcription, cache and resume (M2); X, TikTok, Instagram, Facebook and text posts on the free route (M3); and the optional treg provider for thread context, replies, links, cross-check transcripts and media fallback, with a call log and cost on the review screen (M4).

**Architecture:** The engine keeps one ingest dispatcher and one transcription selector, both turned into registries by a single foundation amendment (M2-A) so every later package adds files instead of editing shared ones. Adapters build an `IngestBundle` on the free route through one shared yt-dlp wrapper (`providers/content_free.py`, the only module that imports `yt_dlp`); optional content providers (treg in M4) then enrich the bundle and supply media when the free route fails. Transcription backends register themselves; cloud backends are never chosen under `auto`.

**Tech Stack:** Python 3.11+, typer 0.27, pydantic 2.14, `yt-dlp[default]` 2026.8.19 (pulls `yt-dlp-ejs` 0.8.0 for the YouTube JS challenge solver), requests 2.x, faster-whisper 1.2.1, mlx-whisper 0.4.3, numpy (via the whisper extras), treg CLI 0.22.0 (subprocess only), pytest 9 with markers `pipeline`, `live`, `whisper`.

**Spec:** `docs/superpowers/specs/2026-10-09-skipwatch-design.md` (v2). Builds on `docs/superpowers/plans/2026-10-09-skipwatch-m0-m1.md`: its orchestrator decisions, its 14 resolved spec issues, its Global Constraints and its "Seams left for M2+" all stay binding. Contracts in spec sections 6 to 9 win over prose; section 3.4 defaults apply without asking.

---

## Orchestrator decisions carried in (2026-10-09, binding)

- Golden set videos are picked by agents (package M2-F). S3 applies to the agent-picked X video in slot G2, not to a tweet of Robert's.
- Remote `github.com/robert-botto/skipwatch` (private). Builders work in `.worktrees/<package>/`, branch `m2/<pkg>`, `m3/<pkg>` or `m4/<pkg>` cut from `origin/main`, commit, push, never merge, never open PRs, never force-push.
- Every model change M2 to M4 needs is in ONE package, M2-A, first in the order. No other package edits `models.py`. A builder who finds a missing field stops and reports.
- Paid evals and real network runs are allowed and run on Robert's Claude subscription; only the orchestrator triggers them. Builders may run `live` tests only inside the packages that say so (M2-B recording step, M2-F, M3-A).
- Tier detection per M0-M1 issue 10; yt-dlp invocation per R-ING-5; cookies only via the explicit `--cookies-from-browser` flag; cloud transcription only with an explicit `--backend` (R-TR-2).
- No builder sends Robert's name, email or any identifier to an external service, including in User-Agent headers. yt-dlp and requests run with their default User-Agent; recorded fixtures are scrubbed (Task M2-B1).

---

## Orchestrator decisions after the M3 spike (2026-10-09, binding)

Source: `docs/spikes/2026-10-m3-spike.md` and `skills/skipwatch/references/platforms.md` (merged in PR #28).

1. **X post id.** yt-dlp's `info["id"]` for X is the media id, not the post id. The X adapter takes the post id from `webpage_url` (`/status/<id>`) and builds `canonical_url = https://x.com/i/status/<post id>` from it. Test with the recorded G2 fixture.
2. **Text post that links a video post.** yt-dlp returns the linked post's video with no error. The X adapter accepts that media, but compares the returned post id with the requested one. When they differ: `source.author`, `source.url` and `source.title` describe the LINKED post (the video's creator gets the credit), the requested post's text goes into `context.thread` with its own URL, and `context.links` records the linked post. The review screen says "video came from a linked post: <url>". A post with no media and no link card stays kind `text` (exit 7 on the free route when it has no usable text, per issue 8).
3. **Instagram text.** `anyapi.instagram.post.detail` returns no caption. Instagram post text comes from the free route (yt-dlp `description`). M4-A uses treg for Instagram only as a media fallback and for the transcript cross-check, never for post text.
4. **Facebook media.** `anyapi.facebook.post.detail` returns no media URL. Facebook media comes from the free route only. M4-A never offers treg as a Facebook download fallback, and `platforms.md` says so.
5. **treg call id.** It is printed only on stderr (`treg: charged $X · call id <hex>`). `content_treg.py` parses it from stderr for `treg review`.
6. **TikTok formats.** 720p and 1080p are h265 only. ffmpeg decodes h265, so no change, but M3-C's tests include an h265 format fixture to prove the format rule still picks the smallest at or above 720p.

## Spec issues found (M2-M4)

Each is a genuine gap or contradiction. The plan applies the proposed resolution; the orchestrator confirms or overrules before builders start. None changes the spec text.

1. **`yt-dlp` without the `default` extra has no YouTube challenge solver.** Verified: `yt-dlp==2026.8.19` moved the YouTube JS challenge scripts into `yt-dlp-ejs`, which is only pulled by the `default` extra. With the M0 dependency `yt-dlp>=2026.8.19`, R-ING-5's "use node when present" does nothing useful. **Resolution:** M2-A changes the dependency to `yt-dlp[default]>=2026.8.19` (adds `yt-dlp-ejs==0.8.0`, `requests`, `certifi`, `brotli`, `mutagen`, `pycryptodomex`, `websockets`, `urllib3`). No remote components (`remote_components`) are ever enabled, so no script is fetched from npm or GitHub at run time.
2. **yt-dlp enables deno by default.** Verified: `YoutubeDL` sets `js_runtimes = {'deno': {}}` when the param is absent. R-ING-5 says "without a runtime otherwise". **Resolution:** `content_free.ydl_params()` always passes `js_runtimes` explicitly: `{'node': {'path': <node>}}` when node 22+ is on PATH (yt-dlp's own minimum is also 22.0.0), else `{'deno': {'path': <deno>}}` when deno is on PATH (yt-dlp minimum 2.3.0), else `{}`. Spec says node before deno; yt-dlp's own priority is deno first, so passing exactly one runtime is what makes the spec order hold.
3. **"720p" on vertical video.** TikTok, Reels and Shorts are 720x1280 or 1080x1920; a `height <= 1080` cap would reject the 1080x1920 original and pick 576x1024. **Resolution:** R-ING-4 compares the short side: "p" means `min(width, height)`. Format choice is a pure function (`select_format`, Task M2-B2) tested on recorded format lists: among formats whose short side is in [720, 1080] pick the smallest (`filesize` or `filesize_approx`, else `tbr * duration`); if none, the largest with short side below 720; never above 1080 when anything at or below exists.
4. **The long-video warning needs the duration before ingest (15, 3.4), but `ingest` downloads.** **Resolution:** new engine command `skipwatch probe <url|path> [--cookies-from-browser B] [--json]` (metadata only, writes nothing, prints `ProbeResult`). The orchestrator runs it first, warns over 60 minutes and continues only with `--yes` or confirmation. This adds one row to the section 6 contract; the PR notes it.
5. **`resume` needs the original input and flags, and `/skipwatch resume` takes no folder.** 5.3 has no file for run arguments and 6 has `resume <dir>` with a required folder. **Resolution:** (a) the orchestrator writes `run.json` (`RunFile`: input, flags, name) into the work folder before `ingest`; it has a model and a schema (R-ARCH-2). (b) `skipwatch resume [<dir>] [--json]`: with no folder it picks the newest work folder whose `first_incomplete()` is not `None` and whose `review` stage is not `done`; it prints `ResumeResult` (next stage, completed stages, `run`, whether `media/` still exists). A stage left `running` by a killed process counts as incomplete.
6. **Cache holds ingest.json and transcript.json, not media (5.3, R-TR-3).** Frames need media, so a cached ingest cannot skip the download. **Resolution:** an ingest cache hit reuses metadata, context, captions and provider calls (so treg is never billed twice for one URL within 7 days) but still downloads media; a transcribe cache hit copies `transcript.json` and skips Whisper or cloud (the expensive part). Cache key: `sha256(canonical_url or url)[:16]`; for local files `sha256(f"{abs_path}|{size}|{mtime_ns}")[:16]`. Entries older than 7 days are ignored and overwritten. `cache --clear` (M0-C) already removes the whole folder.
7. **Provider transcripts that are timed (treg `anyapi.youtube.video_transcript_full`, `anyapi.tiktok.video_transcript_full`) vs R-ING-2.** 8.3 calls the YouTube one "a timed transcript as a second source". `TranscriptOrigin` has no provider value. **Resolution:** provider transcripts, timed or not, are only ever stored as `transcript_hint` (text) and later `transcript.cross_check`; never as the primary transcript. Tier 3 already requires Whisper, so no Tier 3 machine lacks a primary timed source.
8. **Text-only X posts on the free route.** yt-dlp's Twitter extractor raises "No video could be found in this tweet" and returns no text. The text row of 8.3 says "page or post text". **Resolution:** on the free route a text-only X post exits 7 with "This post has no video. Enable treg (Tier 3) to read text posts." With treg (M4) the X adapter builds a `text` bundle from `anyapi.twitter.thread`. The M3 spike confirms the yt-dlp behaviour.
9. **Cost ceiling for treg is not specified.** 8.3 lists five optional treg calls per X post; nothing bounds a run. **Resolution:** new config key `[providers.treg] max_cost_usd = 0.05` (per run). `content_treg` stops calling once the logged `cost_usd` sum would exceed it and records `"treg: cost cap reached"` in `route.fallbacks`.
10. **`treg review` needs a call id; where it appears is undocumented.** `treg review CALL_ID {useful,partly,not_useful,not_sure}` exists (verified `--help`), but `treg call` help does not say where the call id is printed; AnyAPI bodies carry `resultId`, routed calls carry `_treg.served_by`. **Resolution:** the M3 spike records the exact location (stdout field, stderr line or header) in `platforms.md` and in a recorded fixture; M4-A parses it from there. If no call id is exposed, M4-A logs `review: null` with `error: "no call id"` for each call, and the spike sends one `treg feedback` describing the gap (no private data).
11. **treg login detection.** M0-M1 issue 11 deferred it to M4. `treg balance --json` is a free network call. **Resolution:** `content_treg.logged_in()` runs `treg balance --json` with a 10 s timeout; exit 0 and parseable JSON means logged in. Doctor (`doctor.py`, ownership moves to M4-A) calls it only when `treg` is on PATH, and caches nothing new. This is the only network doctor ever does, and it is inside `providers/`.
12. **Whisper model downloads.** `faster-whisper` and `mlx-whisper` fetch weights from Hugging Face on first use (about 500 MB for `small` int8, about 1.6 GB for `large-v3-turbo`). This is network outside the user's named platform. **Resolution:** it lives in `providers/transcribe_{faster,mlx}.py` (R-ARCH-1 holds). Doctor prints "whisper model <name>: not downloaded yet (about N MB on first use)" when the Hugging Face cache lacks it; the orchestrator says so before the first transcription. No install or download from doctor (R-DOC-1).
13. **mlx-whisper shells out to `ffmpeg` on PATH.** Verified in `mlx_whisper/audio.py`: `load_audio` runs `["ffmpeg", ...]`. A Tier 0+mlx machine that only has static ffmpeg would fail. **Resolution:** the engine extracts `media/audio-16k.wav` itself (`audio.py`, static or system ffmpeg via `media.ffmpeg_paths`) and passes mlx a float32 numpy array; faster-whisper gets the same WAV path (it decodes with PyAV, no ffmpeg needed).
14. **Cloud size limits.** OpenAI and Groq (free tier) cap uploads at 25 MB; OpenAI timestamps require `whisper-1` (`gpt-4o-transcribe` returns `json` only). **Resolution:** cloud backends upload 16 kHz mono MP3 at 32 kbps (about 14 MB per hour) and split audio longer than 50 minutes into 50-minute chunks, offsetting timings. OpenAI model `whisper-1`, Groq `whisper-large-v3-turbo`, Deepgram `nova-3`.
15. **`--provider treg` when treg is missing.** Not specified. **Resolution:** exit 8 with "treg is not installed or not logged in: run `treg login`" (R-TIER-2 still holds for `auto`, which silently degrades).
16. **Golden ranges and `--yes`.** `--yes` refuses to install with any gap, but golden ranges allow a small gap ceiling. **Resolution:** `scripts/golden_run.py` judges the staged draft and `check-report.json` in an isolated `SKIPWATCH_HOME`, installed or not.

## Tooling facts verified on 2026-10-09 (this machine)

| Fact | Verified result | Spec says |
|---|---|---|
| Resolution (`uv pip compile`, py3.11) | `yt-dlp==2026.8.19`, `faster-whisper==1.2.1` (`ctranslate2==4.8.2`, `av==18.1.0`, `onnxruntime==1.31.0`), `mlx-whisper==0.4.3` (`mlx==0.32.3`, pulls `torch==2.14.1`, `numpy==2.4.6`), `requests` via yt-dlp default extra, `httpx==0.28.1` (not used) | n/a |
| yt-dlp default extra | `yt-dlp[default]` adds `yt-dlp-ejs==0.8.0` (YouTube challenge solver), requests, certifi, brotli, mutagen, pycryptodomex, urllib3, websockets | spec lists `yt-dlp` only (issue 1) |
| yt-dlp JS runtimes | Python param `js_runtimes: dict[str, dict]`, keys `deno`, `node`, `bun`, `quickjs`, config key `path`; default when absent `{'deno': {}}`; CLI `--js-runtimes RUNTIME[:PATH]`, `--no-js-runtimes`. Minimum versions: node 22.0.0, deno 2.3.0, bun 1.2.11 | R-ING-5 name `--js-runtimes node` is correct for the CLI (issue 2) |
| yt-dlp remote components | param `remote_components` (`ejs:npm`, `ejs:github`); default none fetched | n/a; never enabled |
| yt-dlp params used | `quiet`, `no_warnings`, `noplaylist`, `skip_download`, `writesubtitles`, `writeautomaticsub`, `subtitlesformat`, `subtitleslangs`, `outtmpl`, `paths`, `format`, `merge_output_format`, `ffmpeg_location`, `cookiesfrombrowser` (tuple, e.g. `('chrome',)`), `socket_timeout`, `retries`, `overwrites`, `logger` | n/a |
| yt-dlp API | `YoutubeDL(params).extract_info(url, download=False)`; `process_ie_result(info, download=True)`; `YoutubeDL.sanitize_info(info)` for JSON-safe dumps; downloaded file in `info['requested_downloads'][0]['filepath']` | n/a |
| Cookie browsers | `yt_dlp.cookies.SUPPORTED_BROWSERS` = chromium family + `firefox`, `safari`; unsupported name raises `ValueError` | n/a |
| Extractor keys (`info['extractor_key']`) | `Youtube`, `Generic`, `Twitter`, `TikTok`, `TikTokVM`, `Instagram`, `Facebook`, `FacebookReel` | n/a |
| Login and private errors | `raise_login_required` appends a hint containing `--cookies-from-browser or --cookies` (or `Use --cookies, --cookies-from-browser, ...`); YouTube "sign in" reasons get the same hint; X protected tweets say "You are not authorized to view this protected tweet"; NSFW tweets "requires authentication". Errors arrive as `yt_dlp.utils.DownloadError` (message prefixed `ERROR: `) | R-ING-6 |
| YouTube subtitle formats | `_SUBTITLE_FORMATS = ('json3', 'srv1', 'srv2', 'srv3', 'ttml', 'srt', 'vtt')`; auto captions of the original language also appear as `<lang>-orig` | n/a |
| faster-whisper | `WhisperModel(model_size_or_path, device="auto", compute_type="default", download_root=None, local_files_only=False)`; `model.transcribe(audio, language=None, word_timestamps=True, vad_filter=...)` returns `(segments_generator, TranscriptionInfo)`; `Segment.start/end/text/words`, `Word.start/end/word/probability`; `info.language`, `info.duration`. Model names include `small`, `large-v3-turbo` (alias `turbo`) | 3.4 defaults match |
| mlx-whisper | `mlx_whisper.transcribe(audio: str | np.ndarray, *, path_or_hf_repo="mlx-community/whisper-tiny", word_timestamps=False, ...)` returns `{"text", "segments": [{"start","end","text","words":[{"word","start","end","probability"}]}], "language"}`; string audio is decoded by `ffmpeg` on PATH | issue 13 |
| OpenAI transcription | `POST https://api.openai.com/v1/audio/transcriptions` multipart (`file`, `model`, `response_format=verbose_json`, `timestamp_granularities[]=word`, `timestamp_granularities[]=segment`); only `whisper-1` supports `verbose_json`; response `{language, duration, text, words:[{word,start,end}], segments:[{id,start,end,text,...}]}`; verified from `openai==3.26.1` types (the docs page returns 403 to fetchers) | n/a |
| Groq transcription | `POST https://api.groq.com/openai/v1/audio/transcriptions`, OpenAI-compatible multipart; models `whisper-large-v3-turbo`, `whisper-large-v3`; `verbose_json` plus `timestamp_granularities[]` `word` and `segment`; 25 MB free tier, 100 MB dev tier | n/a |
| Deepgram transcription | `POST https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true&punctuate=true&utterances=true&detect_language=true`, header `Authorization: Token <key>`, raw body `Content-Type: application/octet-stream` (verified in `deepgram-sdk==7.12.0` raw client); response `metadata.duration`, `results.channels[0].detected_language`, `results.channels[0].alternatives[0].words[{word,start,end,confidence,punctuated_word?}]`, `results.utterances[{start,end,transcript,words}]` | n/a |
| treg CLI | `treg 0.22.0`; `treg call <id> --method POST --data '<json>'` or `--query k=v`; `treg review CALL_ID {useful,partly,not_useful,not_sure} [--reason]`; `treg balance --json`; no `whoami` | issue 10, 11 |
| treg endpoints (catalog, 2026-10-09) | see the table in Package M3-A; all AnyAPI bodies are `{"output": {"found": bool, "data": {...}}, "provider", "costUsd", "items", "replayed", "source", "resultId"}`; routed `treg.*` ids return `{output, raw, _treg: {served_by, tried}}` | 8.3 |
| node / deno here | node v25.4.0, deno absent, ffmpeg 8.0.1 (Homebrew) | n/a |
| `claude -p` isolation | `--setting-sources project` limits settings sources; `--bare` needs `ANTHROPIC_API_KEY` (not usable on the subscription); `--disable-slash-commands` disables all skills | S2 acceptance (M2) |

## Global Constraints

Everything in the M0-M1 plan's Global Constraints, plus:

- yt-dlp is imported only in `src/skipwatch/providers/content_free.py` (and in `scripts/`). `requests` is imported only under `src/skipwatch/providers/`. `test_arch.py` already enforces both.
- `js_runtimes` is always passed explicitly (issue 2); `remote_components` is never set; `cookiesfrombrowser` is set only from the `--cookies-from-browser` flag, and then `fetched_with_cookies` is `true` in `ingest.json` and the manifest (R-ING-5).
- Downloads: short side in [720, 1080], smallest file (R-ING-4, issue 3). Audio for transcription: `media/audio-16k.wav` (16 kHz mono PCM s16le).
- Link fetch: plain GET, 20 000 character cap per link after HTML to text, 10 s timeout, at most 5 links per post, `http` and `https` only, no cookies, default `requests` User-Agent.
- Cloud backends only when `--backend openai|groq|deepgram` is given explicitly (R-TR-2); keys only from `OPENAI_API_KEY`, `GROQ_API_KEY`, `DEEPGRAM_API_KEY`; keys never logged or written.
- treg: subprocess only (`treg` on PATH), cost cap from config (issue 9), every used call followed by `treg review` (R-ING-3), every call appended to `calls.json` and `ingest.json` `provider_calls`.
- Recorded fixtures under `tests/fixtures/recorded/` are scrubbed by `scripts/scrub_fixture.py`: no cookies, no `http_headers`, no signed CDN query strings (`?` and after replaced by `?SCRUBBED`), no `formats[].url` beyond host, no account ids of the operator; creator handles of the public post stay (they are attribution data).
- Pytest markers: `pipeline` (needs ffmpeg and fixtures), `whisper` (needs a Whisper backend importable), `live` (real network; excluded by default via `addopts = "-m 'not live'"`, never run in CI).
- No em dash character (U+2014) in any file; tests that need one build it from the escape `"\u2014"`.

## Review Focus

Five conditions the spec implies but no task's main tests exercise; each has a pinned test in the owning task.

1. **Vertical video format choice** (TikTok, Reels, Shorts at 1080x1920). Expected: the 1080x1920 or 720x1280 rendition is chosen, not 576x1024 and not a 4K one. Pinned: `test_r_ing_4_vertical_uses_short_side` (Task M2-B2).
2. **A YouTube video with only auto captions in a non-English original language plus 150 machine translations.** Expected: the original-language `-orig` track is chosen (or English when the source is English), not `ab`, not a translation. Pinned: `test_caption_choice_prefers_manual_then_orig` (Task M2-B3).
3. **A run killed mid-download or mid-frames, then resumed.** Expected: `resume` names the killed stage (status `running`), partial frames do not survive, the run completes. Pinned: `test_resume_after_killed_frames_completes` (Task M2-H1) and `test_running_stage_counts_as_incomplete` (Task M2-E2).
4. **A post whose links include huge pages, binary files or redirects to localhost.** Expected: each link capped at 20 000 characters, non-text content types skipped, private and loopback hosts never fetched. Pinned: `test_links_skip_private_hosts_and_binary` (Task M3-B1).
5. **treg returning `found: false`, malformed JSON, or exceeding the cost cap.** Expected: fall to the next route, record the reason in `route.fallbacks`, never crash, never exceed `max_cost_usd`. Pinned: `test_treg_not_found_and_bad_json_fall_through`, `test_treg_cost_cap_stops_calls` (Task M4-A1).

---

## Work packages

| Package | Branch | Owns (exclusive) | Depends on | Parallel with |
|---|---|---|---|---|
| **M2-A Foundation amendment** | `m2/foundation-amend` | `src/skipwatch/models.py`, `schemas/*.json`, `tests/unit/test_models.py`, `pyproject.toml`, `uv.lock`, `src/skipwatch/adapters/registry.py` (new), `src/skipwatch/providers/registry.py` (new), and the edits listed in Task M2-A3 to `src/skipwatch/ingest.py`, `src/skipwatch/transcribe.py`, `src/skipwatch/providers/base.py`, `src/skipwatch/adapters/base.py`, `src/skipwatch/adapters/localfile.py`, `src/skipwatch/providers/transcribe_captions.py` (ownership of these six transfers from M1-B), `scripts/scrub_fixture.py`, `tests/unit/test_registry.py`, `tests/unit/test_scrub.py` | M1 merged | nothing (lands first) |
| **M2-B Free provider, YouTube, generic, probe** | `m2/youtube-generic` | `src/skipwatch/providers/content_free.py`, `src/skipwatch/adapters/ytdlp_common.py`, `src/skipwatch/adapters/youtube.py`, `src/skipwatch/adapters/generic.py`, `src/skipwatch/captions_json3.py`, `src/skipwatch/captions.py` (one dispatch line; ownership transfers from M1-B), `src/skipwatch/probe.py`, `src/skipwatch/commands/probe.py`, `scripts/record_fixture.py`, `tests/fixtures/recorded/youtube/`, `tests/fixtures/recorded/generic/`, `tests/unit/test_content_free.py`, `tests/unit/test_format_select.py`, `tests/unit/test_captions_json3.py`, `tests/unit/test_adapter_youtube.py`, `tests/unit/test_adapter_generic.py`, `tests/unit/test_probe.py`, `tests/live/test_live_youtube.py` | M2-A | M2-C, M2-D, M2-E, M2-F |
| **M2-C Local Whisper** | `m2/whisper` | `src/skipwatch/audio.py`, `src/skipwatch/providers/transcribe_faster.py`, `src/skipwatch/providers/transcribe_mlx.py`, `tests/unit/test_audio.py`, `tests/unit/test_transcribe_whisper.py`, `tests/pipeline/test_whisper_pipeline.py` | M2-A | M2-B, D, E, F |
| **M2-D Cloud backends** | `m2/cloud` | `src/skipwatch/providers/transcribe_cloud.py`, `tests/fixtures/recorded/cloud/`, `tests/unit/test_transcribe_cloud.py`, `tests/live/test_live_cloud.py` | M2-A (imports `audio.extract_audio` from M2-C; see interface note) | M2-B, C, E, F |
| **M2-E Cache and resume** | `m2/cache-resume` | `src/skipwatch/runcache.py`, `src/skipwatch/resume.py`, `src/skipwatch/commands/resume.py`, edits to `src/skipwatch/ingest.py` and `src/skipwatch/transcribe.py` (cache hooks only; ownership transfers from M2-A after it merges), `tests/unit/test_runcache.py`, `tests/unit/test_resume.py` | M2-A merged | M2-B, C, D, F |
| **M2-F Golden set** | `m2/golden` | `tests/golden/golden.json`, `tests/golden/README.md`, `scripts/golden_check.py`, `scripts/golden_run.py`, `tests/unit/test_golden_file.py` | M2-A | M2-B..E |
| **M2-G Orchestrator M2** | `m2/orchestrator` | `skills/skipwatch/SKILL.md`, `skills/skipwatch/references/run-protocol.md`, `skills/skipwatch/references/review-screen.md`, `tests/unit/test_orchestrator_files.py` (ownership transfers from M1-F) | M2-A | M2-B..F |
| **M2-H Pipeline and acceptance** | `m2/pipeline` | `tests/pipeline/test_resume_pipeline.py`, `.github/workflows/ci.yml` (adds `-m "not live"` guard and the whisper job; ownership from M1-G) | M2-A..G merged | none |
| **M3-A Spike** | `m3/spike` | `skills/skipwatch/references/platforms.md` (ownership from M1-F for all of M3 and M4), `tests/fixtures/recorded/{x,tiktok,instagram,facebook,text}/`, `tests/fixtures/recorded/treg/`, `docs/spikes/2026-10-m3-spike.md` | M2 merged | nothing (first in M3) |
| **M3-B X, text, links** | `m3/x-text` | `src/skipwatch/adapters/x.py`, `src/skipwatch/adapters/text.py`, `src/skipwatch/providers/links.py`, `src/skipwatch/htmltext.py`, `tests/unit/test_adapter_x.py`, `tests/unit/test_adapter_text.py`, `tests/unit/test_links.py` | M3-A merged | M3-C, M3-D |
| **M3-C TikTok, Instagram, Facebook** | `m3/tiktok-ig-fb` | `src/skipwatch/adapters/tiktok.py`, `src/skipwatch/adapters/instagram.py`, `src/skipwatch/adapters/facebook.py`, `tests/unit/test_adapter_social.py`, `tests/live/test_live_social.py` | M3-A merged | M3-B, M3-D |
| **M3-D Orchestrator M3** | `m3/orchestrator` | `skills/skipwatch/SKILL.md`, `skills/skipwatch/references/run-protocol.md`, `tests/unit/test_orchestrator_files.py` | M3-A merged | M3-B, M3-C |
| **M4-A treg provider** | `m4/treg` | `src/skipwatch/providers/content_treg.py`, `src/skipwatch/doctor.py` (login detection; ownership from M0-C), `tests/unit/test_content_treg.py`, `tests/unit/test_doctor_treg.py`, `tests/live/test_live_treg.py` | M3 merged | M4-B, M4-C |
| **M4-B Cross-check** | `m4/crosscheck` | `src/skipwatch/crosscheck.py`, edit to `src/skipwatch/transcribe.py` (cross-check hook; ownership from M2-E), `tests/unit/test_crosscheck.py` | M3 merged | M4-A, M4-C |
| **M4-C Orchestrator M4** | `m4/orchestrator` | `skills/skipwatch/SKILL.md`, `skills/skipwatch/references/run-protocol.md`, `skills/skipwatch/references/review-screen.md`, `skills/skipwatch/references/platforms.md`, `tests/unit/test_orchestrator_files.py` | M3 merged | M4-A, M4-B |

**Order and parallelism**

1. **M2-A** alone. Merge.
2. **M2-B, M2-C, M2-D, M2-E, M2-F, M2-G in parallel.** Merge order: C before D (D imports `audio.extract_audio`; D develops against the signature below with `pytest.importorskip("skipwatch.audio")` until C lands), then B, E, F, G in any order.
3. **M2-H**, then the M2 acceptance runs (orchestrator triggers the paid ones).
4. **M3-A** (spike, live, cost-capped). Merge.
5. **M3-B, M3-C, M3-D in parallel.** Merge. M3 acceptance.
6. **M4-A, M4-B, M4-C in parallel.** Merge. M4 acceptance.

**Registration points (no two packages edit one file)**

- **Commands:** new files in `src/skipwatch/commands/` only (`probe.py`, `resume.py`); `cli.py` auto-registers them (M0-A).
- **Adapters:** `adapters/registry.py` (M2-A) imports every module in `skipwatch.adapters` that defines `PLATFORMS: tuple[str, ...]` and `ADAPTER: Adapter`. New platforms are new files.
- **Content providers:** `providers/registry.py` (M2-A) imports every `providers/content_*.py` except `content_free` that defines `PROVIDER: ContentProvider`. treg (M4-A) is a new file.
- **Transcription backends:** `providers/registry.py` imports every `providers/transcribe_*.py` that defines `BACKENDS: tuple[TranscriptionBackend, ...]`. Whisper and cloud are new files.
- **Models:** only M2-A. **pyproject.toml:** only M2-A.
- **Shared, sequential files:** `ingest.py` and `transcribe.py` (M1-B, then M2-A, then M2-E, then M4-B for `transcribe.py`); `SKILL.md`, `run-protocol.md`, `test_orchestrator_files.py` (M2-G, then M3-D, then M4-C); `platforms.md` (M3-A, then M4-C); `ci.yml` (M2-H only).

---
# MILESTONE M2: YouTube and generic

## Package M2-A: Foundation amendment (`m2/foundation-amend`)

### Task M2-A1: Model amendments (every model change M2 to M4 needs)

**Files:**
- Modify: `src/skipwatch/models.py`
- Regenerate: `schemas/*.json` via `uv run python scripts/export_schemas.py`
- Modify: `tests/unit/test_models.py`

**Interfaces (exact names; later packages import, never edit):**

| Model | Change | Used by |
|---|---|---|
| `IngestContext` | add `captions_lang: str \| None = None`, `captions_kind: Literal["manual", "auto"] \| None = None` | M2-B, M3 |
| `ProviderCall` | add `endpoint: str \| None = None`, `call_id: str \| None = None`, `review: Literal["useful", "partly", "not_useful", "not_sure"] \| None = None`, `error: str \| None = None` | M4-A (calls.json, review screen) |
| `IngestBundle` | add `from_cache: bool = False` | M2-E, review screen |
| `TregConfig` | add `max_cost_usd: float = Field(default=0.05, ge=0)` | M4-A (issue 9) |
| new `ProbeResult(_Tagged)` | `schema_: Literal["skipwatch/probe/1"]`; `value: str`; `kind: Literal["video", "audio", "text", "file", "unknown"]`; `platform: str`; `title: str \| None = None`; `author: str \| None = None`; `duration_s: float \| None = None`; `captions_available: bool = False`; `long_video: bool = False`; `estimated_run_s: int \| None = None` | M2-B, M2-G |
| new `RunFile(_Tagged)` | `schema_: Literal["skipwatch/run/1"]`; `input: str`; `flags: list[str] = []`; `name: str \| None = None`; `started_at: str` | M2-E, M2-G |
| new `ResumeResult(_Tagged)` | `schema_: Literal["skipwatch/resume/1"]`; `work: str`; `next_stage: StageName \| None`; `completed: list[StageName] = []`; `run: RunFile \| None = None`; `media_present: bool = False` | M2-E, M2-G |
| new `CacheEntry(_Tagged)` | `schema_: Literal["skipwatch/cache-entry/1"]`; `key: str`; `source: str`; `created_at: str`; `files: list[str] = []` | M2-E |
| `SCHEMA_MODELS` | add `"probe": ProbeResult`, `"run": RunFile`, `"resume": ResumeResult`, `"cache-entry": CacheEntry` | test_schemas |

No other model changes are needed for M2 to M4: `TranscriptHint`, `CrossCheck`, `Route.fallbacks`, `LinkContext` (20k cap), `SourceInfo` and `CallsFile` already carry every field the spec's 7.1 and 7.2 examples show.

- [ ] **Step 1: Branch**

```bash
cd ~/Projects/SkipWatch
git fetch origin && git worktree add .worktrees/m2-foundation-amend -b m2/foundation-amend origin/main
cd .worktrees/m2-foundation-amend && uv sync --dev
```

- [ ] **Step 2: Write failing tests** (append to `tests/unit/test_models.py`; update the registry test's expected set)

```python
from skipwatch.models import (
    CacheEntry, Config, IngestBundle, ProbeResult, ProviderCall, ResumeResult, RunFile,
)


def test_r_arch_2_registry_covers_every_work_file():
    expected = {"ingest", "transcript", "frames", "batches", "notes", "check", "manifest",
                "stages", "source", "calls", "critique", "doctor", "cache", "install", "config",
                "probe", "run", "resume", "cache-entry"}
    assert set(SCHEMA_MODELS) == expected


def test_provider_call_carries_review_fields():
    c = ProviderCall(provider="treg", op="x.thread", ok=True, cost_usd=0.00375, ms=900,
                     endpoint="anyapi.twitter.thread", call_id="abc", review="useful")
    assert c.review == "useful"
    with pytest.raises(ValidationError):
        ProviderCall(provider="treg", op="x", ok=True, review="great")


def test_ingest_example_still_round_trips_with_new_defaults():
    bundle = IngestBundle.model_validate(INGEST_EXAMPLE)
    assert bundle.from_cache is False and bundle.context.captions_kind is None


def test_treg_cost_cap_default_and_bounds():
    assert Config().providers.treg.max_cost_usd == 0.05
    with pytest.raises(ValidationError):
        Config.model_validate({"providers": {"treg": {"max_cost_usd": -1.0}}})


def test_probe_and_resume_require_schema_tag_on_read():
    with pytest.raises(ValidationError):
        ProbeResult.model_validate({"value": "u", "kind": "video", "platform": "youtube"})
    r = ResumeResult(work="/w", next_stage="frames", completed=["detect", "ingest", "transcribe"],
                     run=RunFile(input="https://youtu.be/x", flags=["--thorough"], started_at="2026-10-09T18:00:00Z"))
    assert ResumeResult.model_validate_json(r.model_dump_json(by_alias=True)) == r


def test_cache_entry_round_trip():
    e = CacheEntry(key="0123456789abcdef", source="https://youtu.be/x",
                   created_at="2026-10-09T18:00:00Z", files=["ingest.json"])
    assert CacheEntry.model_validate_json(e.model_dump_json(by_alias=True)) == e
```

Note: `INGEST_EXAMPLE` from the spec omits `from_cache`, `captions_lang` and `captions_kind`, so the existing round-trip test (`json.loads(dump) == INGEST_EXAMPLE`) would now fail on the extra defaults. Change that test to dump with `exclude_defaults=False` and compare the spec keys only: `assert {k: dumped[k] for k in INGEST_EXAMPLE} == INGEST_EXAMPLE` after removing the three new keys from nested `context` and top level. Write the new comparison explicitly in the test.

- [ ] **Step 3: Run, expect FAIL** `uv run pytest tests/unit/test_models.py -v` (ImportError on `ProbeResult`).

- [ ] **Step 4: Implement** the table above in `models.py` (place new classes in the "command --json outputs" and "other work-folder files" sections; `ProbeResult`, `ResumeResult` with outputs, `RunFile`, `CacheEntry` with work-folder files). Then regenerate schemas:

```bash
uv run python scripts/export_schemas.py && uv run python scripts/export_schemas.py --check
```
Expected: `--check` prints nothing and exits 0; `git status` shows four new files `schemas/{probe,run,resume,cache-entry}.schema.json` and modified `ingest`, `calls`, `config` schemas.

- [ ] **Step 5: Run, expect PASS** `uv run pytest tests/unit -v` (all pass, including `test_schemas.py`).

- [ ] **Step 6: Commit** `git add src/skipwatch/models.py schemas tests/unit/test_models.py && git commit -m "M2-A: model amendments for M2-M4 (probe, run, resume, cache entry, provider call review, treg cost cap)"`

### Task M2-A2: Dependencies, markers, scrubber

**Files:** Modify `pyproject.toml`, `uv.lock`; Create `scripts/scrub_fixture.py`, `tests/unit/test_scrub.py`

- [ ] **Step 1: pyproject changes** (exact):

```toml
dependencies = [
  "typer>=0.27,<0.28",
  "pydantic>=2.14,<3",
  "pyyaml>=6.0",
  "pillow>=12.0",
  "static-ffmpeg>=3.0",
  "yt-dlp[default]>=2026.8.19",
  "requests>=2.32.2,<3",
]

[project.optional-dependencies]
whisper = ["faster-whisper>=1.2"]
mlx = ["mlx-whisper>=0.4.3; sys_platform == 'darwin' and platform_machine == 'arm64'"]

[tool.pytest.ini_options]
testpaths = ["tests/unit", "tests/pipeline", "tests/live"]
addopts = "-m 'not live'"
markers = [
  "pipeline: needs ffmpeg and the committed fixture video",
  "whisper: needs faster-whisper or mlx-whisper importable",
  "live: real network; never in CI; run only when the orchestrator says so",
]
```

Run `uv lock && uv sync --dev`. Expected: `uv.lock` gains `yt-dlp-ejs 0.8.0` and `requests`. Verify: `uv run python -c "import yt_dlp_ejs, requests; print('ok')"` prints `ok`.

- [ ] **Step 2: Failing scrub tests** `tests/unit/test_scrub.py`

```python
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "scrub_fixture.py"


def run(tmp_path, data):
    p = tmp_path / "in.json"; p.write_text(json.dumps(data))
    out = tmp_path / "out.json"
    subprocess.run([sys.executable, str(SCRIPT), str(p), "-o", str(out)], check=True)
    return json.loads(out.read_text())


def test_scrub_removes_cookies_headers_and_signed_queries(tmp_path):
    data = {"http_headers": {"Cookie": "a=b"}, "cookies": "x", "uploader": "@creator",
            "formats": [{"format_id": "18", "url": "https://rr1.googlevideo.com/videoplayback?sig=SECRET&ip=1.2.3.4",
                         "height": 360, "width": 640, "filesize": 10}],
            "thumbnail": "https://i.ytimg.com/vi/x/hq.jpg?sqp=SIGNED"}
    out = run(tmp_path, data)
    text = json.dumps(out)
    assert "SECRET" not in text and "1.2.3.4" not in text and "SIGNED" not in text
    assert "Cookie" not in text and "cookies" not in out
    assert out["formats"][0]["url"] == "https://rr1.googlevideo.com/videoplayback?SCRUBBED"
    assert out["uploader"] == "@creator"  # attribution data stays


def test_scrub_is_idempotent(tmp_path):
    data = {"formats": [{"url": "https://a.example/v?x=1"}]}
    once = run(tmp_path, data)
    assert run(tmp_path, once) == once
```

- [ ] **Step 3: FAIL, then implement** `scripts/scrub_fixture.py`: `scrub(obj) -> obj` recursively: drop keys `http_headers`, `cookies`, `_cookies`, `__x_forwarded_for_ip`, `requested_subtitles` (contains signed URLs), and any key whose name contains `token` or `session`; for every string value that starts with `http` and contains `?`, replace from `?` onward with `?SCRUBBED`; strip IPv4 literals anywhere in strings (`\b\d{1,3}(\.\d{1,3}){3}\b` to `0.0.0.0`). CLI: `scrub_fixture.py IN -o OUT` (json in, json out, `indent=2`, `sort_keys=True`). Also usable as `from scrub_fixture import scrub` by `scripts/record_fixture.py` (M2-B), which adds `scripts/` to `sys.path`.
- [ ] **Step 4: PASS** `uv run pytest tests/unit/test_scrub.py -v` (2 passed).
- [ ] **Step 5: Commit** `git commit -am "M2-A: yt-dlp default extra, requests, live and whisper markers, fixture scrubber"` (add the new files explicitly).

### Task M2-A3: Registries for adapters, content providers and transcription backends

**Files:**
- Create: `src/skipwatch/adapters/registry.py`, `src/skipwatch/providers/registry.py`, `tests/unit/test_registry.py`
- Modify: `src/skipwatch/adapters/base.py` (add `NoMediaError`, `DownloadFailed`), `src/skipwatch/adapters/localfile.py` (add `PLATFORMS`, `ADAPTER`), `src/skipwatch/providers/base.py` (exact protocol signatures below), `src/skipwatch/providers/transcribe_captions.py` (add `BACKENDS`), `src/skipwatch/ingest.py` (dispatch through the registry, provider enrichment, media fallback), `src/skipwatch/transcribe.py` (`select_backend` through the registry; explicit-only cloud rule)

**Interfaces:**
- Produces in `adapters/base.py`:

```python
class NoMediaError(Exception):
    """The URL resolved but has no video or audio. ingest may retry it as a text source."""
    def __init__(self, url: str, reason: str): ...

class DownloadFailed(Exception):
    """Every free route failed for media. attempts are 'route.op: reason' strings."""
    def __init__(self, attempts: list[str]): ...
```

- Produces in `providers/base.py` (replace the M1 stubs; `TranscriptionBackend` keeps its M1 shape and gains two attributes):

```python
class ContentProvider(Protocol):
    name: str                                   # "treg"
    def available(self) -> bool: ...            # installed and logged in; may do one cheap check
    def enrich(self, bundle: IngestBundle, work: WorkDir, opts: IngestOptions) -> IngestBundle: ...
    def fetch_media(self, bundle: IngestBundle, work: WorkDir, opts: IngestOptions) -> MediaInfo | None: ...

class TranscriptionBackend(Protocol):
    name: str                                   # "captions" | "mlx" | "faster" | "openai" | "groq" | "deepgram"
    cloud: bool                                 # True only for openai, groq, deepgram
    auto_rank: int | None                       # order under auto: captions 0, mlx 1, faster 2; cloud None
    def available(self, bundle: IngestBundle) -> bool: ...
    def transcribe(self, work: WorkDir, model: str | None) -> Transcript: ...
    def missing_hint(self) -> str: ...          # install command or env var to set, for exit 8
```

- Produces in `adapters/registry.py`: `adapter_for(platform: str) -> Adapter | None`; `all_platforms() -> set[str]`.
- Produces in `providers/registry.py`: `content_providers() -> list[ContentProvider]` (sorted by name); `transcription_backends() -> dict[str, TranscriptionBackend]`.
- Changes in `ingest.py`: `run_ingest(value, work, opts)` becomes:

```python
def build_bundle(value: str, work: WorkDir, opts: IngestOptions, cfg: Config) -> IngestBundle:
    detected = detect(value)
    adapter = adapter_for(detected.platform)
    if adapter is None:
        raise SkipwatchError(ExitCode.UNSUPPORTED_SOURCE, f"no adapter for {detected.platform}")
    providers = enabled_providers(opts, cfg)          # [] for --provider free
    try:
        bundle = adapter.build(detected, work, opts)
    except NoMediaError as exc:
        text = adapter_for("text")
        if text is None:
            raise SkipwatchError(ExitCode.NO_CONTENT, f"{exc.url} has no video: {exc.reason}") from exc
        bundle = text.build(detected, work, opts)
    except DownloadFailed as exc:
        bundle = _media_fallback(detected, work, opts, providers, exc.attempts)   # exit 3 when nothing works
    for provider in providers:
        bundle = provider.enrich(bundle, work, opts)
    return bundle
```

  `enabled_providers(opts, cfg)`: `opts.provider == "free"` gives `[]`; `"treg"` gives the treg provider or raises exit 8 (issue 15); `"auto"` gives every registered provider whose config is not `false` and whose `available()` is true. `_media_fallback` asks each provider's `fetch_media`; if all return `None` it raises `SkipwatchError(DOWNLOAD_FAILED, ...)` whose message lists every attempt and ends with "Try: uv sync --upgrade-package yt-dlp, or --cookies-from-browser <browser>, or the content is private." Adapters that hit a login error raise `SkipwatchError(PRIVATE_CONTENT, ...)` directly (R-ING-6); the dispatcher never catches it.
- Changes in `transcribe.py`: `select_backend(requested, bundle)`: `requested == "auto"`: the available backend with the lowest `auto_rank` (cloud never, R-TR-2); none: exit 8 with the hint of the highest-ranked local backend that is not installed (`--extra mlx` on Apple Silicon, else `--extra whisper`). Explicit `requested`: that backend; unknown name: exit 64 is typer's job, so `SkipwatchError(MISSING_DEPENDENCY, f"backend {requested} is not available: {backend.missing_hint()}")` when `available()` is false. `captions` explicitly requested without captions stays exit 7 (M1 behaviour).

- [ ] **Step 1: Failing tests** `tests/unit/test_registry.py`

```python
import pytest

from skipwatch.adapters.registry import adapter_for, all_platforms
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import IngestBundle, IngestContext, Route, SourceInfo
from skipwatch.providers.registry import transcription_backends
from skipwatch import transcribe


def bundle(captions=False):
    ctx = IngestContext(captions_available=captions, captions_path="captions/a.en.vtt" if captions else None)
    return IngestBundle(source=SourceInfo(kind="file", platform="local", path="/x.mp4"),
                        context=ctx, route=Route(context="local", media="local"))


def test_localfile_registers_itself():
    assert "local" in all_platforms() and adapter_for("local") is not None
    assert adapter_for("nope") is None


def test_captions_backend_registered_with_rank_zero():
    b = transcription_backends()["captions"]
    assert b.auto_rank == 0 and b.cloud is False


def test_r_tr_2_auto_never_picks_a_cloud_backend(monkeypatch):
    class FakeCloud:
        name, cloud, auto_rank = "openai", True, None
        def available(self, bundle): return True
        def missing_hint(self): return "set OPENAI_API_KEY"
    monkeypatch.setattr(transcribe, "transcription_backends",
                        lambda: {"captions": transcription_backends()["captions"], "openai": FakeCloud()})
    with pytest.raises(SkipwatchError) as e:
        transcribe.select_backend("auto", bundle(captions=False))
    assert e.value.code == ExitCode.MISSING_DEPENDENCY
    assert transcribe.select_backend("openai", bundle()).name == "openai"   # explicit is allowed


def test_ingest_url_without_adapter_is_exit_2(tmp_path, monkeypatch):
    from skipwatch.adapters import base
    from skipwatch.adapters.base import IngestOptions
    from skipwatch.config import load_config
    from skipwatch.ingest import build_bundle
    from skipwatch.workdir import WorkDir
    monkeypatch.setattr("skipwatch.ingest.adapter_for", lambda p: None)
    w = WorkDir(tmp_path / "w"); w.ensure()
    with pytest.raises(SkipwatchError) as e:
        build_bundle("https://vimeo.com/1", w, IngestOptions(), load_config(tmp_path / "none.toml"))
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
    w = WorkDir(tmp_path / "w"); w.ensure()
    with pytest.raises(SkipwatchError) as e:
        build_bundle("https://vimeo.com/1", w, IngestOptions(provider="free"), load_config(tmp_path / "n.toml"))
    assert e.value.code == ExitCode.DOWNLOAD_FAILED
    assert "free.yt-dlp.download: HTTP Error 403" in e.value.message and "--cookies-from-browser" in e.value.message


def test_provider_treg_requested_but_missing_is_exit_8(tmp_path, monkeypatch):
    from skipwatch.adapters.base import IngestOptions
    from skipwatch.config import load_config
    from skipwatch.ingest import enabled_providers
    monkeypatch.setattr("skipwatch.ingest.content_providers", lambda: [])
    with pytest.raises(SkipwatchError) as e:
        enabled_providers(IngestOptions(provider="treg"), load_config(tmp_path / "n.toml"))
    assert e.value.code == ExitCode.MISSING_DEPENDENCY
```

- [ ] **Step 2: Run, expect FAIL** `uv run pytest tests/unit/test_registry.py -v`.
- [ ] **Step 3: Implement.** Registries follow the `cli._register_all` pattern (`pkgutil.iter_modules`, sorted, `importlib.import_module`, `getattr(module, "ADAPTER"/"PROVIDER"/"BACKENDS", None)`); `providers/registry.py` skips modules whose name does not start with `content_` or `transcribe_`, and skips `content_free` (a library, not a provider). An import error in a backend module (for example `faster_whisper` missing) must not break the registry: backend modules import heavy libraries lazily inside `transcribe()`. `localfile.py` gains `PLATFORMS = ("local",)` and `ADAPTER = LocalFileAdapter()`. `transcribe_captions.py` gains `cloud = False`, `auto_rank = 0`, `missing_hint()` returning `"no captions sidecar or platform captions"`, and `BACKENDS = (CaptionsBackend(),)`; its `available` takes the bundle (M1 read `ingest.json` itself; keep that path working by passing the loaded bundle).
- [ ] **Step 4: PASS** `uv run pytest tests/unit -v` (all M1 tests still pass: the M1 tests `test_url_in_m1_is_exit_2` and `test_cloud_backend_not_available_in_m1` are now wrong by design; replace them in `test_ingest_local.py` / `test_transcribe.py` with `test_url_without_network_adapter_is_exit_2` (monkeypatched registry) and `test_cloud_backend_without_key_is_exit_8`; ownership of those two test files moves to M2-A for this edit only).
- [ ] **Step 5: Lint, types, commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pyright
git add -A src tests && git commit -m "M2-A: adapter, content provider and transcription backend registries (R-TR-2 auto rule)"
git push -u origin m2/foundation-amend
```
Expected: `All checks passed!`, `0 errors`. Tell the orchestrator the branch is ready.

---

## Package M2-B: Free content provider, YouTube, generic, probe (`m2/youtube-generic`)

### Task M2-B1: Fixture recorder (live, run once per platform)

**Files:** Create `scripts/record_fixture.py`, `tests/fixtures/recorded/youtube/`, `tests/fixtures/recorded/generic/`

**Interfaces:** `uv run python scripts/record_fixture.py <url> --name <slug> --platform <dir> [--captions]` runs `YoutubeDL({"quiet": True, "skip_download": True, "noplaylist": True, "js_runtimes": <per issue 2>}).extract_info(url, download=False)`, passes `YoutubeDL.sanitize_info(info)` through `scrub_fixture.scrub`, keeps only the keys adapters read (`id, title, uploader, uploader_id, channel, upload_date, timestamp, duration, webpage_url, extractor_key, description, formats[format_id,ext,width,height,filesize,filesize_approx,tbr,vcodec,acodec,url], subtitles{lang:[{ext,url}]}, automatic_captions{lang:[{ext,url}]}, language, is_live, availability, age_limit`), and writes `tests/fixtures/recorded/<platform>/<slug>.info.json`. With `--captions` it also downloads the chosen caption file (json3 when available, else vtt) to `<slug>.<lang>.<ext>`. It never passes cookies.

- [ ] **Step 1:** Write the script. **Step 2 (live, allowed in this package):** record three fixtures and commit them:
  - `youtube/manual-captions` from the G1 candidate list in M2-F (or any public CLI tutorial with manual English captions),
  - `youtube/auto-only-nonenglish` (a public video whose only captions are automatic in a non-English original language; Review Focus 2),
  - `generic/vimeo-public` (a public Vimeo video, no captions),
  plus one handmade `youtube/vertical-short.info.json` built from the manual one by replacing `formats` with the vertical list in Task M2-B2's test (document this in a comment field `"_handmade": true`).
- [ ] **Step 3:** `grep -rE "sig=|Cookie|[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}" tests/fixtures/recorded | grep -v 0.0.0.0` prints nothing.
- [ ] **Step 4: Commit** `git commit -m "M2-B: scrubbed recorded yt-dlp fixtures for YouTube and generic"`

### Task M2-B2: `content_free`: yt-dlp params, format choice, error mapping (R-ING-4, R-ING-5, R-ING-6)

**Files:** Create `src/skipwatch/providers/content_free.py`; Tests `tests/unit/test_format_select.py`, `tests/unit/test_content_free.py`

**Interfaces (produced; M3 adapters use them too):**
- `js_runtime() -> dict[str, dict[str, str]]`: `{"node": {"path": p}}` when `shutil.which("node")` reports `v22` or later (`node --version`), else `{"deno": {"path": p}}` when deno is found, else `{}`.
- `ydl_params(work: Path | None, opts: IngestOptions, *, download: bool) -> dict`: always `quiet=True`, `no_warnings=True`, `noplaylist=True`, `socket_timeout=30`, `retries=3`, `js_runtimes=js_runtime()`, `logger=_Quiet()`; when `opts.cookies_from_browser`: `cookiesfrombrowser=(opts.cookies_from_browser,)`; when `download`: `paths={"home": str(work / "media")}`, `outtmpl="video.%(ext)s"`, `merge_output_format="mp4"`, `ffmpeg_location=str(media.ffmpeg_paths()[0].parent)`, `overwrites=True`. Never `remote_components`.
- `select_format(info: dict, max_short_side: int = 1080) -> str` (issue 3): returns a yt-dlp format spec: a single progressive id (`"18"`), or `"<video_id>+<audio_id>"` with the smallest audio-only format by size; raises `SkipwatchError(NO_CONTENT, ...)` when `info` has no video or audio formats.
- `extract(url: str, opts: IngestOptions) -> dict` (metadata only; returns the sanitized info dict).
- `download(info: dict, work: WorkDir, opts: IngestOptions) -> MediaInfo`: picks `select_format(info, opts.max_height)` and calls `process_ie_result(info, download=True)` with `format=<spec>`; probes the file with `media.probe`; returns `MediaInfo(path="media/video.mp4", ...)` (work-relative).
- `download_captions(info: dict, work: WorkDir, opts: IngestOptions) -> tuple[str, str, Literal["manual","auto"]] | None`: chooses the track (Task M2-B3), downloads it with `writesubtitles`/`writeautomaticsub`, `subtitlesformat="json3/vtt/best"`, `subtitleslangs=[lang]`, `skip_download=True` into `work/captions/`, returns `(work-relative path, lang, kind)`.
- `classify_error(message: str) -> ExitCode`: `PRIVATE_CONTENT` when the message contains `--cookies` or (case-insensitive) `private video`, `protected tweet`, `requires authentication`, `log in to access`, `login required`; `NO_CONTENT` for `No video could be found` or `There's no video in this`; otherwise `DOWNLOAD_FAILED`.
- `call_log(op: str, ok: bool, started: float) -> ProviderCall` with `provider="free"`, `cost_usd=0`.

- [ ] **Step 1: Failing format tests** `tests/unit/test_format_select.py`

```python
from skipwatch.providers.content_free import select_format


def f(fid, w, h, size, v="avc1", a="none", tbr=None):
    return {"format_id": fid, "width": w, "height": h, "filesize": size, "vcodec": v, "acodec": a, "tbr": tbr}


AUDIO = [{"format_id": "140", "vcodec": "none", "acodec": "mp4a", "filesize": 3_000_000},
         {"format_id": "251", "vcodec": "none", "acodec": "opus", "filesize": 2_500_000}]


def test_r_ing_4_smallest_at_or_above_720_capped_at_1080():
    info = {"duration": 600, "formats": [f("160", 256, 144, 1e6), f("136", 1280, 720, 40e6), f("398", 1280, 720, 30e6),
                                         f("137", 1920, 1080, 90e6), f("401", 3840, 2160, 400e6)] + AUDIO}
    assert select_format(info) == "398+251"


def test_r_ing_4_vertical_uses_short_side():
    info = {"duration": 30, "formats": [f("a", 576, 1024, 4e6), f("b", 720, 1280, 6e6), f("c", 1080, 1920, 9e6),
                                        f("d", 2160, 3840, 40e6)] + AUDIO}
    assert select_format(info).startswith("b+")


def test_r_ing_4_below_720_takes_the_largest_available():
    info = {"duration": 30, "formats": [f("s", 320, 240, 1e6, a="mp4a"), f("m", 640, 480, 2e6, a="mp4a")]}
    assert select_format(info) == "m"


def test_unknown_sizes_fall_back_to_bitrate_times_duration():
    info = {"duration": 100, "formats": [f("x", 1280, 720, None, a="mp4a", tbr=3000), f("y", 1920, 1080, None, a="mp4a", tbr=1500)]}
    assert select_format(info) == "y"
```

- [ ] **Step 2: Failing provider tests** `tests/unit/test_content_free.py` (no network: `yt_dlp.YoutubeDL` is monkeypatched with a fake whose `extract_info` returns a recorded fixture or raises `DownloadError`)

```python
import json
from pathlib import Path

import pytest

from skipwatch.adapters.base import IngestOptions
from skipwatch.errors import ExitCode
from skipwatch.providers import content_free as cf

REC = Path(__file__).resolve().parents[1] / "fixtures" / "recorded"


def test_r_ing_5_node_22_is_passed_explicitly(monkeypatch):
    monkeypatch.setattr(cf.shutil, "which", lambda n: "/usr/bin/node" if n == "node" else None)
    monkeypatch.setattr(cf, "_version_of", lambda path: "v25.4.0")
    assert cf.js_runtime() == {"node": {"path": "/usr/bin/node"}}


def test_r_ing_5_old_node_and_no_deno_means_no_runtime(monkeypatch):
    monkeypatch.setattr(cf.shutil, "which", lambda n: "/usr/bin/node" if n == "node" else None)
    monkeypatch.setattr(cf, "_version_of", lambda path: "v20.11.0")
    assert cf.js_runtime() == {}  # explicit empty dict: yt-dlp would otherwise default to deno


def test_r_ing_5_cookies_only_from_the_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(cf, "js_runtime", lambda: {})
    assert "cookiesfrombrowser" not in cf.ydl_params(tmp_path, IngestOptions(), download=False)
    p = cf.ydl_params(tmp_path, IngestOptions(cookies_from_browser="firefox"), download=False)
    assert p["cookiesfrombrowser"] == ("firefox",)
    assert "remote_components" not in p


@pytest.mark.parametrize("msg,code", [
    ("ERROR: [youtube] x: Private video. Sign in if you've been granted access to this video. Use --cookies-from-browser or --cookies for the authentication.", ExitCode.PRIVATE_CONTENT),
    ("ERROR: [twitter] 1: You are not authorized to view this protected tweet. Use --cookies, --cookies-from-browser, ...", ExitCode.PRIVATE_CONTENT),
    ("ERROR: [Instagram] abc: Requested content is not available, rate-limit reached or login required. Use --cookies-from-browser or --cookies for the authentication.", ExitCode.PRIVATE_CONTENT),
    ("ERROR: [twitter] 1: No video could be found in this tweet", ExitCode.NO_CONTENT),
    ("ERROR: unable to download video data: HTTP Error 403: Forbidden", ExitCode.DOWNLOAD_FAILED),
])
def test_r_ing_6_error_classification(msg, code):
    assert cf.classify_error(msg) == code
```

- [ ] **Step 3: FAIL, implement, PASS.** `_version_of(path)` runs `[path, "--version"]` with `timeout=10`; parse `v?(\d+)`. Download path: `process_ie_result` writes `media/video.mp4`; R-CLI-1: when `media/video.mp4` exists and its probe duration matches `info["duration"]` within 1 s, skip the download.
- [ ] **Step 4: Commit** `git commit -m "M2-B: free content provider: yt-dlp params, format choice, error classes (R-ING-4..6)"`

### Task M2-B3: YouTube and generic adapters, json3 captions

**Files:** Create `src/skipwatch/captions_json3.py`, `src/skipwatch/adapters/ytdlp_common.py`, `src/skipwatch/adapters/youtube.py`, `src/skipwatch/adapters/generic.py`; Modify `src/skipwatch/captions.py` (one line in `parse_file`: `.json3` goes to `captions_json3.parse_json3`); Tests `tests/unit/test_captions_json3.py`, `tests/unit/test_adapter_youtube.py`, `tests/unit/test_adapter_generic.py`

**Interfaces:**
- `captions_json3.parse_json3(text: str) -> list[Segment]`: events with `segs`; `start = tStartMs/1000`, `end = (tStartMs + dDurationMs)/1000`; text = joined `segs[].utf8` with newlines turned into spaces, stripped; words from `segs` with `tOffsetMs` when more than one seg (`s = (tStartMs + tOffsetMs)/1000`, `e` = next word start or segment end); drop events whose text is empty or only `\n` (YouTube "append" events); merge rolling duplicates like `parse_vtt`.
- `ytdlp_common.choose_caption_track(info: dict, prefer: str = "en") -> tuple[str, Literal["manual","auto"]] | None`: manual `subtitles` first (skip `live_chat`): a language starting with `prefer`, else `info["language"]`, else the first; then `automatic_captions`: `f"{info['language']}-orig"` when present, then `prefer`, then `info['language']`; never a translation otherwise. Returns `None` when nothing matches.
- `ytdlp_common.build_video_bundle(detected, work, opts, platform: str, info: dict) -> IngestBundle`: fills `SourceInfo(kind="video" or "audio" when no format has a video codec, platform, url=detected.value, canonical_url=info["webpage_url"], author="@"+uploader_id when present else uploader, author_name=uploader or channel, title, posted_at=ISO from timestamp or upload_date, duration_s=duration)`, `context.post_text=info.get("description")` (full, never truncated, R-ING-1), downloads captions and media through `content_free`, records each op in `provider_calls` and the route (`Route(context="free", media="free")`), sets `fetched_with_cookies = opts.cookies_from_browser is not None`. A `DownloadError` is mapped with `classify_error`: `PRIVATE_CONTENT` raises `SkipwatchError(4, "<platform> says this needs a login. Re-run with --cookies-from-browser <browser> if you can see it in that browser.")`; `NO_CONTENT` raises `NoMediaError`; anything else raises `DownloadFailed(["free.yt-dlp.<op>: <first line of message>"])`.
- `youtube.py`: `PLATFORMS = ("youtube",)`, `ADAPTER = YoutubeAdapter()`; `generic.py`: `PLATFORMS = ("generic",)`, `ADAPTER = GenericAdapter()`; generic raises `NoMediaError` when yt-dlp reports `Unsupported URL` or the info has no formats (so text pages reach the M3 text adapter).

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_captions_json3.py
from skipwatch.captions_json3 import parse_json3

JSON3 = '''{"events": [
 {"tStartMs": 0, "dDurationMs": 4000, "segs": [{"utf8": "first"}, {"utf8": " type", "tOffsetMs": 600}, {"utf8": " this", "tOffsetMs": 1100}]},
 {"tStartMs": 2000, "dDurationMs": 10, "aAppend": 1, "segs": [{"utf8": "\\n"}]},
 {"tStartMs": 4000, "dDurationMs": 2000, "segs": [{"utf8": "run it"}]}]}'''


def test_json3_segments_and_word_timings():
    segs = parse_json3(JSON3)
    assert [(s.start, s.end, s.text) for s in segs] == [(0.0, 4.0, "first type this"), (4.0, 6.0, "run it")]
    assert [(w.w, w.s) for w in segs[0].words] == [("first", 0.0), ("type", 0.6), ("this", 1.1)]
    assert segs[1].words is None
```

```python
# tests/unit/test_adapter_youtube.py
import json
from pathlib import Path

from skipwatch.adapters.ytdlp_common import choose_caption_track

REC = Path(__file__).resolve().parents[1] / "fixtures" / "recorded" / "youtube"


def test_caption_choice_prefers_manual_then_orig():
    info = {"language": "de", "subtitles": {"live_chat": [{}], "de": [{"ext": "vtt"}]},
            "automatic_captions": {"en": [{}], "de-orig": [{}], "ab": [{}]}}
    assert choose_caption_track(info) == ("de", "manual")
    info["subtitles"] = {}
    assert choose_caption_track(info) == ("de-orig", "auto")
    assert choose_caption_track({"language": None, "subtitles": {}, "automatic_captions": {"ab": [{}]}}) is None


def test_recorded_manual_fixture_builds_a_bundle(tmp_path, monkeypatch):
    info = json.loads((REC / "manual-captions.info.json").read_text())
    ...  # monkeypatch content_free.extract -> info, download -> MediaInfo(path="media/video.mp4", width=1280, height=720, has_audio=True),
         # download_captions -> ("captions/x.en.json3", "en", "manual"); run ADAPTER.build; assert:
    # bundle.source.platform == "youtube", bundle.source.author_name == info["uploader"], bundle.context.captions_kind == "manual",
    # bundle.context.post_text == info["description"] (full), bundle.route.context == "free", bundle.fetched_with_cookies is False,
    # [c.op for c in bundle.provider_calls] == ["yt-dlp.metadata", "yt-dlp.captions", "yt-dlp.download"]


def test_r_ing_6_login_required_is_exit_4_naming_the_flag(tmp_path, monkeypatch):
    ...  # extract raises DownloadError("ERROR: [youtube] x: Sign in to confirm your age. ... Use --cookies-from-browser or --cookies ...")
    # CliRunner ingest https://www.youtube.com/watch?v=x --work W --provider free  -> exit_code == 4 and "--cookies-from-browser" in output
```

Write the two elided bodies out in full in the test file; the comments above are the exact assertions.

```python
# tests/unit/test_adapter_generic.py
def test_generic_unsupported_url_raises_no_media(...):   # extract raises DownloadError("ERROR: Unsupported URL: https://example.com/post")
    ...  # ADAPTER.build -> raises NoMediaError; via CLI with no text adapter registered: exit 7 (M2) and message names the URL
```

- [ ] **Step 2-4:** FAIL, implement, PASS (`uv run pytest tests/unit -k "json3 or adapter_youtube or adapter_generic" -v`).
- [ ] **Step 5: Commit** `git commit -m "M2-B: YouTube and generic adapters, json3 captions, caption track choice"`

### Task M2-B4: `skipwatch probe` (issue 4) and the live YouTube test

**Files:** Create `src/skipwatch/probe.py`, `src/skipwatch/commands/probe.py`, `tests/unit/test_probe.py`, `tests/live/__init__.py`, `tests/live/test_live_youtube.py`

**Interfaces:** `probe(value: str, opts: IngestOptions) -> ProbeResult`: local paths use `media.probe` (kind `file`, captions when a sidecar exists per M0-M1 issue 4); URLs use `content_free.extract` (no download) and `choose_caption_track`; `long_video = duration_s > 3600`; `estimated_run_s = round(30 + duration_s * f)` where `f = 0.05` with captions, `0.25` with mlx, `0.6` with faster-whisper, `0.1` with a cloud key; errors map like ingest (exit 4, 2, 3, 7). Writes nothing. Command: `skipwatch probe <url|path> [--cookies-from-browser B] [--json]`; stderr one line: `Probe: "<title>" <mm:ss>, captions <yes|no>, est. <n>s`.

- [ ] **Step 1: Failing tests** (fixture-driven; same monkeypatch pattern): `test_probe_youtube_fixture_reports_duration_and_captions`, `test_probe_long_video_flag_over_60_minutes` (fixture copy with `duration: 3700`), `test_probe_writes_nothing` (`SKIPWATCH_HOME` stays empty), `test_probe_json_validates` (R-CLI-2: `ProbeResult.model_validate_json(r.stdout)`).
- [ ] **Step 2: Live test** `tests/live/test_live_youtube.py` (marker `live`; uses the G1 URL from `tests/golden/golden.json` when present, else skips): runs `skipwatch ingest <G1> --work <tmp> --provider free --json`; asserts exit 0, `captions_kind in {"manual","auto"}`, `media.height` short side in [720, 1080], `transcribe --backend captions` exit 0 with at least 20 segments.
- [ ] **Step 3: FAIL, implement, PASS** (`uv run pytest tests/unit/test_probe.py -v`). Live run (allowed here, once): `uv run pytest -m live tests/live/test_live_youtube.py -v`; paste the output into the PR.
- [ ] **Step 4: Commit and push** `git commit -m "M2-B: probe command and live YouTube ingest test" && git push -u origin m2/youtube-generic`

---

## Package M2-C: Local Whisper backends (`m2/whisper`)

### Task M2-C1: Audio extraction

**Files:** Create `src/skipwatch/audio.py`, `tests/unit/test_audio.py`

**Interfaces (M2-D depends on these exact names):**
- `extract_audio(work: WorkDir, bundle: IngestBundle) -> Path`: writes `work/media/audio-16k.wav` (`ffmpeg -v error -y -i <media> -vn -ac 1 -ar 16000 -c:a pcm_s16le <out>`), reusing it when it exists and is newer than the media file (R-CLI-1); media path from `bundle.media.path` (absolute for local files, work-relative otherwise); no audio stream: `SkipwatchError(NO_CONTENT, "the video has no audio track")` (the orchestrator then treats the run as silent).
- `load_wav_float32(path: Path) -> "numpy.ndarray"` (imports numpy lazily; `wave` module; int16 / 32768.0).
- `encode_mp3_chunks(wav: Path, out_dir: Path, chunk_s: int = 3000, kbps: int = 32) -> list[tuple[Path, float]]` (chunk path and its start offset in seconds; `ffmpeg -ss <start> -t <chunk_s> -i wav -ac 1 -ar 16000 -b:a 32k`).
- `audio_duration(wav: Path) -> float`.

- [ ] Tests (system ffmpeg, `needs_ffmpeg` skip): `test_extract_audio_16k_mono` (2 s sine from `testsrc`+`sine` lavfi: `wave` reports 1 channel, 16000 Hz, about 32000 frames), `test_extract_audio_is_reused` (mtime unchanged on second call), `test_no_audio_track_is_exit_7`, `test_mp3_chunks_offsets` (130 s input, `chunk_s=60`: offsets `[0.0, 60.0, 120.0]`). FAIL, implement, PASS, commit `M2-C: audio extraction for transcription`.

### Task M2-C2: faster-whisper and mlx-whisper backends (word timestamps)

**Files:** Create `src/skipwatch/providers/transcribe_faster.py`, `src/skipwatch/providers/transcribe_mlx.py`, `tests/unit/test_transcribe_whisper.py`, `tests/pipeline/test_whisper_pipeline.py`

**Interfaces:**
- `FasterWhisperBackend`: `name="faster"`, `cloud=False`, `auto_rank=2`; `available()` = `importlib.util.find_spec("faster_whisper") is not None` and media has audio; `missing_hint()` = `'uv sync --project "<root>" --extra whisper'` (root from `CLAUDE_PLUGIN_ROOT` else `uv tool install "skipwatch[whisper]"`, same rule as doctor); `transcribe(work, model)`: model default `small` (`large-v3-turbo` when `model` given as such by `--thorough`; the orchestrator passes `--model large-v3-turbo`), `WhisperModel(model, device="auto", compute_type="int8")`, `model.transcribe(str(wav), word_timestamps=True, vad_filter=True)`; maps segments to `Segment(start, end, text.strip(), words=[Word(w=word.strip(), s=start, e=end)])`; `Transcript(origin="faster-whisper", model=model, language=info.language, segments=...)`.
- `MlxWhisperBackend`: `name="mlx"`, `auto_rank=1`; `available()` = Apple Silicon and `find_spec("mlx_whisper")`; default repo `mlx-community/whisper-large-v3-turbo` (3.4); `mlx_whisper.transcribe(load_wav_float32(wav), path_or_hf_repo=repo, word_timestamps=True)` (issue 13: an array, never a path); maps the dict result; `origin="mlx-whisper"`, `model="large-v3-turbo"`.
- `BACKENDS = (FasterWhisperBackend(),)` and `(MlxWhisperBackend(),)` in the two modules.
- Silence: `transcribe.mark_silence` (M1) runs on every transcript, so the silent path needs no new code; the pipeline test below pins it.

- [ ] **Step 1: Failing unit tests** with fake modules injected into `sys.modules` (no real model, no network):

```python
import sys
import types
from dataclasses import dataclass

from skipwatch.providers.transcribe_faster import FasterWhisperBackend


@dataclass
class W: start: float; end: float; word: str; probability: float = 0.9
@dataclass
class S: start: float; end: float; text: str; words: list
@dataclass
class Info: language: str; duration: float


def test_faster_maps_word_timestamps(tmp_path, monkeypatch, work_with_audio):
    calls = {}
    class FakeModel:
        def __init__(self, name, device, compute_type): calls["init"] = (name, device, compute_type)
        def transcribe(self, audio, word_timestamps, vad_filter):
            calls["word_timestamps"] = word_timestamps
            return iter([S(1.0, 2.5, " paste this", [W(1.0, 1.4, " paste"), W(1.5, 2.5, " this")])]), Info("en", 60.0)
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))
    t = FasterWhisperBackend().transcribe(work_with_audio, None)
    assert calls["init"] == ("small", "auto", "int8") and calls["word_timestamps"] is True
    assert t.origin == "faster-whisper" and t.language == "en"
    assert [(w.w, w.s, w.e) for w in t.segments[0].words] == [("paste", 1.0, 1.4), ("this", 1.5, 2.5)]
```

  (`work_with_audio` is a fixture in the same file that writes `ingest.json` and a 1 s silent `media/audio-16k.wav` with the `wave` module.) Same shape for mlx: `test_mlx_receives_an_array_not_a_path` asserts the first argument is not a `str`, and `path_or_hf_repo == "mlx-community/whisper-large-v3-turbo"`. Plus `test_auto_prefers_mlx_on_apple_silicon_then_faster` (monkeypatch `available`), `test_whisper_missing_is_exit_8_with_extra_command`.

- [ ] **Step 2: Pipeline test** (`@pytest.mark.pipeline` and `@pytest.mark.whisper`; skipped unless a backend imports): run `ingest` on `tests/fixtures/tutorial-60s.mp4` copied to `tmp_path` **without** its `.vtt` sidecar, then `transcribe --backend auto`; assert `origin in {"mlx-whisper","faster-whisper"}`, every segment has words, and each scripted sentence start from `tutorial-60s.script.json` is within 1.0 s of a segment start (11.2). Second test `test_silent_video_sets_silent_and_dense_frames`: make a 30 s `testsrc2` video with `anullsrc` audio, transcribe (`silent is True`), run `frames`, assert `frames.json` `sampling.per_minute == 6`.
- [ ] **Step 3: FAIL, implement, PASS.** Local run with the extra: `uv sync --dev --extra whisper && uv run pytest -m "pipeline and whisper" -v` (downloads the `small` model once, about 500 MB; allowed here).
- [ ] **Step 4: Commit and push** `git commit -m "M2-C: faster-whisper and mlx-whisper backends with word timestamps" && git push -u origin m2/whisper`

---

## Package M2-D: Cloud backends (`m2/cloud`)

### Task M2-D1: OpenAI, Groq, Deepgram with explicit-only selection (R-TR-2)

**Files:** Create `src/skipwatch/providers/transcribe_cloud.py`, `tests/fixtures/recorded/cloud/{openai_verbose.json,groq_verbose.json,deepgram_listen.json}`, `tests/unit/test_transcribe_cloud.py`, `tests/live/test_live_cloud.py`

**Interfaces:**
- Three backends, all `cloud=True`, `auto_rank=None`, `BACKENDS = (OpenAIBackend(), GroqBackend(), DeepgramBackend())`.
- `available(bundle)`: the env var is set (`OPENAI_API_KEY`, `GROQ_API_KEY`, `DEEPGRAM_API_KEY`); `missing_hint()`: `"set OPENAI_API_KEY"` and so on.
- `transcribe(work, model)`: `audio.extract_audio`, then `audio.encode_mp3_chunks(wav, work.path / "media" / "chunks")`; one request per chunk; offsets added to every `start`/`end`/word time; `Transcript(origin=<name>, model=<model>, language=<lang>, segments=...)`.
  - OpenAI: `requests.post("https://api.openai.com/v1/audio/transcriptions", headers={"Authorization": f"Bearer {key}"}, files={"file": (name, fh, "audio/mpeg")}, data=[("model", "whisper-1"), ("response_format", "verbose_json"), ("timestamp_granularities[]", "word"), ("timestamp_granularities[]", "segment")], timeout=600)`. Segments from `segments[]`; words from top-level `words[]` assigned to the segment whose `[start, end]` contains the word start.
  - Groq: same request shape at `https://api.groq.com/openai/v1/audio/transcriptions`, model `whisper-large-v3-turbo`.
  - Deepgram: `requests.post("https://api.deepgram.com/v1/listen", params={"model": "nova-3", "smart_format": "true", "punctuate": "true", "utterances": "true", "detect_language": "true"}, headers={"Authorization": f"Token {key}", "Content-Type": "application/octet-stream"}, data=fh, timeout=600)`; segments from `results.utterances[]` (`start`, `end`, `transcript`, words with `punctuated_word` or `word`); language `results.channels[0].detected_language`.
  - HTTP 401/403: `SkipwatchError(MISSING_DEPENDENCY, "<provider> rejected the key in <ENV>")`; other HTTP errors or timeouts: `SkipwatchError(DOWNLOAD_FAILED, "<provider> transcription failed: <status>")`. The key value never appears in any message or file.
- No extra dependency: `requests` is a core dependency since M2-A.

- [ ] **Step 1: Write the three response fixtures by hand** from the shapes in Tooling facts (two segments, five words each; Deepgram with two utterances). Mark each with `"_handmade": "shape from provider docs and SDK types, 2026-10-09"`.
- [ ] **Step 2: Failing tests** (monkeypatch `requests.post` in the module; no sockets):

```python
def test_r_tr_2_cloud_needs_explicit_backend(cli_work_without_captions, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    r = CliRunner().invoke(app, ["transcribe", "--work", str(cli_work_without_captions)])
    assert r.exit_code == 8                      # auto never chooses cloud, even with a key present
    assert not (cli_work_without_captions / "transcript.json").exists()


def test_openai_request_shape_and_mapping(...):
    # captured kwargs: url ends with /v1/audio/transcriptions; ("model", "whisper-1") in data;
    # both timestamp_granularities[] entries present; Authorization header starts "Bearer ";
    # transcript.origin == "openai"; words attached to the right segments


def test_chunk_offsets_are_added(...):
    # two chunks at offsets 0 and 3000: the second response's first segment start 1.0 becomes 3001.0


def test_deepgram_uses_token_auth_and_octet_stream(...):
    # headers["Authorization"].startswith("Token "); headers["Content-Type"] == "application/octet-stream";
    # params["model"] == "nova-3"; transcript.language == fixture detected_language


def test_key_never_written_or_printed(...):
    # 401 response: exit 8; "sk-test-not-real" not in r.output and not in any file under the work folder
```

  Write each elided body in full using the captured-kwargs pattern: `monkeypatch.setattr(transcribe_cloud.requests, "post", fake)` where `fake(url, **kw)` records `(url, kw)` and returns an object with `status_code`, `json()`.
- [ ] **Step 3: Live test** `tests/live/test_live_cloud.py` (marker `live`; skips per provider when its key is absent): transcribe `tests/fixtures/narration.wav` wrapped in a work folder; assert at least one segment start within 1 s of each scripted sentence. Not run by the builder; the orchestrator runs it only if Robert provides a key.
- [ ] **Step 4: FAIL, implement, PASS, commit, push** `git commit -m "M2-D: OpenAI, Groq and Deepgram backends, explicit only (R-TR-2)" && git push -u origin m2/cloud`

---

## Package M2-E: Cache and resume (`m2/cache-resume`)

### Task M2-E1: Run cache (R-TR-3)

**Files:** Create `src/skipwatch/runcache.py`, `tests/unit/test_runcache.py`; Modify `src/skipwatch/ingest.py`, `src/skipwatch/transcribe.py` (cache hooks only)

**Interfaces:**
- `cache_key(source: SourceInfo) -> str` (issue 6).
- `lookup(home: Path, key: str, name: str, now: datetime) -> Path | None`: `home/cache/<key>/<name>` when `entry.json` exists and `created_at` is under 7 days old.
- `store(home: Path, key: str, source: str, files: dict[str, Path], now: datetime) -> CacheEntry`: copies files, writes `entry.json` (`CacheEntry`), keeps files from earlier stores of the same key.
- Hook in `ingest.run_ingest`: after `detect` and metadata, before provider enrichment: a fresh cached `ingest.json` supplies `context`, `source`, `transcript_hint`, `provider_calls` (marked as cached by `from_cache=True`), and treg is not called again; media is still downloaded. After a successful ingest: `store(... {"ingest.json": ...})`.
- Hook in `transcribe.run_transcribe`: before selecting a backend, a fresh cached `transcript.json` whose `origin` matches the requested backend (any origin under `auto`) is copied and the backend never runs; after success: `store(... {"transcript.json": ...})`. Progress line: `Transcribe: reused cached transcript (<origin>, <age>h old)`.

- [ ] Tests: `test_r_tr_3_transcript_reused_within_7_days` (fake backend counts calls: second run on a new work folder for the same URL makes 0 calls), `test_r_tr_3_cache_ignored_after_7_days` (`now + 8 days`: backend runs again), `test_cache_key_local_file_changes_with_mtime`, `test_ingest_cache_skips_enrichment_but_not_media` (fake provider `enrich` counter stays 0 on the second ingest; fake download counter is 2), `test_explicit_backend_mismatch_ignores_cache` (cached `captions`, requested `faster`: backend runs). FAIL, implement, PASS, commit `M2-E: 7-day run cache for ingest and transcript (R-TR-3)`.

### Task M2-E2: `skipwatch resume` (issue 5)

**Files:** Create `src/skipwatch/resume.py`, `src/skipwatch/commands/resume.py`, `tests/unit/test_resume.py`

**Interfaces:** `resume_info(work: Path) -> ResumeResult`; `newest_incomplete(home: Path) -> Path | None` (work folders sorted by the `yyyymmdd-hhmmss` suffix, newest first; skips folders whose `review` stage is `done`); command `skipwatch resume [<dir>] [--json]`: stderr one line `Resume: <dir> at <stage> (<n> stages done)`; no folder and none incomplete: exit 0 with `Resume: nothing to resume` and `next_stage: null`; a folder without `stages.json`: exit 2 (`not a SkipWatch work folder`).

- [ ] Tests:

```python
def test_running_stage_counts_as_incomplete(tmp_path):
    w = WorkDir(tmp_path / "w"); w.ensure()
    for s in ("detect", "ingest", "transcribe"): w.mark(s, "done")
    w.mark("frames", "running")                      # process was killed here
    r = resume_info(w.path)
    assert r.next_stage == "frames" and r.completed == ["detect", "ingest", "transcribe"]


def test_newest_incomplete_skips_reviewed_runs(sw_home): ...   # two folders; the newer has review done -> returns the older
def test_resume_reads_run_json(tmp_path): ...                   # RunFile written -> ResumeResult.run.flags == ["--thorough"]
def test_resume_json_validates_and_exit_codes(tmp_path): ...   # R-CLI-2; non-work folder -> exit 2
```

  Write the three elided bodies out in full. FAIL, implement, PASS, commit, push `git commit -m "M2-E: resume command (R-WORK-1)" && git push -u origin m2/cache-resume`.

---

## Package M2-F: Golden set (`m2/golden`)

### Task M2-F1: Pick and verify the five golden videos

**Files:** Create `tests/golden/golden.json`, `tests/golden/README.md`, `scripts/golden_check.py`, `tests/unit/test_golden_file.py`

**Selection rules (the builder picks; Robert supplies none):**
- G1: a YouTube CLI tutorial, 5 to 15 minutes, **manual** English captions, a worked example that runs offline in a scratch directory with free, cross-platform tools (for example `jq`, `git`, `ripgrep`, `make`, a Python stdlib script); from a channel with over 50k subscribers and an upload over 6 months old (stability).
- G2: a public X post with a native video tutorial (screen recording showing prompts or settings on screen), 1 to 5 minutes, from an account with over 10k followers; no login wall when opened logged out.
- G3: a public TikTok tutorial with on-screen text, 30 s to 3 min.
- G4: a public Instagram reel tutorial, 30 s to 3 min (expect it may need cookies; record that).
- G5: a YouTube talk with slides, 25 to 40 minutes, captions present.
- No creator who is a private individual without a public creator presence; no NSFW, medical, financial-advice or political content.

**golden.json shape** (validated by `test_golden_file.py`):

```json
{
  "version": 1,
  "selected_at": "2026-10-09",
  "videos": [
    {"id": "G1", "url": "https://www.youtube.com/watch?v=...", "platform": "youtube",
     "title": "...", "author": "@...", "duration_s": 612, "captions": "manual",
     "why": "one sentence on why it was picked",
     "needs_cookies": false,
     "expected": {"steps": [6, 20], "inferred_ratio_max": 0.2, "gaps_max": 1,
                  "safety_flags_max": 0, "illegible_in_quotes_max": 0},
     "s2": {"task": "the video's worked example, phrased as a user request",
            "verify": "a shell command run in the scratch dir that exits 0 only when the task was done"}}
  ]
}
```

G2 also carries `expected.context = {"thread_min": n, "replies_min": n, "links_min": n}` with the counts seen on the post (view it logged out in a browser); pick an X post with at least one continuation, one author reply and one link so M4 acceptance #2 is meaningful.

Ranges: G1 steps [6, 20], inferred max 0.2, gaps max 1; G2 to G4 steps [3, 15], inferred max 0.3, gaps max 2; G5 steps [8, 40], inferred max 0.3, gaps max 3. All: safety flags 0, illegible in quotes 0 (S3, S4). `s2` only for G1.

- [ ] **Step 1: Failing schema test** `tests/unit/test_golden_file.py`: five entries G1 to G5 in order; platforms `youtube, x, tiktok, instagram, youtube`; G1 `captions == "manual"`; G5 `duration_s` in [1500, 2400]; every `expected` has the five keys; ranges well formed; G1 has `s2.task` and `s2.verify`; G2 has `expected.context` with three non-negative integers summing to at least 3; no URL contains `?si=` or other share tracking parameters.
- [ ] **Step 2 (live, allowed here):** `scripts/golden_check.py [--only GN]` runs `yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "js_runtimes": ...}).extract_info(url, download=False)` per entry (metadata only, no cookies) and prints `G1 OK youtube 10:12 captions=manual formats>=720p=yes` or `G1 FAIL <reason>`; exit 0 only when all pass. Pick candidates, run it, replace any candidate that fails (G4 may legitimately fail without cookies: then set `needs_cookies: true` and record the error line in `why`).
- [ ] **Step 3:** `tests/golden/README.md`: how to run `golden_check.py` and `golden_run.py`, the selection rules above, and "replace a video when it disappears; keep the id".
- [ ] **Step 4: Commit** `git commit -m "M2-F: golden set selection and metadata check"`

### Task M2-F2: `scripts/golden_run.py`

**Interfaces:** `golden_run.py [--only G1,G5] [--out DIR] [--plugin-dir .]`: for each entry, sets `SKIPWATCH_HOME=<out>/<id>/home`, runs `claude -p --plugin-dir <repo> --allowedTools "Bash,Read,Write,Agent" "/skipwatch:skipwatch <url> --yes --to <out>/<id>/skills --name <id-lower>-skill" < /dev/null` (timeout 30 min, plus `--cookies-from-browser chrome` only when the entry says `needs_cookies` **and** the env var `SKIPWATCH_GOLDEN_COOKIES=chrome` is set); then judges from `<home>/work/*/check-report.json` and `<home>/work/*/staging/<name>/SKILL.md` (issue 16): steps, inferred ratio, gaps, safety flags count, count of `[illegible` inside `>` quote lines. Prints one line per video, `G1 PASS steps=11 inferred=0.09 gaps=0 flags=0 illegible_in_quotes=0 installed=yes`, or `FAIL` with each out-of-range value as `steps=4 (want 6..20)`. Exit 0 when all selected pass. Pure judging is `judge(report: dict, skill_md: str, expected: dict) -> list[str]`, unit-tested in `test_golden_file.py` (`test_judge_flags_illegible_inside_quotes_only`, `test_judge_ranges`).

- [ ] FAIL, implement, PASS, commit, push `git commit -m "M2-F: golden_run.py judge and runner" && git push -u origin m2/golden`

---

## Package M2-G: Orchestrator M2 (`m2/orchestrator`)

### Task M2-G1: run-protocol, SKILL.md and review screen for URLs, Whisper, cloud, resume

**Files:** Modify `skills/skipwatch/SKILL.md`, `skills/skipwatch/references/run-protocol.md`, `skills/skipwatch/references/review-screen.md`, `tests/unit/test_orchestrator_files.py`

Content requirements (tests grep for the quoted phrases):
- run-protocol.md, new steps before ingest: write `W/run.json` (`{"schema": "skipwatch/run/1", "input": ..., "flags": [...], "name": ..., "started_at": ...}`); run `probe <input> --json`; when `long_video` is true, print `Long video: <mm:ss>, about <n> min to process.` and continue only under `--yes` or after the user says yes.
- Ingest passes `--provider <flag or auto>` and `--cookies-from-browser <b>` only when the user gave the flag. Exit 4: print the engine's message and "Re-run with --cookies-from-browser <browser> if you can open it logged in." Exit 3: print every route line. Exit 2 and 7: say what was tried, stop.
- Transcribe: `--backend auto` (plus `--model large-v3-turbo` under `--thorough` when the backend is `faster`). Exit 8 with no local Whisper: if doctor listed a cloud key, ask once: "No local transcription is installed. Send the audio to <OpenAI|Groq|Deepgram> for transcription? (yes / install Whisper instead / cancel)"; only on yes run `transcribe --work W --backend <name>` (R-TR-2: "Audio goes to a cloud provider only after the user said yes to that provider by name."). Otherwise print the install command from the engine message and stop.
- Silent path: when `transcript.json` has `silent: true`, say `Silent video: leaning on frames and post text.`, run `frames --dense`, and in the outline prefer `[on-screen]` and `[written]` tags.
- Resume: `/skipwatch resume [dir]` runs `resume [dir] --json`; reads `run` for the original input and flags; re-runs from `next_stage` with the same flags; when `next_stage` is `read`, `distill` or `critique`, re-dispatches readers only for batches whose notes file is missing or invalid; when `media_present` is false and the next stage needs media (`ingest`, `transcribe`, `frames`), re-runs `ingest` first.
- Media retention: delete `W/media/` after install unless `--keep-media`; keep it on any failure (3.4).
- review-screen.md: `Provider calls:` line shows `none (free route)` or `free route; cached from <date>` when `ingest.json` has `from_cache`.
- SKILL.md: `resume` no longer prints "arrives in M2"; flags list adds `--provider`, `--cookies-from-browser`, `--keep-media`; stays under 300 lines.

- [ ] Tests (extend `test_orchestrator_files.py`): phrases present ("only after the user said yes to that provider by name", "probe", "run.json", "resume", "--cookies-from-browser", "Silent video"); SKILL.md under 300 lines; no em dash; `claude plugin validate --strict .` exit 0.
- [ ] Commit, push `git commit -m "M2-G: orchestrator protocol for URLs, Whisper, cloud consent, resume (R-TR-2, R-UX-1)" && git push -u origin m2/orchestrator`

---

## Package M2-H: Resume pipeline test and CI (`m2/pipeline`)

### Task M2-H1: Killed `frames` stage, then resume

**Files:** Create `tests/pipeline/test_resume_pipeline.py`; Modify `.github/workflows/ci.yml`

```python
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app

pytestmark = pytest.mark.pipeline
FIX = Path(__file__).resolve().parents[1] / "fixtures"


def stage(work, name):
    return json.loads((work / "stages.json").read_text())["stages"][name]["status"]


def test_resume_after_killed_frames_completes(tmp_path):
    work = tmp_path / "work"
    run = CliRunner().invoke
    assert run(app, ["ingest", str(FIX / "tutorial-60s.mp4"), "--work", str(work)]).exit_code == 0
    assert run(app, ["transcribe", "--work", str(work)]).exit_code == 0
    proc = subprocess.Popen([sys.executable, "-m", "skipwatch.cli", "frames", "--work", str(work), "--per-minute", "6"],
                            stderr=subprocess.DEVNULL)
    deadline = time.time() + 30
    while time.time() < deadline and stage(work, "frames") != "running":
        time.sleep(0.05)
    assert stage(work, "frames") == "running"
    os.kill(proc.pid, signal.SIGKILL); proc.wait()
    assert stage(work, "frames") == "running"            # killed, not failed

    r = run(app, ["resume", str(work), "--json"])
    assert r.exit_code == 0 and json.loads(r.stdout)["next_stage"] == "frames"
    for args in (["frames", "--work", str(work)], ["plan", "--work", str(work)]):
        assert run(app, args).exit_code == 0
    assert stage(work, "frames") == "done" and stage(work, "plan") == "done"
    frames = json.loads((work / "frames.json").read_text())["frames"]
    on_disk = sorted(p.name for p in (work / "frames").iterdir())
    assert on_disk == sorted(f"{f['id']}.jpg" for f in frames)   # no partial frames survive
```

Note: `python -m skipwatch.cli` needs `if __name__ == "__main__": main()` at the bottom of `cli.py`. If M0-A did not add it, this task uses `[sys.executable, "-c", "from skipwatch.cli import main; main()", ...]` instead (do not edit `cli.py`). On Windows `SIGKILL` does not exist; the pipeline job runs on ubuntu and macos only.

- [ ] CI: add `-m "not live"` explicitly to every `pytest` line (belt and braces with `addopts`), and a `whisper` job on `macos-latest` only: `uv sync --dev --extra whisper` then `uv run pytest -m "pipeline and whisper" -v` (downloads the `small` model, about 500 MB, cached with `actions/cache` on `~/.cache/huggingface`).
- [ ] Run `uv run pytest -m pipeline -v`; all pass. Commit, push `git commit -m "M2-H: resume after killed frames pipeline test, whisper CI job"`.

---

## M2 acceptance (merged M2 tree, `uv sync --dev`)

| # | "Done when" item | Exact command | Expected |
|---|---|---|---|
| 1 | Unit, lint, types, schemas | `bash scripts/ci_local.sh` | last line `CI-LOCAL: OK` |
| 2 | Resume after a killed `frames` completes | `uv run pytest tests/pipeline/test_resume_pipeline.py -v` | `1 passed` |
| 3 | Whisper path (local) | `uv sync --dev --extra whisper && uv run pytest -m "pipeline and whisper" -v` | all pass (2 tests) |
| 4 | Golden metadata still valid | `uv run python scripts/golden_check.py --only G1,G5` | `G1 OK ...`, `G5 OK ...`, exit 0 |
| 5 | G1 produces a skill (paid, orchestrator triggers) | `uv run python scripts/golden_run.py --only G1 --out /tmp/sw-golden` | `G1 PASS ...` and `installed=yes`, exit 0 |
| 6 | S2: a fresh session with only the G1 skill completes G1's worked example (paid) | `T=$(mktemp -d) && mkdir -p $T/.claude/skills && cp -R /tmp/sw-golden/G1/skills/g1-skill $T/.claude/skills/ && cd $T && git init -q && claude -p --setting-sources project --output-format stream-json --verbose --allowedTools "Bash,Read,Write,Edit,Skill" "$(jq -r '.videos[0].s2.task' <repo>/tests/golden/golden.json)" < /dev/null > s2.jsonl; jq -r 'select(.type=="system" and .subtype=="init") .skills' s2.jsonl; bash -c "$(jq -r '.videos[0].s2.verify' <repo>/tests/golden/golden.json)"; echo $?` | the init `skills` list contains `g1-skill` and no other user or project skill (built-in and plugin entries aside); a `Skill` tool call to `g1-skill` appears in `s2.jsonl`; the verify command prints and the final line is `0`. If the init list shows any user skill, the run does not count: report to the orchestrator, who decides how to isolate (a separate macOS user account is the fallback). |
| 7 | G5 within range (paid, informative for M2) | `uv run python scripts/golden_run.py --only G5 --out /tmp/sw-golden` | `G5 PASS ...` |
| 8 | Evals still pass (paid) | `claude plugin eval . --trust-plugin --scaffold --case local-fixture --case doctor --case no-trigger --runs 1 --threshold 0.8 --no-publish --max-cost-usd 24 < /dev/null; echo $?` | `0` |

---

# MILESTONE M3: Social platforms

## Package M3-A: Spike (`m3/spike`), live, cost cap $0.05

**Goal (8.3 "M3 spike"):** before the X, Instagram and Facebook adapters, confirm with real calls which treg responses include a downloadable media URL, confirm yt-dlp handles a public X video without cookies, and record every answer and a scrubbed fixture per call.

**Budget rule:** total treg spend under **$0.05**, checked by `treg balance --json` before and after (record both micro-USD numbers). Planned calls (catalog prices, 2026-10-09):

| # | Endpoint | Input | Catalog price | Question it answers |
|---|---|---|---|---|
| 1 | `anyapi.twitter.thread` (POST body `{"url"}`) | G2 URL | $0.00375 | thread continuations; `tweets[].media[].videoUrl` present? |
| 2 | `treg.x.post.comments` (POST body `{"tweet_id"}`, header `X-Treg-Route-Max-Cost: 0.01`) | G2 id | $0.0005 to $0.01 | author replies findable by `authorHandle`? response shape |
| 3 | `anyapi.twitter.tweet_transcript` (POST `{"url"}`) | G2 URL | $0.0012 | untimed transcript text for cross-check |
| 4 | `anyapi.tiktok.video_download` (POST `{"url"}`) | G3 URL | $0.0012 | `videoUrl` downloadable with a plain GET? |
| 5 | `anyapi.instagram.post.detail` (POST `{"url"}`) | G4 URL | $0.0015 | `videoUrl` downloadable with a plain GET? caption text field? |
| 6 | `anyapi.facebook.post.detail` (POST `{"url"}`) | a public Facebook video post picked here | $0.002 | does it expose any media URL (the catalog example shows none)? |
| 7 | `anyapi.youtube.video_transcript_full` (POST `{"url","captionKind":"any"}`) | G1 URL | $0.00308 | timed segments shape (stored only as hint, issue 7) |
| | **Planned total** | | **about $0.012 to $0.022** | leaves headroom under $0.05 for one retry each of 4 to 6 |

Free calls (no treg): yt-dlp metadata and a 10-second partial download (`download_ranges` not needed: use `--max-filesize 5M` equivalent `max_filesize: 5_000_000`) on G2, G3, G4 and the Facebook post, without cookies; yt-dlp on one text-only X post (issue 8).

### Task M3-A1: Run the spike and record

**Files:** Create `docs/spikes/2026-10-m3-spike.md`, `tests/fixtures/recorded/treg/<endpoint>.json` (one per call, scrubbed), `tests/fixtures/recorded/{x,tiktok,instagram,facebook,text}/*.info.json` (via `scripts/record_fixture.py`); Modify `skills/skipwatch/references/platforms.md`

- [ ] **Step 1:** `treg balance --json > /tmp/sw-bal-before.json` (record `balance` micro-USD).
- [ ] **Step 2:** for each row, run exactly the `treg call` shown in `treg catalog get <id>` "RUN IT", with `2> err.txt`, saving stdout to `/tmp/sw-spike/<n>.json`. Record **where the call id appears** (stdout field, stderr line, or neither) for issue 10, and run `treg review <id> useful|partly|not_useful --reason "<one sanitized line>"` once per call (R-ING-3, also proves the review command works). Stop calling if the running total from `costUsd` fields exceeds $0.04.
- [ ] **Step 3:** for every media URL returned (rows 1, 4, 5, 6), test a plain `curl -sS -r 0-1023 -o /dev/null -w "%{http_code} %{content_type}\n" "<url>"` (no cookies, default UA): record status and content type, and whether it expires (the query string's expiry parameter, if any).
- [ ] **Step 4:** yt-dlp checks, no cookies: `uv run python scripts/record_fixture.py <url> --name <slug> --platform <dir>` for G2, G3, G4, the Facebook post, and one text-only X post (expect `No video could be found in this tweet`; record the exact error line in the spike doc).
- [ ] **Step 5:** `treg balance --json > /tmp/sw-bal-after.json`; spend = before minus after; must be under 50 000 micro-USD.
- [ ] **Step 6:** scrub every treg response with `scripts/scrub_fixture.py` and commit them as `tests/fixtures/recorded/treg/<endpoint-id>.json`. Grep for signed query strings and IPs as in Task M2-B1 Step 3 (prints nothing).
- [ ] **Step 7:** write `platforms.md`, one section per platform (YouTube, X, TikTok, Instagram, Facebook, generic, local, text), each with: free route result (works without cookies: yes/no, error line when not), formats seen (short side), captions available, treg endpoints and whether their media URL downloads with a plain GET, the call-id location, and "known failure modes" with the fix the orchestrator should print. Keep it under 150 lines; no em dash.
- [ ] **Step 8:** `docs/spikes/2026-10-m3-spike.md`: the table above with the actual cost per call, the balance before and after, every answer in one line, and the list of fixture files.
- [ ] **Step 9: Commit and push** `git commit -m "M3-A: spike results, platforms.md facts, recorded X/TikTok/Instagram/Facebook/treg fixtures" && git push -u origin m3/spike`

**Output contract for later packages:** M3-B, M3-C and M4-A read only `platforms.md` and the recorded fixtures. If the spike shows a fact that contradicts this plan (for example, yt-dlp needs cookies for public X videos), the builder reports it and the orchestrator amends the affected package before M3-B/C start.

---

## Package M3-B: X, text adapter, links (`m3/x-text`)

### Task M3-B1: Link fetching (R-ING-1)

**Files:** Create `src/skipwatch/providers/links.py`, `src/skipwatch/htmltext.py`, `tests/unit/test_links.py`

**Interfaces:**
- `htmltext.html_to_text(html: str) -> tuple[str | None, str]` (title, text): stdlib `html.parser`; drops `script`, `style`, `nav`, `footer`, `noscript`; block elements become newlines; whitespace collapsed.
- `links.extract_urls(text: str) -> list[str]`: `https?://` URLs in order, de-duplicated, trailing punctuation stripped, at most 5.
- `links.fetch_link(url: str) -> LinkContext | None`: refuses non-http(s), hosts that resolve to private, loopback, link-local or multicast addresses (`ipaddress` checks on `socket.getaddrinfo` results; resolution happens inside `providers/`), follows at most 3 redirects re-checking each host, `timeout=10`, `stream=True`, reads at most 2 MB; `text/html` goes through `html_to_text`; `text/plain` and `text/markdown` as is; anything else returns `None`; text capped at 20 000 chars (R-ING-1). GitHub repo URLs (`github.com/<o>/<r>` with no further path) fetch `https://raw.githubusercontent.com/<o>/<r>/HEAD/README.md` instead; gist URLs fetch `<gist>/raw`.
- `links.fetch_all(text: str, calls: list[ProviderCall]) -> list[LinkContext]`: appends one `ProviderCall(provider="free", op="link.get", endpoint=<host>, ok=...)` per link.

- [ ] Tests (monkeypatch `requests.get`/`Session.get` and `socket.getaddrinfo` in the module; no sockets):

```python
def test_r_ing_1_link_text_capped_at_20k(...): ...           # 50k-char HTML body -> len(text) == 20_000
def test_links_skip_private_hosts_and_binary(...): ...       # http://127.0.0.1/, http://10.0.0.5/, a host resolving to 192.168.1.2,
                                                              # and an image/png response all return None; requests.get never called for the first three
def test_redirect_to_private_host_is_refused(...): ...       # 302 Location http://localhost/ -> None
def test_github_repo_url_fetches_readme(...): ...            # requested URL == raw.githubusercontent.com/o/r/HEAD/README.md
def test_html_to_text_drops_scripts_and_keeps_headings(): ...
```

  Write each body out in full. FAIL, implement, PASS, commit `M3-B: link fetching with caps and private-host refusal (R-ING-1)`.

### Task M3-B2: X adapter and text adapter

**Files:** Create `src/skipwatch/adapters/x.py`, `src/skipwatch/adapters/text.py`, `tests/unit/test_adapter_x.py`, `tests/unit/test_adapter_text.py`

**Interfaces:**
- `x.py`: `PLATFORMS = ("x",)`; `XAdapter.build`: `content_free.extract`; `post_text = info["description"]` (yt-dlp puts the full tweet text there; confirm against the spike fixture, else `info["title"]`), never truncated (R-ING-1); `author = "@" + info["uploader_id"]`; `canonical_url = f"https://x.com/i/status/{id}"`; links from `post_text` via `links.fetch_all`; then `ytdlp_common.build_video_bundle` for captions (rare on X) and media. "No video could be found" raises `NoMediaError` (issue 8: on the free route the dispatcher has no text for X, so the text adapter returns exit 7 with "This post has no video. Enable treg (Tier 3) to read text posts.").
- `text.py`: `PLATFORMS = ("text",)`; `TextAdapter.build(detected, work, opts)`: for `x` URLs, asks each provider from `providers.registry.content_providers()` that is enabled for this run (`ingest.enabled_providers(opts, load_config())`) and has a `build_text_x` method; the first non-`None` bundle is returned; otherwise raises `SkipwatchError(NO_CONTENT, <issue 8 message>)` (M4-A adds `build_text_x` to treg); for other URLs `links.fetch_link(url)` on the page itself; under 200 words: `SkipwatchError(NO_CONTENT, "no video and under 200 words of text at <url>")` (8.2); else `IngestBundle(source=SourceInfo(kind="text", platform="generic", url=..., title=...), context=IngestContext(post_text=<page text>, links=fetch_all(page text)), media=None, route=Route(context="free", media=None))`.
- Transcribe and frames on a `text` bundle: `transcribe` writes nothing and marks the stage done with progress `Transcribe: text source, skipped` (M1-B said text-kind skips); `frames` writes an empty `frames.json` (M1-C audio-only path). If either M1 behaviour is missing, report to the orchestrator (do not edit `transcribe.py` or `frames.py` here).

- [ ] Tests from the spike fixtures: `test_x_fixture_builds_video_bundle_with_full_text` (post text equals the fixture description; author starts with `@`; canonical URL form), `test_x_links_are_fetched_and_capped` (fake `links.fetch_all`), `test_x_text_only_free_route_is_exit_7_naming_treg` (CLI, `--provider free`), `test_text_page_over_200_words_becomes_text_kind`, `test_text_page_under_200_words_is_exit_7`. FAIL, implement, PASS, commit, push `git commit -m "M3-B: X and text adapters" && git push -u origin m3/x-text`.

---

## Package M3-C: TikTok, Instagram, Facebook (`m3/tiktok-ig-fb`)

### Task M3-C1: Three thin adapters over `ytdlp_common`

**Files:** Create `src/skipwatch/adapters/tiktok.py`, `src/skipwatch/adapters/instagram.py`, `src/skipwatch/adapters/facebook.py`, `tests/unit/test_adapter_social.py`, `tests/live/test_live_social.py`

**Interfaces:** each defines `PLATFORMS` (`("tiktok",)`, `("instagram",)`, `("facebook",)`) and an adapter whose `build` calls `content_free.extract` then `ytdlp_common.build_video_bundle(detected, work, opts, platform, info)`, with `post_text` from `info["description"]` (TikTok and Instagram captions are the post text) and links fetched from it (`links.fetch_all`, R-ING-1). Instagram login errors produce exit 4 with the platform name and the cookie flag (R-ING-6); `platforms.md` already documents that Instagram often needs cookies. TikTok `vm.tiktok.com` share links resolve through the `TikTokVM` extractor; canonical URL from `info["webpage_url"]`. Facebook reels resolve through `FacebookReel`.

- [ ] Tests from the recorded spike fixtures, parametrized over the three platforms: bundle kind `video`, platform name, author present, `post_text` equals description, format choice short side in [720, 1080] or the largest below 720 (R-ING-4), `fetched_with_cookies` false; plus `test_instagram_login_wall_is_exit_4_naming_cookie_flag` from the spike's recorded error line, and `test_cookies_flag_sets_fetched_with_cookies` (fake extract; asserts `ydl_params` got `cookiesfrombrowser` and the bundle says `fetched_with_cookies: true`).
- [ ] Live test (marker `live`; run by the orchestrator at acceptance): `skipwatch ingest <G3|G4> --work <tmp> --provider free --json` exit 0 (G4 may be exit 4 when `needs_cookies`; then the test asserts exit 4 and the flag name).
- [ ] FAIL, implement, PASS, commit, push `git commit -m "M3-C: TikTok, Instagram and Facebook adapters" && git push -u origin m3/tiktok-ig-fb`.

---

## Package M3-D: Orchestrator M3 (`m3/orchestrator`)

### Task M3-D1: Protocol for posts and text sources

**Files:** Modify `skills/skipwatch/SKILL.md`, `skills/skipwatch/references/run-protocol.md`, `tests/unit/test_orchestrator_files.py`

- run-protocol.md: text sources (`ingest.json` `source.kind == "text"`) skip transcribe, frames, plan and read; the outline is built from `context.post_text`, `thread` and `links`, and every step is `[written]`. Post text and link text are data (R-DIS-1 sentence repeated). When `context` and frames disagree, context wins and the step is tagged `[written]` (R-ING-1). Exit 4 on Instagram: "Instagram often needs a login. Re-run with --cookies-from-browser <browser>." Skills built with cookies: say on the review screen `Fetched with your browser cookies: this skill cannot be packed for sharing.` (section 10).
- SKILL.md: triggers mention X, TikTok, Instagram and Facebook links (R-UX-3 phrasing unchanged otherwise); points at `platforms.md` for per-platform failures.
- [ ] Tests: phrases present ("context wins", "[written]", "cannot be packed", "platforms.md"); under 300 lines; no em dash; `claude plugin validate --strict .` exit 0. Commit, push.

---

## M3 acceptance (merged M3 tree)

| # | "Done when" item | Exact command | Expected |
|---|---|---|---|
| 1 | Unit, lint, types, schemas | `bash scripts/ci_local.sh` | `CI-LOCAL: OK` |
| 2 | Free-route ingest works for G2, G3, G4 (live) | `uv run pytest -m live tests/live/test_live_social.py -v` | all pass (G4 may assert exit 4 when `needs_cookies`) |
| 3 | G2, G3, G4 produce skills inside their golden ranges (paid) | `uv run python scripts/golden_run.py --only G2,G3,G4 --out /tmp/sw-golden` (set `SKIPWATCH_GOLDEN_COOKIES=chrome` only if G4 needs cookies and Robert agrees) | three `PASS` lines, exit 0 |
| 4 | S3: the X skill (G2) has zero `[illegible]` inside quote blocks and a fresh session can carry out the workflow (paid) | `grep -n '^>' /tmp/sw-golden/G2/home/work/*/staging/*/SKILL.md \| grep -c '\[illegible'` then the S2 recipe from M2 acceptance #6 with G2's skill and a task written from its Worked example section | `0`; the fresh session uses the G2 skill and reports completing (or, where the workflow needs an account or paid tool, stops at that step as the tester rules in 8.9 say; the orchestrator judges) |
| 5 | S4 on G1 to G4: zero safety flags | `jq '.results[] \| select(.check=="safety") \| .flags \| length' /tmp/sw-golden/G*/home/work/*/check-report.json` | every line `0` |
| 6 | platforms.md present and current | `uv run pytest tests/unit/test_orchestrator_files.py -v` | pass |

---

# MILESTONE M4: treg provider

## Package M4-A: treg content provider (`m4/treg`)

### Task M4-A1: `content_treg`: calls, call log, cost cap, review (R-ING-3)

**Files:** Create `src/skipwatch/providers/content_treg.py`, `tests/unit/test_content_treg.py`

**Interfaces:**
- `TregClient`: `__init__(self, max_cost_usd: float, runner=subprocess.run)`; `call(endpoint: str, *, body: dict | None = None, query: dict | None = None, headers: dict | None = None) -> dict | None`: builds `["treg", "call", endpoint, "--method", "POST", "--data", json.dumps(body)]` (or `--query k=v` pairs for GET endpoints, `--header` per header), timeout 60 s; refuses (returns `None`, records `error="cost cap"`) when `spent + catalog_price(endpoint) > max_cost_usd`; parses stdout JSON; `output.found == false` returns `None` (logged `ok=False`, `error="not found"`); non-JSON or non-zero exit returns `None` (logged with the first stderr line, scrubbed of anything after `?`); success logs `ProviderCall(provider="treg", op=<short op>, endpoint=endpoint, ok=True, cost_usd=<costUsd or catalog price>, ms=..., call_id=<from the location the spike recorded>)` and adds to `spent`; returns `output.data` (AnyAPI) or `output` (routed `treg.*`).
- `TregClient.review_all(useful: dict[str, str])`: for each logged call with a `call_id`, runs `treg review <id> <rating> --reason "<sanitized, under 200 chars>"` once; sets `ProviderCall.review`; a call never used gets `not_sure` (R-ING-3: review after use).
- `CATALOG_PRICES: dict[str, float]` with the seven endpoints in the M3-A table (catalog values 2026-10-09; the spike's actual costs are logged, these are only the pre-call cap estimate).
- `logged_in() -> bool` (issue 11): `treg balance --json`, exit 0 and JSON parse; any error or missing binary is `False`.
- `TregProvider(ContentProvider)`: `name="treg"`; `available()` = `shutil.which("treg")` and `logged_in()`; `PROVIDER = TregProvider()`.

- [ ] **Step 1: Failing tests** with a fake runner that serves the recorded M3-A fixtures by endpoint:

```python
def test_r_ing_3_every_used_call_is_reviewed(fake_runner): ...      # after enrich + review_all: one "treg review <id> ..." argv per logged call with call_id
def test_treg_not_found_and_bad_json_fall_through(fake_runner): ... # found:false -> None, ok False; stdout "oops" -> None, ok False; no exception
def test_treg_cost_cap_stops_calls(fake_runner): ...                 # max_cost_usd=0.004: thread (0.00375) runs, comments refused with error "cost cap";
                                                                      # sum(cost_usd) <= 0.004; route.fallbacks gains "treg: cost cap reached"
def test_logged_in_false_without_binary(monkeypatch): ...            # which("treg") None -> available() False, runner never called
def test_no_personal_data_in_argv(fake_runner): ...                  # every argv contains only the endpoint, the post URL or id, and fixed flags
```

  Write each body in full against the fake runner (`fake_runner(argv, **kw)` returns `CompletedProcess(argv, 0, stdout=<fixture json>, stderr="")` keyed by `argv[2]`).
- [ ] **Step 2-4:** FAIL, implement, PASS, commit `M4-A: treg client with call log, cost cap and review (R-ING-3)`.

### Task M4-A2: Enrichment and media fallback per platform

**Files:** Modify `src/skipwatch/providers/content_treg.py` (same package), `tests/unit/test_content_treg.py`

**Interfaces (`TregProvider.enrich(bundle, work, opts)`, by `bundle.source.platform`):**

| Platform | Calls (in order, each skipped when the cap would be exceeded) | Fills |
|---|---|---|
| x | `anyapi.twitter.thread` (url) | `context.thread` = texts of `tweets[1:]` by the author, in order; when the bundle is a text-only placeholder (issue 8), `source.kind="text"` and `post_text` = root tweet text |
| x | `treg.x.post.comments` (tweet_id, header `X-Treg-Route-Max-Cost: 0.01`) | `context.author_replies` = replies whose author handle equals the post author |
| x | links in thread and replies not yet fetched | `context.links` via `links.fetch_all` (free; same caps) |
| x | `anyapi.twitter.tweet_transcript` (url), only when `source.kind == "video"` | `transcript_hint = TranscriptHint(origin="treg:anyapi.twitter.tweet_transcript", text=...)` (R-ING-2) |
| youtube | `anyapi.youtube.video_transcript_full` only when `captions_available` is false | `transcript_hint` (origin `treg:anyapi.youtube.video_transcript_full`, text = joined segment text) |
| tiktok | `anyapi.tiktok.video_transcript_full` | `transcript_hint` |
| instagram | `anyapi.instagram.reel_transcript` only if the spike showed it within budget, else none | `transcript_hint` |
| facebook | `anyapi.facebook.post.detail` | `context.post_text` when the free route had none |

`fetch_media(bundle, work, opts)`: x: `tweets[0].media[].videoUrl` from the thread call (reusing the logged response, no second call); tiktok: `anyapi.tiktok.video_download` `videoUrl` (never `watermarkedUrl` when the clean one exists); instagram: `anyapi.instagram.post.detail` `videoUrl`; facebook: only if the spike found a media URL. Download the URL with `requests` (`stream=True`, 1 GB cap, no cookies) to `media/video.mp4`, probe it, return `MediaInfo`; on failure return `None` (the dispatcher then exits 3 listing `free...` and `treg...` attempts). `route.media = "treg"` and `route.fallbacks` gains `"free.yt-dlp.download: <reason>"` when the fallback served (8.3).

Text-only X under treg: M2-A's dispatcher calls `text.build`, which (Task M3-B2) asks enabled content providers for `build_text_x` before raising exit 7. `TregProvider.build_text_x(detected, work, opts) -> IngestBundle | None` calls `anyapi.twitter.thread` and returns a `kind="text"` bundle (root tweet as `post_text`, the rest as `thread`), or `None` when not found.

- [ ] Tests (fixtures from M3-A): `test_m4_x_enrich_fills_thread_replies_links_and_hint`, `test_m4_free_route_unchanged_when_disabled` (`--provider free`: zero treg argv, bundle equals the M3 bundle byte for byte after `write_model`), `test_treg_media_fallback_when_ytdlp_blocked` (fake `DownloadFailed` from the adapter, fake GET of `videoUrl`: `route.media == "treg"`, `fallbacks` has the free reason), `test_text_only_x_post_via_treg`, `test_r_ing_2_provider_transcript_never_primary` (after `transcribe`, `transcript.origin` is a Whisper or captions origin and the treg text is only in `cross_check`, see M4-B).
- [ ] FAIL, implement, PASS, commit `M4-A: treg enrichment and media fallback per platform (8.3)`.

### Task M4-A3: Doctor login detection

**Files:** Modify `src/skipwatch/doctor.py`; Create `tests/unit/test_doctor_treg.py`, `tests/live/test_live_treg.py`

- `probe_machine()` sets `treg_on_path` as before and a new probe attribute `treg_logged_in: bool | None` (None when not on PATH) from `content_treg.logged_in()`; `compute_tier` gives `3` only when `treg_logged_in` is true; the rendered line becomes `treg: logged in` or `treg: on PATH, not logged in: run treg login`. `Probe` is a dataclass in `doctor.py`, not a pydantic model, so no `models.py` change; `DoctorReport.components` carries it as `DoctorComponent(name="treg", found=..., detail=...)`.
- [ ] Tests: `test_tier_3_needs_treg_logged_in` (on PATH but `logged_in` False gives tier 1 with whisper), `test_r_doc_1_doctor_still_never_installs` (the M0 spy test passes with the new call, and the only network-capable call is `treg balance --json`). Live test (marker `live`): `skipwatch doctor --json` on Robert's machine reports tier `3`.
- [ ] Commit, push `git commit -m "M4-A: treg login detection in doctor" && git push -u origin m4/treg`

---

## Package M4-B: Cross-check (`m4/crosscheck`)

### Task M4-B1: Cross-check transcripts

**Files:** Create `src/skipwatch/crosscheck.py`, `tests/unit/test_crosscheck.py`; Modify `src/skipwatch/transcribe.py` (one hook after the transcript is built)

**Interfaces:** `similarity(a: str, b: str) -> float`: lowercase, strip punctuation, word lists, `difflib.SequenceMatcher(None, a_words, b_words, autojunk=False).ratio()`, rounded to 2 places. `attach(transcript: Transcript, hint: TranscriptHint) -> Transcript`: when `hint.text`, sets `cross_check = CrossCheck(origin=hint.origin, text=hint.text, similarity=similarity(" ".join(s.text for s in transcript.segments), hint.text))`; otherwise unchanged. Hook in `run_transcribe`: `transcript = attach(transcript, bundle.transcript_hint)` before writing, and also when the transcript came from cache (M2-E).

- [ ] Tests: identical text 1.0; disjoint text below 0.2; `test_r_tr_1_untimed_text_only_in_cross_check` (a hint never creates segments); `test_cross_check_written_by_transcribe` (CLI on a captions work folder with a hint in `ingest.json`). FAIL, implement, PASS, commit, push `git commit -m "M4-B: cross-check transcripts against provider text (R-ING-2)" && git push -u origin m4/crosscheck`.

---

## Package M4-C: Orchestrator M4 (`m4/orchestrator`)

### Task M4-C1: Provider calls and cost on the review screen; treg in platforms.md

**Files:** Modify `skills/skipwatch/SKILL.md`, `skills/skipwatch/references/run-protocol.md`, `skills/skipwatch/references/review-screen.md`, `skills/skipwatch/references/platforms.md`, `tests/unit/test_orchestrator_files.py`

- review-screen.md `Provider calls:` line: `none (free route)` | `treg: <n> calls, $<sum to 4 decimals> (<op list>)` | `treg: <n> calls, $<sum>, cached from <date>`; plus `Cross-check: <similarity> against <origin>` when `transcript.json` has one, and a warning line `Transcript and provider text disagree (similarity <x>)` when similarity is under 0.6.
- run-protocol.md: `--provider auto|free|treg` passthrough; the outline uses `context.thread` and `context.author_replies` (tag `[written]`), and `cross_check` only to flag disagreements, never as a step source; never prints the treg balance.
- platforms.md: a "treg (Tier 3)" subsection per platform listing which calls run and what they add, from M3-A's facts.
- [ ] Tests: phrases present ("Provider calls:", "treg:", "cross_check", "never as a step source"); line order of review-screen example still matches 4.3; under 300 lines; no em dash; `claude plugin validate --strict .` exit 0. Commit, push.

---

## M4 acceptance (merged M4 tree)

| # | "Done when" item | Exact command | Expected |
|---|---|---|---|
| 1 | Recorded fixtures cover both routes; unit suite | `uv run pytest tests/unit/test_content_treg.py tests/unit/test_crosscheck.py -v && bash scripts/ci_local.sh` | all pass; `CI-LOCAL: OK` |
| 2 | With treg enabled, G2's `ingest.json` has thread, replies and expanded links (live, under $0.05) | `W=$(mktemp -d)/w && uv run skipwatch ingest "$(jq -r '.videos[1].url' tests/golden/golden.json)" --work $W --provider treg --json > /dev/null && jq '{thread: (.context.thread\|length), replies: (.context.author_replies\|length), links: (.context.links\|length), calls: [.provider_calls[] \| select(.provider=="treg") \| {endpoint, ok, cost_usd, review}]}' $W/ingest.json` | `thread`, `replies` and `links` each at least the `expected.context` minimums for G2; every treg call has `review` set; total `cost_usd` under 0.05 |
| 3 | With treg disabled, the same run passes on the free route | `W2=$(mktemp -d)/w && uv run skipwatch ingest "<G2 url>" --work $W2 --provider free --json > /dev/null; echo $?; jq '[.provider_calls[] \| select(.provider=="treg")] \| length' $W2/ingest.json` | `0` then `0` |
| 4 | Doctor reports Tier 3 on Robert's machine | `uv run pytest -m live tests/live/test_live_treg.py -v` | pass |
| 5 | Review screen shows calls and cost (paid) | `uv run python scripts/golden_run.py --only G2 --out /tmp/sw-golden-treg` with `~/.skipwatch/config.toml` `[providers.treg] enabled = true` | `G2 PASS ...`; the run log contains a line starting `  Provider calls: treg:` |

Note for acceptance item 2: the minimums come from G2's `expected.context` in `golden.json` (Task M2-F1).

---

## Traceability

| Requirement | Task(s) | Test(s) |
|---|---|---|
| R-ING-1 (full post text, links fetched, 20k cap, context wins) | M2-B3, M3-B1, M3-B2, M3-C1, M3-D1 | `test_recorded_manual_fixture_builds_a_bundle` (post_text full), `test_r_ing_1_link_text_capped_at_20k`, `test_links_skip_private_hosts_and_binary`, `test_x_fixture_builds_video_bundle_with_full_text`, orchestrator phrase "context wins" |
| R-ING-2 (untimed provider transcript only as hint) | M4-A2, M4-B1 | `test_r_ing_2_provider_transcript_never_primary`, `test_r_tr_1_untimed_text_only_in_cross_check` |
| R-ING-3 (treg review after use) | M3-A1 (manual), M4-A1 | `test_r_ing_3_every_used_call_is_reviewed`; M4 acceptance #2 (`review` set) |
| R-ING-4 (1080 cap, smallest at or above 720) | M2-B2 | `test_r_ing_4_smallest_at_or_above_720_capped_at_1080`, `test_r_ing_4_vertical_uses_short_side`, `test_r_ing_4_below_720_takes_the_largest_available` |
| R-ING-5 (JS runtime order, cookies only by flag, manifest records) | M2-B2, M2-B3, M3-C1 | `test_r_ing_5_node_22_is_passed_explicitly`, `test_r_ing_5_old_node_and_no_deno_means_no_runtime`, `test_r_ing_5_cookies_only_from_the_flag`, `test_cookies_flag_sets_fetched_with_cookies` |
| R-ING-6 (exit 4 naming the cookie flag) | M2-B2, M2-B3, M3-C1 | `test_r_ing_6_error_classification`, `test_r_ing_6_login_required_is_exit_4_naming_the_flag`, `test_instagram_login_wall_is_exit_4_naming_cookie_flag` |
| R-TR-1 (timed only) | M2-C2, M2-D1, M4-B1 | `test_faster_maps_word_timestamps`, `test_openai_request_shape_and_mapping`, `test_r_tr_1_untimed_text_only_in_cross_check` |
| R-TR-2 (cloud only when named) | M2-A3, M2-D1, M2-G1 | `test_r_tr_2_auto_never_picks_a_cloud_backend`, `test_r_tr_2_cloud_needs_explicit_backend`, orchestrator phrase "only after the user said yes to that provider by name" |
| R-TR-3 (cache 7 days) | M2-E1 | `test_r_tr_3_transcript_reused_within_7_days`, `test_r_tr_3_cache_ignored_after_7_days`, `test_ingest_cache_skips_enrichment_but_not_media` |
| Resume (R-WORK-1, 3.4 Resume) | M2-E2, M2-G1, M2-H1 | `test_running_stage_counts_as_incomplete`, `test_newest_incomplete_skips_reviewed_runs`, `test_resume_after_killed_frames_completes` |
| Silent path (8.4) | M2-C2, M2-G1 | `test_silent_video_sets_silent_and_dense_frames`, orchestrator phrase "Silent video" |
| Whisper backends (8.4 order) | M2-A3, M2-C2 | `test_auto_prefers_mlx_on_apple_silicon_then_faster`, `test_whisper_missing_is_exit_8_with_extra_command`, `test_mlx_receives_an_array_not_a_path` |
| R-DET text kind (8.2: no media and over 200 words) | M2-B3, M3-B2 | `test_generic_unsupported_url_raises_no_media`, `test_text_page_over_200_words_becomes_text_kind`, `test_text_page_under_200_words_is_exit_7` |
| Exit 3 lists routes (section 15) | M2-A3, M4-A2 | `test_download_failed_without_providers_is_exit_3_listing_routes`, `test_treg_media_fallback_when_ytdlp_blocked` |
| Long video warning (3.4, 15) | M2-B4, M2-G1 | `test_probe_long_video_flag_over_60_minutes`, orchestrator phrase "Long video" |
| Media retention (3.4) | M2-G1 | orchestrator phrase test (delete `media/` after install unless `--keep-media`) |
| R-TIER-2 (degrade, never fail on optional deps) | M2-A3 (`--provider auto`), M2-G1 | `test_provider_treg_requested_but_missing_is_exit_8` (explicit only), orchestrator phrase |
| R-CLI-1, R-CLI-2 for new commands | M2-B4, M2-E2, M2-C1 | `test_probe_json_validates`, `test_resume_json_validates_and_exit_codes`, `test_extract_audio_is_reused` |
| R-ARCH-1 (network only in providers) | all | existing `test_arch.py` (yt_dlp, requests, socket only under `providers/`) |
| R-ARCH-2 (models and schemas) | M2-A1 | `test_r_arch_2_registry_covers_every_work_file`, `test_schemas.py` |
| S2, S3, S4, golden set (11.5) | M2-F1, M2-F2, acceptance | `test_golden_file.py`, `test_judge_*`, M2 acceptance #5 to #7, M3 acceptance #3 to #5 |
| M3 spike (8.3) | M3-A1 | `docs/spikes/2026-10-m3-spike.md`, balance before and after |
| M4 done-when (thread, replies, links; free route still passes; fixtures cover both) | M4-A1, M4-A2 | `test_m4_x_enrich_fills_thread_replies_links_and_hint`, `test_m4_free_route_unchanged_when_disabled`, M4 acceptance #2, #3 |

## Seams left for M5+

- `ProviderCall.review` and the cost sum feed the M5 confidence line and `list`.
- `fetched_with_cookies` is set in `ingest.json`; `pack` (M5) refuses such skills (section 10).
- `providers/registry.py` already discovers `content_*` modules, so an index provider (v1.1) and export providers (M6, `export_*`) follow the same pattern with a new prefix.
