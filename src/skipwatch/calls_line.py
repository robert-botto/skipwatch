"""The review screen's `Provider calls:` line (skill audit 2 fix 17), built by `check` so the
skill copies it instead of doing the arithmetic. Format: review-screen.md "Provider calls"."""

from skipwatch.models import IngestBundle, ProviderCall
from skipwatch.providers.content_treg import CAP_REACHED

SHARED_PACK = "none (shared pack)"
FREE_ROUTE = "none (free route)"
MEDIA_OP = "media.get"
CAP_ERROR = "cost cap"


def _dollars(amount: float) -> str:
    """The cap as configured: at least two decimals (`0.05`), more only when set (`0.125`)."""
    text = f"{amount:.4f}".rstrip("0")
    return text + "0" * (2 - len(text.split(".")[1]))


def _item(call: ProviderCall) -> tuple[str, float]:
    """(how one treg row reads, what it adds to the total)."""
    if call.error == CAP_ERROR:
        return f"{call.op} refused (cost cap)", 0.0
    if call.op == MEDIA_OP:
        return f"{call.op} $0.0000", 0.0
    return f"{call.op} ${call.cost_usd:.4f}", call.cost_usd


def provider_calls_line(
    calls: list[ProviderCall], ingest: IngestBundle, max_cost_usd: float
) -> str:
    items = [_item(c) for c in calls if c.provider == "treg"]
    if items:
        total = sum(cost for _, cost in items)
        listed = ", ".join(text for text, _ in items)
        noun = "call" if len(items) == 1 else "calls"
        line = f"treg: {len(items)} {noun}, ${total:.4f} ({listed})"
    else:
        line = FREE_ROUTE
    if CAP_REACHED in ingest.route.fallbacks:
        line += f"; treg cost cap reached (${_dollars(max_cost_usd)})"
    if ingest.from_cache:
        when = ingest.cached_at[:10] if ingest.cached_at else "an earlier run"
        line += f"; cached from {when}"
    return line
