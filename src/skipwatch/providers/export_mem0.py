"""Mem0 export (spec 8.10, M5-M6 issue 8): one pointer memory per skill, never the procedure.

The key comes only from MEM0_API_KEY and appears in no message, log line or exception: errors
name the HTTP status or the exception class, and are raised without their cause.
"""

import os
from pathlib import Path

import requests

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.export import installed_on, tilde
from skipwatch.models import Config, ExportItem, Manifest

ADD_URL = "https://api.mem0.ai/v3/memories/add/"
TIMEOUT_S = 20
AGENT_ID = "skipwatch"


def pointer_text(skill_dir: Path, manifest: Manifest) -> str:
    """Where the skill is and what it is for; the steps stay in the skill."""
    src = manifest.source
    url = src.canonical_url or src.url
    title = f'"{src.title}"' if src.title else "a video"
    by = f" by {src.author}" if src.author else ""
    where = f" ({url})" if url else ""
    posted = f", posted {src.posted_at[:10]}" if src.posted_at else ""
    purpose = manifest.description.strip().rstrip(".")
    return (
        f"SkipWatch skill {manifest.name} installed {installed_on(skill_dir, manifest)}"
        f" at {tilde(skill_dir)}. Purpose: {purpose}."
        f" Source: {title}{by}{where}{posted}."
    )


def _failed(reason: str) -> SkipwatchError:
    return SkipwatchError(ExitCode.DOWNLOAD_FAILED, f"Mem0 export failed: {reason}")


class Mem0Export:
    name = "mem0"

    def enabled(self, cfg: Config) -> bool:
        return cfg.exports.mem0.enabled

    def export(self, skill_dir: Path, manifest: Manifest, cfg: Config) -> ExportItem:
        key = os.environ.get("MEM0_API_KEY", "").strip()
        if not key:
            raise SkipwatchError(ExitCode.MISSING_DEPENDENCY, "set MEM0_API_KEY to export to Mem0")
        mem0 = cfg.exports.mem0
        body = {
            "messages": [{"role": "user", "content": pointer_text(skill_dir, manifest)}],
            "metadata": {
                "project": mem0.tag,
                "skill": manifest.name,
                "source_url": manifest.source.canonical_url or manifest.source.url,
            },
            "infer": False,
            **({"user_id": mem0.user_id} if mem0.user_id else {"agent_id": AGENT_ID}),
        }
        headers = {"Authorization": f"Token {key}", "Accept": "application/json"}
        try:
            response = requests.post(ADD_URL, headers=headers, json=body, timeout=TIMEOUT_S)
        except requests.RequestException as exc:
            raise _failed(type(exc).__name__) from None  # the exception text may hold headers
        if response.status_code in (401, 403):
            raise SkipwatchError(
                ExitCode.MISSING_DEPENDENCY, "Mem0 rejected the key in MEM0_API_KEY"
            )
        if not 200 <= response.status_code < 300:
            raise _failed(f"HTTP {response.status_code}")
        try:
            event_id = response.json().get("event_id")
        except (ValueError, AttributeError):
            event_id = None
        location = f"mem0 event {event_id}" if event_id else "mem0"
        return ExportItem(provider=self.name, ok=True, location=location)


PROVIDER = Mem0Export()
