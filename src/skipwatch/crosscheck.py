"""Cross-check a timed transcript against a provider's untimed text (R-ING-2, 7.2).

The provider text is never the primary transcript (R-TR-1): it only lands in
transcript.json's cross_check, with a similarity the review screen can show.

Similarity is deterministic and linear in the text length: both texts are NFKC-normalized and
casefolded, split into word tokens (punctuation dropped), and scored as the Dice coefficient of
their word-bigram multisets, 2 * shared / (len(a) + len(b)), rounded to 2 places (unigrams when
a side has a single word). Bigrams keep local word order, so unrelated speech that shares
common words still scores low, while caption line breaks, no-break spaces, case and
punctuation do not count. difflib's SequenceMatcher over word lists was the first choice but
is quadratic: about 40 s on an hour of speech against unrelated text.

The disagreement warning also needs the overlap coefficient (shared / min(len(a), len(b)))
under the threshold, so an excerpt is not flagged; CrossCheck has no field for it, so it is
used for the warning only and transcript.json records Dice.

"""

import re
import unicodedata
from collections import Counter

from skipwatch.models import CrossCheck, Transcript, TranscriptHint

LOW_SIMILARITY = 0.6
_WORD = re.compile(r"\w+")


def _words(text: str) -> list[str]:
    return _WORD.findall(unicodedata.normalize("NFKC", text).casefold())


def _grams(words: list[str], n: int) -> Counter[tuple[str, ...]]:
    return Counter(tuple(words[i : i + n]) for i in range(len(words) - n + 1))


def _shared(a: str, b: str) -> tuple[int, int, int] | None:
    """(shared, size of a, size of b) over the n-gram multisets, or None when a side is empty."""
    a_words, b_words = _words(a), _words(b)
    if not a_words or not b_words:
        return None
    n = 2 if min(len(a_words), len(b_words)) >= 2 else 1
    a_grams, b_grams = _grams(a_words, n), _grams(b_words, n)
    return sum((a_grams & b_grams).values()), a_grams.total(), b_grams.total()


def similarity(a: str, b: str) -> float:
    """Dice: 2 * shared / (len(a) + len(b)). This is what transcript.json records."""
    counts = _shared(a, b)
    if counts is None:
        return 0.0
    shared, a_size, b_size = counts
    return round(2 * shared / (a_size + b_size), 2)


def overlap(a: str, b: str) -> float:
    """Overlap coefficient: shared / min(len(a), len(b)); 1.0 when one text is an excerpt."""
    counts = _shared(a, b)
    if counts is None:
        return 0.0
    shared, a_size, b_size = counts
    return round(shared / min(a_size, b_size), 2)


def attach(transcript: Transcript, hint: TranscriptHint) -> Transcript:
    """The transcript with cross_check from this run's hint; segments are never touched.

    No hint text means no cross_check, so a cached transcript never shows a stale one.
    """
    if not (hint.text and hint.text.strip()):
        return transcript.model_copy(update={"cross_check": None})
    timed_text = " ".join(s.text for s in transcript.segments)
    check = CrossCheck(
        origin=hint.origin, text=hint.text, similarity=similarity(timed_text, hint.text)
    )
    return transcript.model_copy(update={"cross_check": check})


def disagreement(transcript: Transcript) -> str | None:
    """The warning line when the two sources disagree, else None.

    Both Dice (the recorded similarity) and the overlap coefficient must be under 0.6, so a
    provider text that is only an excerpt of the transcript (a caption quoting one line) is
    not a disagreement even though its Dice score is tiny.
    """
    check = transcript.cross_check
    if check is None or check.similarity is None or check.similarity >= LOW_SIMILARITY:
        return None
    timed_text = " ".join(s.text for s in transcript.segments)
    if overlap(timed_text, check.text) >= LOW_SIMILARITY:
        return None
    return f"transcript sources disagree: {check.similarity:.2f}"
