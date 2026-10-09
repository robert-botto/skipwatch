#!/usr/bin/env bash
# Runs the same steps as .github/workflows/ci.yml on this machine.
# Prints "CI-LOCAL: OK" only if every step passes; stops at the first failure.
set -euo pipefail
cd "$(dirname "$0")/.."

step() {
  echo "==> $*" >&2
  if ! "$@"; then
    echo "CI-LOCAL: FAILED at: $*" >&2
    exit 1
  fi
}

step uv sync --dev
step uv run ruff check .
step uv run ruff format --check .
step uv run pyright
step uv run python scripts/export_schemas.py --check
step uv run python scripts/check_versions.py
step uv run pytest -m "not pipeline" --cov --cov-report=term --cov-fail-under=85
if command -v claude >/dev/null 2>&1; then
  step claude plugin validate --strict .
  step claude plugin validate --strict .claude-plugin/plugin.json
else
  echo "claude CLI not found; skipping plugin validate" >&2
fi
echo "CI-LOCAL: OK"
