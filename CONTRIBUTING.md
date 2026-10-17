# Contributing to SkipWatch

Thanks for helping. This page covers setup, how changes are made, and how to add a platform, a transcription backend or an export provider.

## Setup

You need Python 3.11 or newer and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
uv sync --dev
bash scripts/ci_local.sh
```

`scripts/ci_local.sh` runs the same steps as CI (ruff, pyright, the schema and version checks, and the unit tests with a coverage floor). It prints `CI-LOCAL: OK` only if every step passes. Run it before you open a PR.

## Branches and commits

- Work on a branch and open a PR against `main`. Do not push to `main`.
- One logical change per commit, with a clear message. Prefer several small commits over one large one.
- Behaviour changes update the [design spec](docs/superpowers/specs/2026-10-09-skipwatch-design.md) first, then the code.
- No em dash character in code, comments, docs, commit messages or PR text. No personal data (home paths, email addresses) in any file.

## Tests: red first

Write the test first and watch it fail for the right reason, then write the code and watch it pass (spec 11.3). A check that cannot fail is worse than no check, so for a new check show that it fails when the bug is present. Paste the failing test output into your PR.

Tests never touch the real `~/.skipwatch` or `~/.claude/skills`. Use temporary folders and the `SKIPWATCH_HOME` override. Tests marked `live` use the network and are skipped by default.

## Requirement IDs

The spec numbers its requirements (for example `R-ING-6`). Every PR lists the requirement IDs it covers. A change with no matching requirement adds one to the spec in the same PR.

## Adding a platform adapter

An adapter turns one platform's URLs into an `IngestBundle`. Create `src/skipwatch/adapters/<name>.py` that defines `PLATFORMS` and `ADAPTER` at module level. The registry (`adapters/registry.py`) finds it; nothing else changes.

```python
from skipwatch.adapters.base import IngestOptions
from skipwatch.detect import Detected
from skipwatch.models import IngestBundle
from skipwatch.workdir import WorkDir

PLATFORMS = ("example",)  # the platform names detect.py returns for this adapter


class ExampleAdapter:
    def build(self, detected: Detected, work: WorkDir, opts: IngestOptions) -> IngestBundle:
        # Fetch metadata and media into `work`, then return the bundle.
        # A login or private-content error raises SkipwatchError(ExitCode.PRIVATE_CONTENT).
        ...


ADAPTER = ExampleAdapter()
```

Then:

1. Teach `detect.py` to recognise the platform's URL shapes.
2. Record a scrubbed fixture with `SKIPWATCH_LIVE=1 uv run python scripts/record_fixture.py <url> --name <slug> --platform <name>` (add `--captions` for a caption track). It stores metadata only, never media, and scrubs IPs, tokens and emails. Read every recorded file before you commit it.
3. Add `tests/unit/test_adapter_<name>.py` that builds a bundle from the fixture with no network.

## Adding a transcription backend

Create `src/skipwatch/providers/transcribe_<name>.py` that defines `BACKENDS`, a tuple of backend objects. Import heavy libraries inside `transcribe()`, not at module level.

```python
from skipwatch.models import IngestBundle, Transcript
from skipwatch.workdir import WorkDir


class ExampleBackend:
    name = "example"
    cloud = False  # True only for a backend that sends audio to a provider
    auto_rank: int | None = None  # order under auto; None keeps it out of auto

    def available(self, bundle: IngestBundle) -> bool: ...

    def transcribe(self, work: WorkDir, model: str | None) -> Transcript: ...

    def missing_hint(self) -> str:
        return "uv sync --extra example"  # the install command or env var shown for exit 8


BACKENDS = (ExampleBackend(),)
```

A cloud backend (`cloud = True`) must never run without the user's explicit yes naming the provider. Add tests for `available`, `transcribe` and `missing_hint`.

## Adding an export provider

Create `src/skipwatch/providers/export_<name>.py` that defines `PROVIDER`.

```python
from pathlib import Path

from skipwatch.models import Config, ExportItem, Manifest


class ExampleExport:
    name = "example"

    def enabled(self, cfg: Config) -> bool: ...  # the [exports.example] enabled flag

    def export(self, skill_dir: Path, manifest: Manifest, cfg: Config) -> ExportItem:
        # Raise SkipwatchError(MISSING_DEPENDENCY) for a missing key or folder and
        # SkipwatchError(DOWNLOAD_FAILED) for a network failure.
        # Never print or return a secret.
        ...


PROVIDER = ExampleExport()
```

## Running the evals

The evals under `evals/` run the plugin through `claude plugin eval`. They cost money, so run them only when you need to. Run them from a clean export, because worktrees under `.worktrees/` pollute case discovery:

```bash
E=$(mktemp -d) && git archive HEAD | tar -x -C "$E" && cd "$E" && uv sync --dev
claude plugin eval . --trust-plugin --scaffold --allow-tools Bash Write --case local-fixture \
  --runs 1 --threshold 0.8 --no-publish --max-cost-usd 20 < /dev/null
```

`--case` takes one glob and is not repeatable, so run one case (or one glob such as `'pack-*'`) per invocation. Bash and Write are gated tools, which is why cases that run the pipeline need `--allow-tools`. Each case's `case.yaml` starts with a comment on how to run it.

## Maintainers

After three merged PRs you are invited to become a maintainer.

## Conduct and security

By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Report vulnerabilities as described in [SECURITY.md](SECURITY.md), not in a public issue.
