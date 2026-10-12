"""treg content provider (spec 8.3, Tier 3): thread context, author replies, provider
transcripts as hints, and a media fallback when yt-dlp is blocked.

Per platform (plan Task M4-A2 and the decisions after the M3 spike):
- X: the thread's later posts by the author into context.thread, the author's own replies into
  context.author_replies (never anyone else's), the links in both fetched, and the untimed
  transcript as a hint for a video post. A text-only post becomes a `text` bundle through
  build_text_x. Media fallback: the thread's videoUrl.
- YouTube: the timed transcript as a hint, only when there are no captions.
- TikTok: the transcript as a hint; media fallback from video_download (clean URL first).
- Instagram: media fallback from post.detail only; its text always comes from the free route.
- Facebook: post text when the free route had none; never a media fallback (no media URL).
Media URLs expire (TikTok, Instagram), so each is downloaded right after its call, through the
same SSRF-checked, pinned transport links.py uses, with a size and time cap.

Everything goes through the treg CLI as a subprocess (`treg call`, `treg review`, `treg
balance`); nothing here speaks HTTP to treg. Each `treg call` prints its bill on stderr as
`treg: charged $<cost> · call id <hex>` (plan decision 5): the cost counts against the per-run
cap (`[providers.treg] max_cost_usd`, plan issue 9) and the call id is what `treg review`
rates once the run has used the result (R-ING-3). Reviews carry fixed reasons only, never
post content or anything about the user.
"""

import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
import urllib3

from skipwatch import media, runcache
from skipwatch.adapters.base import IngestOptions
from skipwatch.adapters.localfile import media_info
from skipwatch.adapters.x import canonical, post_id
from skipwatch.config import load_config
from skipwatch.detect import Detected, platform_for_host
from skipwatch.errors import SkipwatchError
from skipwatch.models import (
    IngestBundle,
    IngestContext,
    MediaInfo,
    ProviderCall,
    Route,
    SourceInfo,
    TranscriptHint,
    TregConfig,
)
from skipwatch.providers import links
from skipwatch.workdir import WorkDir

Runner = Callable[..., subprocess.CompletedProcess]

# Pre-call estimates for the cap (catalog, 2026-10-09; TikTok transcript 2026-10-11). What a
# call actually cost is read from its stderr line. The routed comments call is estimated at its
# X-Treg-Route-Max-Cost ceiling, the most it can be billed.
CATALOG_PRICES: dict[str, float] = {
    "anyapi.twitter.thread": 0.00375,
    "treg.x.post.comments": 0.01,
    "anyapi.twitter.tweet_transcript": 0.0012,
    "anyapi.tiktok.video_download": 0.0012,
    "anyapi.instagram.post.detail": 0.0015,
    "anyapi.facebook.post.detail": 0.002,
    "anyapi.youtube.video_transcript_full": 0.00308,
    "anyapi.tiktok.video_transcript_full": 0.0176,
}
OPS: dict[str, str] = {
    "anyapi.twitter.thread": "x.thread",
    "treg.x.post.comments": "x.comments",
    "anyapi.twitter.tweet_transcript": "x.transcript",
    "anyapi.tiktok.video_download": "tiktok.download",
    "anyapi.instagram.post.detail": "instagram.detail",
    "anyapi.facebook.post.detail": "facebook.detail",
    "anyapi.youtube.video_transcript_full": "youtube.transcript",
    "anyapi.tiktok.video_transcript_full": "tiktok.transcript",
}
REVIEW_REASONS: dict[str, str] = {
    "useful": "Result used to build the video's context for a how-to extraction.",
    "not_sure": "Result fetched but not needed in this run.",
    "not_useful": "Call returned nothing usable.",
}
CALL_TIMEOUT_S = 60
REVIEW_TIMEOUT_S = 20
LOGIN_TIMEOUT_S = 10
CAP_REACHED = "treg: cost cap reached"
# a whole number only: "$0,00375" or "$.004" must not read as a smaller charge
_CHARGED = re.compile(r"charged \$(\d+(?:\.\d+)?(?:e-?\d+)?)(?![\d.,])", re.IGNORECASE)
_MENTIONS_CHARGE = re.compile(r"\bcharged\b(?! by the original call)", re.IGNORECASE)
_CALL_ID = re.compile(r"call id ([0-9a-f]{8,})", re.IGNORECASE)
_REPLAY = "nothing new charged"
NOT_FOUND = "not found"
THREAD = "anyapi.twitter.thread"
COMMENTS = "treg.x.post.comments"
COMMENTS_HEADERS = {"X-Treg-Route-Max-Cost": "0.01"}
X_TRANSCRIPT = "anyapi.twitter.tweet_transcript"
YOUTUBE_TRANSCRIPT = "anyapi.youtube.video_transcript_full"
TIKTOK_TRANSCRIPT = "anyapi.tiktok.video_transcript_full"
TIKTOK_DOWNLOAD = "anyapi.tiktok.video_download"
INSTAGRAM_DETAIL = "anyapi.instagram.post.detail"
FACEBOOK_DETAIL = "anyapi.facebook.post.detail"
MEDIA_MAX_BYTES = 1_000_000_000
MEDIA_DEADLINE_S = 600.0
MEDIA_TYPES = ("video/", "application/octet-stream", "binary/octet-stream")
_REPLY_PREFIX = re.compile(r"^(?:@\w+\s+)+")


