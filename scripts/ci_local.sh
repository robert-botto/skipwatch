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

whisper_model_cached() {
  uv run --no-sync python -c "import sys; from huggingface_hub import scan_cache_dir as s; \
sys.exit('Systran/faster-whisper-small' not in {r.repo_id for r in s().repos})" >/dev/null 2>&1
}

# Keep the Whisper extras this venv already has: a bare `uv sync --dev` would remove them.
extras=()
uv run --no-sync python -c "import faster_whisper" >/dev/null 2>&1 && extras+=(--extra whisper)
uv run --no-sync python -c "import mlx_whisper" >/dev/null 2>&1 && extras+=(--extra mlx)
step uv sync --dev ${extras[@]+"${extras[@]}"}
step uv run ruff check .
step uv run ruff format --check .
step uv run pyright
step uv run python scripts/export_schemas.py --check
step uv run python scripts/check_versions.py
step uv run pytest -m "not pipeline and not live" --cov --cov-report=term --cov-fail-under=85
# The pipeline job, when this machine has ffmpeg (no static-ffmpeg download here).
if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
  step uv run pytest -m "pipeline and not whisper and not live" -v
  # The whisper job, when the extras and the faster-whisper small model are here (no download).
  if [ ${#extras[@]} -gt 0 ] && whisper_model_cached; then
    step uv run pytest -m "pipeline and whisper and not live" -v
  else
    echo "Whisper extras or model not found; skipping Whisper pipeline tests" >&2
  fi
else
  echo "ffmpeg not found; skipping pipeline tests" >&2
fi
if command -v claude >/dev/null 2>&1; then
  step claude plugin validate --strict .
  step claude plugin validate --strict .claude-plugin/plugin.json
else
  echo "claude CLI not found; skipping plugin validate" >&2
fi
echo "CI-LOCAL: OK"
