---
# Runner note: doctor runs the engine through Bash, a gated tool. Run this case with
# --allow-tools "Bash(*/scripts/skipwatch *)". The skill runs the engine as
# "<plugin root>/scripts/skipwatch doctor", and that grant covers exactly the wrapper.
# A slash prompt loads the skill without the Skill tool, so doctor-ran (a Bash call that
# ran skipwatch doctor) shows the skill fired; no grader scores Skill use.
max_turns: 8
timeout_seconds: 300
allowed_tools: [Skill, Bash, Read]
runs: 3
---
/skipwatch doctor
