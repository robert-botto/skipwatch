# Changelog

All notable changes to SkipWatch are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - unreleased

First release.

### Added

- `/skipwatch <url or path>` turns a tutorial video into an installed Agent Skill whose steps cite where in the video they came from.
- Sources: links from YouTube, X, TikTok, Instagram and Facebook, any other site yt-dlp supports, local screen recordings and audio files (with an optional `.srt` or `.vtt` sidecar), and text-only posts with the pages they link to.
- Transcription from captions first, then local Whisper (mlx-whisper on Apple silicon, faster-whisper elsewhere), or a cloud provider (OpenAI, Groq or Deepgram) only after you say yes to that provider by name.
- Frame sampling once a second with still screens collapsed and near-duplicates dropped, read by `frame-reader` agents that copy commands, code and settings as shown.
- Provenance tags on every step: `[spoken mm:ss]`, `[on-screen mm:ss]`, `[written]` and `[inferred]`, each checked against the transcript, the frame notes or the post.
- Checks for provenance, redaction, safety, style and structure, with API keys, tokens and passwords replaced by placeholders and risky commands flagged on the review screen.
- A `skill-critic` review of the draft (skip it with `--fast`) and an optional `skill-tester` run in a scratch folder (`--test`).
- A review screen before anything is installed; `--yes` installs only when nothing is flagged.
- Install scopes: user (`~/.claude/skills`), `--project`, `--agents`, and `--to <dir>`, with a backup when an installed skill is replaced.
- `list`, `pack`, `install` and `share`: list your skills, write a checksummed `.skillpack.zip`, install a pack after verification, checks and your review, and print a thank-you post that credits the creator.
- `doctor` reports the capability tier and what to install next; `resume` continues an interrupted run; `cache` shows or clears cached downloads and old work folders.
- Optional treg content provider (`--provider treg`), off unless you enable it.
- `--cookies-from-browser` for private content you can open in your browser, `--thorough` for more frames, `--keep-media`, `--no-frames` and `--name`.
- The `skipwatch` engine runs without Claude Code through `uvx skipwatch` or `uv tool install skipwatch`.
- `export` writes a pointer to an installed skill to Mem0 or a notes folder, from `[exports]` in `config.toml`; re-exporting an unchanged skill does nothing unless you pass `--force`.
- The first run offers to install local Whisper once, never under `--yes`.
- A Claude Code plugin with a SessionStart hook that syncs the plugin's Python environment with uv.
- Example skills under `examples/`, a troubleshooting guide with every exit code, and a design spec.
