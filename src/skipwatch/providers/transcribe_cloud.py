"""Cloud transcription: OpenAI, Groq and Deepgram (8.4, R-TR-1, R-TR-2).

Never chosen under auto (cloud=True, auto_rank=None): the user names one with --backend.
Keys come only from OPENAI_API_KEY, GROQ_API_KEY and DEEPGRAM_API_KEY and never appear in a
message, a log line or a file. Audio goes up as 16 kHz mono 32 kbps MP3 in chunks of at most
50 minutes (OpenAI and Groq cap uploads at 25 MB); every time is offset by its chunk start.

Chunks are sent one after another. If chunk N fails, chunks 1 to N-1 were already billed and
their results are discarded; the stage fails and a rerun starts over (acceptable for v1).

Request and response shapes, checked 2026-10-09: OpenAI from the openai-python types (the
API reference page refuses fetchers), Groq from console.groq.com/docs/speech-to-text, Deepgram
from developers.deepgram.com (listen-pre-recorded reference and pre-recorded-audio guide).
"""

import bisect
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import IngestBundle, Segment, Transcript, TranscriptOrigin, Word
from skipwatch.workdir import WorkDir, read_model

TIMEOUT_S = 600
CHUNK_S = 3000  # 50 minutes: about 12 MB at 32 kbps, under the 25 MB upload cap
MP3_KBPS = 32
ERROR_DETAIL_CHARS = 200

# Whisper reports full language names in verbose_json ("english"); transcripts carry codes.
WHISPER_LANGUAGES = {
    "afrikaans": "af", "albanian": "sq", "amharic": "am", "arabic": "ar", "armenian": "hy",
    "assamese": "as", "azerbaijani": "az", "bashkir": "ba", "basque": "eu", "belarusian": "be",
    "bengali": "bn", "bosnian": "bs", "breton": "br", "bulgarian": "bg", "burmese": "my",
    "cantonese": "yue", "catalan": "ca", "chinese": "zh", "croatian": "hr", "czech": "cs",
    "danish": "da", "dutch": "nl", "english": "en", "estonian": "et", "faroese": "fo",
    "finnish": "fi", "french": "fr", "galician": "gl", "georgian": "ka", "german": "de",
    "greek": "el", "gujarati": "gu", "haitian creole": "ht", "hausa": "ha", "hawaiian": "haw",
    "hebrew": "he", "hindi": "hi", "hungarian": "hu", "icelandic": "is", "indonesian": "id",
    "italian": "it", "japanese": "ja", "javanese": "jw", "kannada": "kn", "kazakh": "kk",
    "khmer": "km", "korean": "ko", "lao": "lo", "latin": "la", "latvian": "lv",
    "lingala": "ln", "lithuanian": "lt", "luxembourgish": "lb", "macedonian": "mk",
    "malagasy": "mg", "malay": "ms", "malayalam": "ml", "maltese": "mt", "maori": "mi",
    "marathi": "mr", "mongolian": "mn", "nepali": "ne", "norwegian": "no", "nynorsk": "nn",
    "occitan": "oc", "pashto": "ps", "persian": "fa", "polish": "pl", "portuguese": "pt",
    "punjabi": "pa", "romanian": "ro", "russian": "ru", "sanskrit": "sa", "serbian": "sr",
    "shona": "sn", "sindhi": "sd", "sinhala": "si", "slovak": "sk", "slovenian": "sl",
    "somali": "so", "spanish": "es", "sundanese": "su", "swahili": "sw", "swedish": "sv",
    "tagalog": "tl", "tajik": "tg", "tamil": "ta", "tatar": "tt", "telugu": "te", "thai": "th",
    "tibetan": "bo", "turkish": "tr", "turkmen": "tk", "ukrainian": "uk", "urdu": "ur",
    "uzbek": "uz", "vietnamese": "vi", "welsh": "cy", "yiddish": "yi", "yoruba": "yo",
}  # fmt: skip


def language_code(name: str | None) -> str | None:
    """'english' or 'English' becomes 'en'; codes and unknown names pass through."""
    if name is None:
        return None
    return WHISPER_LANGUAGES.get(name.strip().lower(), name)


def audio_chunks(work: WorkDir) -> list[tuple[Path, float]]:
    """media/audio-16k.wav (M2-C), cut into MP3 chunks with their start offsets."""
    # M2-C; imported here so the registry never depends on it. Drop the ignore once M2-C merges.
    from skipwatch import audio  # pyright: ignore[reportAttributeAccessIssue]

    bundle = read_model(work.file("ingest.json"), IngestBundle)
    wav = audio.extract_audio(work, bundle)
    return audio.encode_mp3_chunks(wav, work.path / "media" / "chunks", CHUNK_S, MP3_KBPS)


