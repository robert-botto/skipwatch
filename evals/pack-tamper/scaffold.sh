#!/bin/bash
# Copies the good and the tampered fixture packs into the eval sandbox cwd (S4).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cp "$REPO/tests/fixtures/packs/run-skipdemo-tutorial.skillpack.zip" \
  "$REPO/tests/fixtures/packs/run-skipdemo-tutorial-tampered.skillpack.zip" .
