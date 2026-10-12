#!/bin/bash
# Copies the critic-work fixture (a run paused before the critic) into the sandbox cwd as
# ./.skipwatch/work/critic-demo, with the fixture video it was made from (issue 19).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
W=".skipwatch/work/critic-demo"
mkdir -p .skipwatch/work
printf '*\n' > .skipwatch/.gitignore
cp -R "$REPO/tests/fixtures/critic-work" "$W"
mkdir -p "$W/logs"
cp "$REPO/tests/fixtures/tutorial-60s.mp4" "$REPO/tests/fixtures/tutorial-60s.en.vtt" .
for f in run.json ingest.json source.json; do
  sed "s|__CWD__|$PWD|g" "$W/$f" > "$W/$f.tmp" && mv "$W/$f.tmp" "$W/$f"
done