def _redact(text: str, key: str) -> str:
    return text.replace(key, "[key]") if key else text


def _error_detail(response: Any, key: str) -> str:
    try:
        body = response.json()
        error = body.get("error") if isinstance(body, dict) else None
        detail = error.get("message", "") if isinstance(error, dict) else str(error or "")
        detail = detail or (body.get("err_msg", "") if isinstance(body, dict) else "")
    except ValueError:
        detail = response.text or ""
    return _redact(" ".join(str(detail).split()), key)[:ERROR_DETAIL_CHARS]


def _post(name: str, env: str, key: str, send: Callable[[], Any]) -> dict:
    """Run one request; map every failure to a clear SkipwatchError without the key."""
    try:
        response = send()
    except requests.Timeout as exc:
        raise SkipwatchError(
            ExitCode.DOWNLOAD_FAILED, f"{name} transcription failed: timed out after {TIMEOUT_S} s"
        ) from exc
    except requests.RequestException as exc:
        raise SkipwatchError(
            ExitCode.DOWNLOAD_FAILED,
            f"{name} transcription failed: could not reach {name} ({type(exc).__name__})",
        ) from exc
    status = response.status_code
    if status in (401, 403):
        raise SkipwatchError(ExitCode.MISSING_DEPENDENCY, f"{name} rejected the key in {env}")
    if status == 413:
        # chunks are sized to stay under every upload cap, so this is an engine bug
        raise SkipwatchError(
            ExitCode.INTERNAL_ERROR,
            f"{name} transcription failed: HTTP 413, an audio chunk broke the chunk contract "
            f"({CHUNK_S} s at {MP3_KBPS} kbps should fit the upload limit); "
            "this is a skipwatch bug",
        )
    if status == 429:
        raise SkipwatchError(
            ExitCode.DOWNLOAD_FAILED,
            f"{name} transcription failed: HTTP 429, rate limit or quota reached; retry later",
        )
    if status >= 500:
        raise SkipwatchError(
            ExitCode.DOWNLOAD_FAILED,
            f"{name} transcription failed: HTTP {status}, a {name} server error; retry later",
        )
    if status >= 400:
        detail = _error_detail(response, key)
        raise SkipwatchError(
            ExitCode.DOWNLOAD_FAILED, f"{name} transcription failed: HTTP {status} {detail}".strip()
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise SkipwatchError(
            ExitCode.DOWNLOAD_FAILED, f"{name} transcription failed: unreadable response"
        ) from exc
    if not isinstance(body, dict):
        raise SkipwatchError(
            ExitCode.DOWNLOAD_FAILED, f"{name} transcription failed: unreadable response"
        )
    return body


def _shift(segments: list[Segment], offset: float) -> list[Segment]:
    if not offset:
        return segments
    return [
        Segment(
            start=s.start + offset,
            end=s.end + offset,
            text=s.text,
            words=[Word(w=w.w, s=w.s + offset, e=w.e + offset) for w in s.words]
            if s.words is not None
            else None,
        )
        for s in segments
    ]


class _CloudBackend:
    name: str
    env: str
    default_model: str
    cloud = True
    auto_rank: int | None = None

    def _key(self) -> str:
        return os.environ.get(self.env, "").strip()

    def available(self, bundle: IngestBundle) -> bool:
        return bool(self._key())

    def missing_hint(self) -> str:
        return f"set {self.env}"

    def _model(self, model: str | None) -> str:
        return model or self.default_model

    def _request(self, chunk: Path, model: str, key: str) -> dict:
        raise NotImplementedError

    def _parse(self, body: dict) -> tuple[list[Segment], str | None]:
        raise NotImplementedError

    def transcribe(self, work: WorkDir, model: str | None) -> Transcript:
        key = self._key()
        if not key:
            raise SkipwatchError(
                ExitCode.MISSING_DEPENDENCY,
                f"backend {self.name} is not available: {self.missing_hint()}",
            )
        chosen = self._model(model)
        segments: list[Segment] = []
        language: str | None = None
        for chunk, offset in audio_chunks(work):
            body = self._request(chunk, chosen, key)
            try:
                parsed, lang = self._parse(body)
            except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
                raise SkipwatchError(
                    ExitCode.DOWNLOAD_FAILED,
                    f"{self.name} transcription failed: unreadable response from {self.name}",
                ) from exc
            segments.extend(_shift(parsed, offset))
            language = language or lang
        origin: TranscriptOrigin = self.name  # type: ignore[assignment]
        return Transcript(origin=origin, model=chosen, language=language, segments=segments)


class _WhisperApiBackend(_CloudBackend):
    """OpenAI-compatible /audio/transcriptions with verbose_json word and segment times."""

    url: str

    def _request(self, chunk: Path, model: str, key: str) -> dict:
        data = [
            ("model", model),
            ("response_format", "verbose_json"),
            ("timestamp_granularities[]", "word"),
            ("timestamp_granularities[]", "segment"),
        ]
        with chunk.open("rb") as fh:
            return _post(
                self.name,
                self.env,
                key,
                lambda: requests.post(
                    self.url,
                    headers={"Authorization": f"Bearer {key}"},
                    files={"file": (chunk.name, fh, "audio/mpeg")},
                    data=data,
                    timeout=TIMEOUT_S,
                ),
            )

    def _parse(self, body: dict) -> tuple[list[Segment], str | None]:
        kept = sorted(
            (s for s in body.get("segments") or [] if str(s["text"]).strip()),
            key=lambda s: float(s["start"]),
        )
        words: list[list[Word]] = [[] for _ in kept]
        if kept:
            for w in body.get("words") or []:
                index = _nearest(kept, float(w["start"]))
                words[index].append(Word(w=str(w["word"]).strip(), s=w["start"], e=w["end"]))
        segments = [
            Segment(start=s["start"], end=s["end"], text=str(s["text"]).strip(), words=ws or None)
            for s, ws in zip(kept, words, strict=True)
        ]
        return segments, language_code(body.get("language"))


def _nearest(segments: list[dict], at: float) -> int:
    """The segment whose span holds `at`; in a gap, the closer neighbour (ties go before).

    Runs after blank segments are dropped, so a word Whisper put in a blank one is kept.
    """
    starts = [float(s["start"]) for s in segments]
    index = max(bisect.bisect_right(starts, at) - 1, 0)
    if at <= float(segments[index]["end"]) or index + 1 == len(segments):
        return index
    before = at - float(segments[index]["end"])
    after = starts[index + 1] - at
    return index + 1 if after < before else index


class OpenAIBackend(_WhisperApiBackend):
    name = "openai"
    env = "OPENAI_API_KEY"
    default_model = "whisper-1"
    url = "https://api.openai.com/v1/audio/transcriptions"

    def _model(self, model: str | None) -> str:
        if model and model != self.default_model:
            raise SkipwatchError(
                ExitCode.USAGE,
                f"openai returns word and segment times only with whisper-1, not {model}",
            )
        return self.default_model


class GroqBackend(_WhisperApiBackend):
    name = "groq"
    env = "GROQ_API_KEY"
    default_model = "whisper-large-v3-turbo"
    url = "https://api.groq.com/openai/v1/audio/transcriptions"


class DeepgramBackend(_CloudBackend):
    name = "deepgram"
    env = "DEEPGRAM_API_KEY"
    default_model = "nova-3"
    url = "https://api.deepgram.com/v1/listen"

    def _request(self, chunk: Path, model: str, key: str) -> dict:
        params = {
            "model": model,
            "smart_format": "true",
            "punctuate": "true",
            "utterances": "true",
            "detect_language": "true",
        }
        headers = {"Authorization": f"Token {key}", "Content-Type": "application/octet-stream"}
        with chunk.open("rb") as fh:
            return _post(
                self.name,
                self.env,
                key,
                lambda: requests.post(
                    self.url, params=params, headers=headers, data=fh, timeout=TIMEOUT_S
                ),
            )

    def _parse(self, body: dict) -> tuple[list[Segment], str | None]:
        results = body.get("results") or {}
        channels = results.get("channels") or [{}]
        segments = [
            Segment(
                start=u["start"],
                end=u["end"],
                text=str(u["transcript"]).strip(),
                words=[
                    Word(w=str(w.get("punctuated_word") or w["word"]), s=w["start"], e=w["end"])
                    for w in u.get("words") or []
                ]
                or None,
            )
            for u in results.get("utterances") or []
            if str(u.get("transcript", "")).strip()
        ]
        return segments, channels[0].get("detected_language")


BACKENDS = (OpenAIBackend(), GroqBackend(), DeepgramBackend())
