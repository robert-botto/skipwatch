"""treg content provider (spec 8.3, Tier 3): thread context, author replies, provider
transcripts as hints, and a media fallback when yt-dlp is blocked.

Everything goes through the treg CLI as a subprocess (`treg call`, `treg review`, `treg
balance`); nothing here speaks HTTP to treg. Each `treg call` prints its bill on stderr as
`treg: charged $<cost> · call id <hex>` (plan decision 5): the cost counts against the per-run
cap (`[providers.treg] max_cost_usd`, plan issue 9) and the call id is what `treg review`
rates once the run has used the result (R-ING-3). Reviews carry fixed reasons only, never
post content or anything about the user.
"""

import json
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from typing import Any

from skipwatch.models import ProviderCall

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
_CHARGED = re.compile(r"charged \$(\d+(?:\.\d+)?(?:e-?\d+)?)", re.IGNORECASE)
_CALL_ID = re.compile(r"call id ([0-9a-f]{8,})", re.IGNORECASE)
_REPLAY = "nothing new charged"


def _treg_path() -> str | None:
    return shutil.which("treg")


def logged_in(runner: Runner = subprocess.run) -> bool:
    """`treg balance --json` answers (plan issue 11): a free call that needs a valid login.
    The output is parsed only to prove it is JSON and then dropped; nothing is kept."""
    exe = _treg_path()
    if exe is None:
        return False
    try:
        out = runner(
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


def _charged(stderr: str) -> float | None:
    if _REPLAY in (stderr or ""):
        return 0.0
    match = _CHARGED.search(stderr or "")
    return float(match.group(1)) if match else None


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
        return None, "not found"
    if "found" in output:
        data = output.get("data")
        return (data, None) if data else (None, "not found")
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
            self._log(endpoint, None, ok=False, error="cost cap")
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
        cost = _charged(stderr)
        if cost is None:
            cost = _body_cost(parsed)
        if cost is None:
            cost = estimate if data is not None else 0.0
        self.spent += cost
        self._log(
            endpoint,
            started,
            ok=data is not None,
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
        if not call.ok:
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


class TregProvider:
    name = "treg"

    def __init__(self, runner: Runner = subprocess.run):
        self.runner = runner

    def available(self) -> bool:
        return _treg_path() is not None and logged_in(self.runner)


PROVIDER = TregProvider()