DISABLE_ENV = "SKIPWATCH_TREG_DISABLED"  # "1": behave as if treg were not installed (tests)


def _treg_path() -> str | None:
    """The treg CLI, or None when it is not on PATH or SKIPWATCH_TREG_DISABLED=1. The variable
    reaches subprocesses too, so a test running the real CLI can never spend money."""
    if os.environ.get(DISABLE_ENV) == "1":
        return None
    return shutil.which("treg")


def logged_in(runner: Runner | None = None) -> bool:
    """`treg balance --json` answers (plan issue 11): a free call that needs a valid login.
    The output is parsed only to prove it is JSON and then dropped; nothing is kept."""
    exe = _treg_path()
    if exe is None:
        return False
    try:
        out = (runner or subprocess.run)(
            [exe, "balance", "--json", "--limit", "1"],
            capture_output=True,
            text=True,
            timeout=LOGIN_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if out.returncode != 0:
        return False
    try:
        return isinstance(json.loads(out.stdout or ""), dict)
    except ValueError:
        return False


def _first_line(text: str) -> str:
    """The first stderr line with any query string cut off (signed URLs, tokens)."""
    line = next((ln.strip() for ln in (text or "").splitlines() if ln.strip()), "")
    if "?" in line:
        line = line[: line.index("?") + 1]
    return line[:200] or "failed"


class Unparsable(Exception):
    """A stderr line speaks of a charge SkipWatch cannot read."""


def _charged(stderr: str) -> float | None:
    """The sum of every `charged $X` line (a replay is 0), None when no line mentions a
    charge; Unparsable when one does but its amount is not a plain number."""
    total, seen = 0.0, False
    for line in (stderr or "").splitlines():
        if "charged" not in line.lower():
            continue
        seen = True
        if _REPLAY in line:
            continue
        amounts = _CHARGED.findall(line)
        if len(amounts) != len(_MENTIONS_CHARGE.findall(line)) or not amounts:
            raise Unparsable(line)
        total += sum(float(amount) for amount in amounts)
    return total if seen else None


def _body_cost(body: Any) -> float | None:
    if not isinstance(body, dict):
        return None
    if isinstance(body.get("costUsd"), int | float):
        return float(body["costUsd"])
    routed = body.get("_treg")
    if isinstance(routed, dict) and isinstance(routed.get("charged_micro"), int | float):
        return routed["charged_micro"] / 1_000_000
    return None


def _payload(body: Any) -> tuple[Any, str | None]:
    """(data, error): AnyAPI bodies give output.data, routed `treg.*` ones give output."""
    if not isinstance(body, dict) or not isinstance(body.get("output"), dict):
        return None, "unexpected response"
    output = body["output"]
    if output.get("found") is False:
        return None, NOT_FOUND
    if "found" in output:
        data = output.get("data")
        return (data, None) if data else (None, NOT_FOUND)
    return output, None


class TregClient:
    """One run's treg calls: the call log, the money spent and the cap, reviews after use.

    A request made twice in one run (the text adapter and then enrichment both read the X
    thread) is answered from the log, so it is billed once.
    """

    def __init__(
        self, max_cost_usd: float, runner: Runner = subprocess.run, exe: str | None = None
    ):
        self.max_cost_usd = max_cost_usd
        self.runner = runner
        self.exe = exe or _treg_path() or "treg"
        self.calls: list[ProviderCall] = []
        self.spent = 0.0
        self.capped = False
        self._answers: dict[str, Any] = {}
        self._used: set[str] = set()

    def _log(self, endpoint: str, started: float | None, **fields: Any) -> None:
        ms = 0 if started is None else max(0, int((time.monotonic() - started) * 1000))
        self.calls.append(
            ProviderCall(provider="treg", op=OPS[endpoint], endpoint=endpoint, ms=ms, **fields)
        )

    def _argv(
        self, endpoint: str, body: dict | None, query: dict | None, headers: dict | None
    ) -> list[str]:
        argv = [self.exe, "call", endpoint]
        if body is not None:
            argv += ["--method", "POST", "--data", json.dumps(body)]
        for key, value in (query or {}).items():
            argv += ["--query", f"{key}={value}"]
        for key, value in (headers or {}).items():
            argv += ["--header", f"{key}: {value}"]
        return argv

    def call(
        self,
        endpoint: str,
        *,
        body: dict | None = None,
        query: dict | None = None,
        headers: dict | None = None,
    ) -> Any:
        """The response's data, or None (not found, failed, or refused by the cost cap)."""
        estimate = CATALOG_PRICES.get(endpoint)
        if estimate is None:
            raise ValueError(f"{endpoint} has no catalog price; add it before calling it")
        key = json.dumps([endpoint, body, query], sort_keys=True)
        if key in self._answers:
            return self._answers[key]
        if self.spent + estimate > self.max_cost_usd + 1e-9:
            self.capped = True
            # informational, like a not-found answer: the run went as configured, so the
            # bundle stays cacheable and a rerun bills nothing (R-TR-3)
            self._log(endpoint, None, ok=True, error="cost cap")
            return None
        started = time.monotonic()
        try:
            out = self.runner(
                self._argv(endpoint, body, query, headers),
                capture_output=True,
                text=True,
                timeout=CALL_TIMEOUT_S,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.spent += estimate  # it may have been billed: count the worst case
            self._log(endpoint, started, ok=False, error="timeout")
            self._answers[key] = None
            return None
        except OSError as exc:
            self._log(endpoint, started, ok=False, error=type(exc).__name__)
            self._answers[key] = None
            return None
        stderr = out.stderr or ""
        call_id_match = _CALL_ID.search(stderr)
        call_id = call_id_match.group(1) if call_id_match else None
        parsed: Any = None
        if out.returncode != 0:
            data, error = None, _first_line(stderr)
        else:
            try:
                parsed = json.loads(out.stdout or "")
            except ValueError:
                data, error = None, "not JSON"
            else:
                data, error = _payload(parsed)
        try:
            cost = _charged(stderr)
        except Unparsable:
            cost = estimate  # never trust a partial number: count the worst case
        if cost is None:
            cost = _body_cost(parsed)
        if cost is None:  # no word on the bill: assume it was paid unless clearly not
            cost = estimate if data is not None or out.returncode != 0 else 0.0
        self.spent += cost
        # A not-found answer is an outcome, not a failure: ok, with the note in error, so the
        # run cache keeps it and a rerun does not ask (and pay) again. Genuine errors (exit
        # status, unreadable output, timeouts) stay ok=False and are asked again next run.
        self._log(
            endpoint,
            started,
            ok=data is not None or error == NOT_FOUND,
            cost_usd=cost,
            call_id=call_id,
            error=error,
        )
        self._answers[key] = data
        return data

    def use(self, endpoint: str) -> None:
        """Mark an endpoint's result as used by the run; review_all rates it useful."""
        self._used.add(endpoint)

    def _rating(self, call: ProviderCall) -> str:
        if not call.ok or call.error == NOT_FOUND:
            return "not_useful"
        return "useful" if call.endpoint in self._used else "not_sure"

    def review_all(self) -> None:
        """R-ING-3: `treg review` once per logged call that has a call id and no review yet.
        A review that fails leaves `review` unset; it never fails the run."""
        reviewed = []
        for call in self.calls:
            if call.call_id is None or call.review is not None:
                reviewed.append(call)
                continue
            rating = self._rating(call)
            argv = [self.exe, "review", call.call_id, rating, "--reason", REVIEW_REASONS[rating]]
            try:
                out = self.runner(
                    argv, capture_output=True, text=True, timeout=REVIEW_TIMEOUT_S, check=False
                )
            except (OSError, subprocess.SubprocessError):
                reviewed.append(call)
                continue
            ok = out.returncode == 0
            reviewed.append(call.model_copy(update={"review": rating}) if ok else call)
        self.calls = reviewed


def _max_cost() -> float:
    """The per-run cap from config (plan issue 9); the default when config is unreadable."""
    try:
        return load_config().providers.treg.max_cost_usd
    except ValueError:
        return TregConfig().max_cost_usd


# ---- the media fallback download ----


DEADLINE_MESSAGE = "over the media download deadline"


def _stream(response: requests.Response, part: Path, deadline: float) -> None:
    size = 0
    with part.open("wb") as out:
        while True:
            if time.monotonic() >= deadline:
                raise links.Refused(DEADLINE_MESSAGE)
            chunk = response.raw.read1(links.CHUNK, decode_content=False)
            if not chunk:
                break
            size += len(chunk)
            if size > MEDIA_MAX_BYTES:
                raise links.Refused("over the 1 GB media cap")
            out.write(chunk)


def download_media(url: str, dest: Path) -> None:
    """A plain GET of a provider media URL into dest: no cookies, no environment credentials,
    every hop SSRF-checked and pinned (links.get_vetted), at most 1 GB and 10 minutes. Raises
    links.Refused or a requests error; a partial file is never left at dest."""
    deadline = time.monotonic() + MEDIA_DEADLINE_S
    response = links.get_vetted(url, deadline)
    part = dest.with_name(dest.name + ".part")
    try:
        if response.status_code != 200:
            raise links.Refused(f"HTTP {response.status_code}")
        mime = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if not mime.startswith(MEDIA_TYPES):
            raise links.Refused(f"not a video: {mime or '(no type)'}")
        length = response.headers.get("Content-Length")
        if length and length.isdigit() and int(length) > MEDIA_MAX_BYTES:
            raise links.Refused("over the 1 GB media cap")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            _stream(response, part, deadline)
        except (urllib3.exceptions.HTTPError, requests.RequestException, OSError) as exc:
            # a cut connection, a stalled read, or the watchdog closing the socket at the
            # deadline: an expired URL or a flaky CDN, never a crash
            if time.monotonic() >= deadline - links.WATCHDOG_SLACK_S:
                raise links.Refused(DEADLINE_MESSAGE) from exc
            raise links.Refused(type(exc).__name__) from exc
        os.replace(part, dest)
    finally:
        links.close_vetted(response)
        part.unlink(missing_ok=True)


def _probe_media(work: WorkDir, path: Path) -> MediaInfo:
    info = media_info(path, media.probe(path))
    return info.model_copy(update={"path": path.relative_to(work.path).as_posix()})


# ---- response helpers ----


def _handle(value: str | None) -> str:
    return (value or "").lstrip("@").casefold()


def _tweets(thread: Any) -> list[dict]:
    tweets = thread.get("tweets") if isinstance(thread, dict) else None
    return [t for t in tweets or [] if isinstance(t, dict)]


def _root(tweets: list[dict], wanted: str | None) -> dict | None:
    return next((t for t in tweets if wanted and str(t.get("id")) == wanted), None)


def _text(item: dict) -> str:
    return str(item.get("text") or "").strip()


def _segments_text(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    segments = [s for s in data.get("segments") or [] if isinstance(s, dict)]
    joined = " ".join(str(s.get("text") or "").strip() for s in segments).strip()
    return joined or (str(data.get("transcript") or "").strip() or None)


def _posted(seconds: Any) -> str | None:
    if not isinstance(seconds, int | float):
        return None
    stamp = datetime.fromtimestamp(seconds, UTC).isoformat(timespec="seconds")
    return stamp.replace("+00:00", "Z")


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _new_links(texts: list[str], known: list[str], room: int, calls, budget) -> list[str]:
    """Links in the author's posts worth fetching: t.co resolved, X pages dropped (a
    JavaScript shell), ones already fetched skipped, at most `room`."""
    found: list[str] = []
    for text in texts:
        for url in links.extract_urls(text):
            target = links.resolve(url, calls, budget) if _host(url) == "t.co" else url
            if not target or platform_for_host(_host(target)) == "x":
                continue
            if target not in known and target not in found:
                found.append(target)
    return found[:room]


class TregProvider:
    name = "treg"

    def __init__(self, runner: Runner = subprocess.run):
        self.runner = runner
        self._runs: dict[str, TregClient] = {}
        self._available: bool | None = None  # one login check per run; finish resets it

    def available(self) -> bool:
        if self._available is None:
            self._available = _treg_path() is not None and logged_in(self.runner)
        return self._available

    def _client(self, work: WorkDir) -> TregClient:
        """One client per run (work folder): fetch_media or build_text_x, then enrich, share
        the cap and the log, and enrich hands every call to the bundle."""
        key = str(work.path)
        if key not in self._runs:
            self._runs[key] = TregClient(_max_cost(), runner=self.runner)
        return self._runs[key]

    # ---- X ----

    def _thread(self, client: TregClient, url: str) -> Any:
        return client.call(THREAD, body={"url": url})

    def build_text_x(
        self, detected: Detected, work: WorkDir, opts: IngestOptions
    ) -> IngestBundle | None:
        """A text-only X post (plan issue 8): the post as post_text, the author's later posts
        in the thread as thread. None when treg does not return the post."""
        wanted = post_id(detected.value)
        if wanted is None:
            return None
        url = canonical(wanted)
        cookies = opts.cookies_from_browser is not None
        placeholder = IngestBundle(
            source=SourceInfo(kind="text", platform="x", url=detected.value, canonical_url=url),
            route=Route(context="treg", media=None),
        )
        # a text post has no media to fetch first, so a fresh cached run answers before any
        # call: the thread is never billed twice within the cache window (R-TR-3)
        hit = runcache.cached_ingest(placeholder, [self.name], cookies)
        if hit is not None:
            return hit
        client = self._client(work)
        tweets = _tweets(self._thread(client, url))
        root = _root(tweets, wanted)
        if root is None:
            return None
        client.use(THREAD)
        handle = root.get("authorHandle")
        return IngestBundle(
            source=SourceInfo(
                kind="text",
                platform="x",
                url=detected.value,
                canonical_url=url,
                author=f"@{handle}" if handle else None,
                author_name=root.get("authorName") or None,
                posted_at=_posted(root.get("createdUtc")),
            ),
            context=IngestContext(post_text=_text(root) or None),
            route=Route(context="treg", media=None),
        )

    def _enrich_x(self, bundle: IngestBundle, client: TregClient) -> IngestBundle:
        source, context = bundle.source, bundle.context
        url = source.canonical_url or source.url or ""
        wanted = post_id(url)
        tweets = _tweets(self._thread(client, canonical(wanted) if wanted else url))
        root = _root(tweets, wanted) or (tweets[0] if tweets else None)
        author = _handle(source.author) or _handle((root or {}).get("authorHandle"))
        thread_ids = {str(t.get("id")) for t in tweets}
        # privacy: with no known author nothing can be attributed, so nothing is kept
        later = tweets[tweets.index(root) + 1 :] if root is not None and author else []
        continuations = [
            _text(t) for t in later if _handle(t.get("authorHandle")) == author and _text(t)
        ]
        thread = list(context.thread)
        added = [t for t in continuations if t not in thread]
        if added:
            client.use(THREAD)
        if source.kind == "text" and not context.post_text and root is not None:
            context = context.model_copy(update={"post_text": _text(root) or None})
        replies: list[str] = []
        if wanted is not None and author:
            comments = client.call(COMMENTS, body={"tweet_id": wanted}, headers=COMMENTS_HEADERS)
            items = comments.get("comments") if isinstance(comments, dict) else None
            for item in items or []:
                if not isinstance(item, dict) or _handle(item.get("authorHandle")) != author:
                    continue
                if str(item.get("id")) in thread_ids | {wanted}:
                    continue  # a continuation, already in the thread
                # the leading @handles address other people: drop them, keep the words
                text = _REPLY_PREFIX.sub("", _text(item)).strip()
                if text and text not in context.author_replies and text not in replies:
                    replies.append(text)
            if replies:
                client.use(COMMENTS)
        calls = list(bundle.provider_calls)
        known = [link.url for link in context.links]
        room = links.MAX_LINKS - len(known)
        budget = links.Budget()
        fresh = _new_links([*added, *replies], known, room, calls, budget) if room > 0 else []
        fetched = links.fetch_urls(fresh, calls, budget) if fresh else []
        context = context.model_copy(
            update={
                "thread": [*thread, *added],
                "author_replies": [*context.author_replies, *replies],
                "links": [*context.links, *fetched],
            }
        )
        bundle = bundle.model_copy(update={"context": context, "provider_calls": calls})
        if source.kind == "video":
            bundle = self._hint(bundle, client, X_TRANSCRIPT, {"url": url}, "transcript")
        return bundle

    # ---- other platforms ----

    def _hint(
        self, bundle: IngestBundle, client: TregClient, endpoint: str, body: dict, field: str
    ) -> IngestBundle:
        """R-ING-2: a provider transcript is only ever a hint (later a cross-check)."""
        if bundle.transcript_hint.text:
            return bundle
        data = client.call(endpoint, body=body)
        if not isinstance(data, dict):
            return bundle
        text = (_segments_text(data) if field == "segments" else str(data.get(field) or "")) or ""
        if not text.strip():
            return bundle
        client.use(endpoint)
        hint = TranscriptHint(origin=f"treg:{endpoint}", text=text.strip())
        return bundle.model_copy(update={"transcript_hint": hint})

    def _enrich_facebook(self, bundle: IngestBundle, client: TregClient) -> IngestBundle:
        if bundle.context.post_text:
            return bundle
        url = bundle.source.canonical_url or bundle.source.url
        data = client.call(FACEBOOK_DETAIL, body={"url": url})
        text = str(data.get("text") or "").strip() if isinstance(data, dict) else ""
        if not text:
            return bundle
        client.use(FACEBOOK_DETAIL)
        context = bundle.context.model_copy(update={"post_text": text})
        return bundle.model_copy(update={"context": context})

    def enrich(self, bundle: IngestBundle, work: WorkDir, opts: IngestOptions) -> IngestBundle:
        client = self._client(work)
        platform = bundle.source.platform
        url = bundle.source.canonical_url or bundle.source.url or ""
        if platform == "x":
            bundle = self._enrich_x(bundle, client)
        elif platform == "youtube" and not bundle.context.captions_available:
            body = {"url": url, "captionKind": "any"}
            bundle = self._hint(bundle, client, YOUTUBE_TRANSCRIPT, body, "segments")
        elif platform == "tiktok" and bundle.source.kind == "video":
            bundle = self._hint(bundle, client, TIKTOK_TRANSCRIPT, {"url": url}, "segments")
        elif platform == "facebook":
            bundle = self._enrich_facebook(bundle, client)
        # instagram: post text only ever comes from the free route (plan decision 3)
        route = bundle.route
        if client.capped and CAP_REACHED not in route.fallbacks:
            route = route.model_copy(update={"fallbacks": [*route.fallbacks, CAP_REACHED]})
        return bundle.model_copy(update={"route": route})

    def finish(self, work: WorkDir, bundle: IngestBundle | None) -> list[ProviderCall]:
        """End of run, on every exit path: review every call (R-ING-3) and hand the log to
        ingest, which writes it to provider_calls and calls.json; then forget the run."""
        self._available = None
        client = self._runs.pop(str(work.path), None)
        if client is None:
            return []
        client.review_all()
        return list(client.calls)

    # ---- media fallback ----

    def _media_url(self, bundle: IngestBundle, client: TregClient) -> tuple[str, str | None]:
        """(endpoint, media URL) for the platforms treg can download; Facebook has none."""
        platform = bundle.source.platform
        url = bundle.source.canonical_url or bundle.source.url or ""
        if platform == "x":
            wanted = post_id(url)
            tweets = _tweets(self._thread(client, canonical(wanted) if wanted else url))
            root = _root(tweets, wanted) or (tweets[0] if tweets else {})
            videos = [m.get("videoUrl") for m in root.get("media") or [] if isinstance(m, dict)]
            return THREAD, next((v for v in videos if v), None)
        if platform == "tiktok":
            data = client.call(TIKTOK_DOWNLOAD, body={"url": url})
            data = data if isinstance(data, dict) else {}
            return TIKTOK_DOWNLOAD, data.get("videoUrl") or data.get("watermarkedUrl")
        if platform == "instagram":
            data = client.call(INSTAGRAM_DETAIL, body={"url": url})
            return INSTAGRAM_DETAIL, data.get("videoUrl") if isinstance(data, dict) else None
        return "", None

    def fetch_media(
        self, bundle: IngestBundle, work: WorkDir, opts: IngestOptions
    ) -> MediaInfo | None:
        if bundle.source.platform not in ("x", "tiktok", "instagram"):
            return None  # Facebook: treg exposes no media URL (plan decision 4)
        client = self._client(work)
        endpoint, url = self._media_url(bundle, client)
        if not url:
            return None
        dest = work.path / "media" / "video.mp4"
        started = time.monotonic()
        error = None
        found = None
        try:
            download_media(url, dest)
            found = _probe_media(work, dest)
        except links.Refused as exc:
            error = str(exc)
        except (requests.RequestException, urllib3.exceptions.HTTPError, OSError) as exc:
            error = type(exc).__name__  # backstop: a media failure never ends ingest
        except SkipwatchError:
            error = "downloaded file is not playable media"
        if found is None:
            dest.unlink(missing_ok=True)
        else:
            client.use(endpoint)
        ms = max(0, int((time.monotonic() - started) * 1000))
        client.calls.append(
            ProviderCall(
                provider="treg",
                op="media.get",
                ok=found is not None,
                ms=ms,
                endpoint=_host(url) or None,
                error=error,
            )
        )
        return found


PROVIDER = TregProvider()
