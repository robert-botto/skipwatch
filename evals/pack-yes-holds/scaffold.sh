#!/bin/bash
# Copies the good fixture pack into the eval sandbox cwd (S4).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cp "$REPO/tests/fixtures/packs/run-skipdemo-tutorial.skillpack.zip" .
