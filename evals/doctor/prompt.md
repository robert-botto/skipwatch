---
# Runner note: doctor runs the engine through Bash, a gated tool. Run this case with
# --allow-tools 'Bash(uv run:*)' or the skill cannot call `uv run ... skipwatch doctor`.
max_turns: 8
timeout_seconds: 300
allowed_tools: [Skill, Bash, Read]
runs: 1
---
/skipwatch doctor
