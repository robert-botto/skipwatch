#!/bin/bash
# Copies the fixture video and its captions into the eval sandbox cwd (plan issue 6).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cp "$REPO/tests/fixtures/tutorial-60s.mp4" "$REPO/tests/fixtures/tutorial-60s.en.vtt" .
