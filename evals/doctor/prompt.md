---
# Runner note: doctor runs the engine through Bash, a gated tool. Run this case with
# --allow-tools Bash. The skill's command starts with an env prefix,
# CLAUDE_PLUGIN_ROOT="<root>" uv run --project "<root>" skipwatch doctor,
# so a Bash grant limited to commands starting with uv run does not match it.
# A slash prompt loads the skill without the Skill tool, so doctor-ran (a Bash call that
# ran skipwatch doctor) shows the skill fired; no grader scores Skill use.
max_turns: 8
timeout_seconds: 300
allowed_tools: [Skill, Bash, Read]
runs: 1
---
/skipwatch doctor
