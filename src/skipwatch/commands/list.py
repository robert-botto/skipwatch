from pathlib import Path

import typer

from skipwatch.listing import scan
from skipwatch.models import ListedSkill
from skipwatch.output import emit_json, progress
from skipwatch.runner import run_command


def _line(skill: ListedSkill) -> str:
    if skill.problem is not None:
        return f"{skill.name}  ?  {skill.problem}  {skill.scope}  {skill.path}"
    title = skill.title or "untitled"
    author = skill.author or "unknown"
    date = (skill.extracted_at or "?")[:10]
    confidence = skill.confidence or "?"
    return f'{skill.name}  {confidence}  "{title}" by {author}  {date}  {skill.scope}  {skill.path}'


def _list(json_out: bool) -> int:
    result = scan(Path.cwd(), Path.home())
    if not result.skills:
        progress("No SkipWatch skills installed.")
    for skill in result.skills:
        progress(_line(skill))
    if json_out:
        emit_json(result)
    return 0


def register(app: typer.Typer) -> None:
    @app.command("list")
    def _cmd(json_out: bool = typer.Option(False, "--json", help="Print the result as JSON.")):
        """List installed SkipWatch skills, reading only each skill's skipwatch.json."""
        run_command(lambda: _list(json_out))
