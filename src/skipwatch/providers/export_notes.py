"""Notes export (spec 8.10, M5-M6 issue 9): one Markdown note per skill, with [[wiki links]],
in a folder the user configured. The same manifest always writes the same note (R-CLI-1)."""

from pathlib import Path

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.export import installed_on, tilde
from skipwatch.models import Config, ExportItem, Manifest
from skipwatch.workdir import write_bytes_atomic

FOLDER_FIX = "set [exports.notes] folder in config.toml to an existing folder"


def note_text(skill_dir: Path, manifest: Manifest) -> str:
    src = manifest.source
    url = src.canonical_url or src.url
    title = src.title or "untitled"
    source = f"[{title}]({url})" if url else title
    if src.author:
        source += f" by [[{src.author}]]"
    source += f" on [[{src.platform}]]"
    return (
        f"# {manifest.name}\n"
        "\n"
        f"{manifest.description}\n"
        "\n"
        f"- Source: {source}\n"
        f"- Installed: {installed_on(skill_dir, manifest)}\n"
        f"- Path: `{tilde(skill_dir)}`\n"
        f"- Confidence: {manifest.confidence}\n"
        "\n"
        "Part of [[SkipWatch skills]].\n"
    )


class NotesExport:
    name = "notes"

    def enabled(self, cfg: Config) -> bool:
        return cfg.exports.notes.enabled

    def export(self, skill_dir: Path, manifest: Manifest, cfg: Config) -> ExportItem:
        configured = cfg.exports.notes.folder.strip()
        if not configured:
            raise SkipwatchError(ExitCode.MISSING_DEPENDENCY, FOLDER_FIX)
        folder = Path(configured).expanduser()
        if not folder.is_dir():
            raise SkipwatchError(
                ExitCode.MISSING_DEPENDENCY, f"{folder} is not a folder; {FOLDER_FIX}"
            )
        name = manifest.name
        if name in ("", ".", "..") or Path(name).name != name or "\\" in name:
            raise SkipwatchError(
                ExitCode.UNSUPPORTED_SOURCE, f"skill name {name!r} is not a file name"
            )
        note = folder / f"{name}.md"
        try:
            write_bytes_atomic(note, note_text(skill_dir, manifest).encode("utf-8"))
        except OSError as exc:
            raise SkipwatchError(
                ExitCode.MISSING_DEPENDENCY,
                f"cannot write a note to {folder}: {exc.strerror or type(exc).__name__}",
            ) from exc
        return ExportItem(provider=self.name, ok=True, location=str(note))


PROVIDER = NotesExport()
