"""Export an installed skill to Mem0 or a notes folder (spec 8.10, M5-M6 issues 8 and 9).

Without a provider name every provider enabled in config runs; a named provider runs even when
disabled (an explicit request). Re-exporting an unchanged skill is a no-op (R-CLI-1):
$SKIPWATCH_HOME/exports.json remembers (provider, name, sha256 of skipwatch.json).
"""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from skipwatch import installs
from skipwatch.config import skipwatch_home
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.manifest import MANIFEST_NAME
from skipwatch.models import (
    Config,
    ExportItem,
    ExportLog,
    ExportLogEntry,
    ExportResult,
    Manifest,
)
from skipwatch.output import progress
from skipwatch.providers.registry import export_providers
from skipwatch.workdir import read_model, write_model

EXPORTS = "exports.json"
UNCHANGED = "unchanged since last export"


def tilde(path: Path) -> str:
    """The resolved path with the home folder written as ~, so no export names the user."""
    path = path.resolve()
    try:
        rel = path.relative_to(Path.home().resolve())
    except ValueError:
        return path.as_posix()
    return "~" if rel == Path() else f"~/{rel.as_posix()}"


def installed_on(skill_dir: Path, manifest: Manifest) -> str:
    """The install date from the install log, else the date the skill was made."""
    folder = installs.resolved(str(skill_dir))
    for record in installs.load().installs:
        if folder is not None and installs.resolved(record.path) == folder:
            return record.installed_at[:10]
    return manifest.extracted_at[:10]


def _load_log() -> ExportLog:
    path = skipwatch_home() / EXPORTS
    if not path.exists():
        return ExportLog()
    try:
        return read_model(path, ExportLog)
    except (OSError, ValidationError, ValueError) as exc:
        progress(f"ignoring {path}: {exc.__class__.__name__}")
        return ExportLog()


def _save_log(log: ExportLog) -> None:
    home = skipwatch_home()
    home.mkdir(parents=True, exist_ok=True)
    write_model(home / EXPORTS, log)


def run_exports(skill_dir: Path, provider: str | None, cfg: Config, now: datetime) -> ExportResult:
    """Export one installed skill. Raises the first provider's SkipwatchError after logging the
    providers that succeeded before it."""
    path = skill_dir / MANIFEST_NAME
    try:
        data = path.read_bytes()
        manifest = Manifest.model_validate_json(data)
    except (OSError, ValidationError, ValueError) as exc:
        raise SkipwatchError(ExitCode.UNSUPPORTED_SOURCE, f"{path} is not readable") from exc
    registered = export_providers()
    if provider is not None:
        if provider not in registered:
            known = ", ".join(registered) or "none"
            raise SkipwatchError(
                ExitCode.USAGE, f"unknown export provider {provider} (known: {known})"
            )
        chosen = [registered[provider]]
    else:
        chosen = [p for p in registered.values() if p.enabled(cfg)]

    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    stamp = now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    log = _load_log()
    result = ExportResult(name=manifest.name)
    exported = False
    try:
        for p in chosen:
            key = (p.name, manifest.name)
            if any((e.provider, e.name, e.manifest_sha256) == (*key, digest) for e in log.entries):
                result.results.append(
                    ExportItem(provider=p.name, ok=True, skipped=True, detail=UNCHANGED)
                )
                continue
            item = p.export(skill_dir, manifest, cfg)
            result.results.append(item)
            entry = ExportLogEntry(
                provider=p.name,
                name=manifest.name,
                manifest_sha256=digest,
                ref=item.location,
                exported_at=stamp,
            )
            kept = [e for e in log.entries if (e.provider, e.name) != key]
            log = ExportLog(entries=[*kept, entry])
            exported = True
    finally:
        if exported:  # a later provider's failure keeps the earlier exports remembered
            _save_log(log)
    return result
