<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/hero-dark.svg">
  <img src="docs/assets/hero.svg" alt="SkipWatch. Paste a video. Claude knows kung fu." width="100%">
</picture>

A Claude Code plugin that turns a tutorial video into an installed Agent Skill,<br>
with every step traced to the moment in the video it came from.

[![ci](https://github.com/robert-botto/skipwatch/actions/workflows/ci.yml/badge.svg)](https://github.com/robert-botto/skipwatch/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-3b82f6?style=flat-square)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab?style=flat-square&logo=python&logoColor=white)](pyproject.toml)
[![Claude Code plugin](https://img.shields.io/badge/Claude_Code-plugin-d97757?style=flat-square)](.claude-plugin/plugin.json)

[Install](#install) · [Use it](#use-it) · [How it works](#how-it-works) · [What you get](#what-you-get) · [Capability tiers](#capability-tiers) · [Privacy](#privacy) · [FAQ](#faq)

<code>/skipwatch &lt;video link&gt;</code>

<br>

<img src="docs/demo/demo.gif" alt="A real /skipwatch run on a TypeScript tip posted on X: the review screen, then the installed skill" width="100%">

</div>

---

## Why

Tutorial videos are a slow way to learn a workflow. You pause, rewind, squint at a terminal, and type the command by hand. Then next month you watch it again.

SkipWatch watches it once for you. It reads the captions or transcribes the audio, looks at the frames, and writes a skill Claude can use from then on. Every step says where it came from, so you can check it. Nothing is installed until you say yes.

## Features

**Any tutorial source**

- Links from YouTube, X, TikTok, Instagram and Facebook, plus any other site yt-dlp supports.
- Local screen recordings and audio files (`.mp4`, `.mov`, `.mkv`, `.webm`, `.mp3`, `.m4a` and more), with an `.srt` or `.vtt` sidecar if you have one.
- Text-only posts, and the READMEs, gists and docs pages a post links to.

**Reads the video, not just the words**

- Captions first. No captions: local Whisper (mlx-whisper on Apple silicon, faster-whisper elsewhere).
- Key frames sampled at scene changes, with near-duplicates dropped.
- `frame-reader` agents read the frames and copy commands, code and settings exactly as shown.

**Skills you can check**

- Every step carries one tag: `[spoken mm:ss]`, `[on-screen mm:ss]`, `[written]` or `[inferred]`. The check matches each quote against the transcript, the frame notes or the post.
- API keys, tokens and passwords are redacted before anything is written.
- Risky commands, such as piping a download into a shell, are flagged on the review screen. They are never hidden.
- Text in the video is data, never instructions. Nothing from the video runs during a run.
- Nothing installs until you say yes on the review screen.

**Keep and share**

- `list` shows every SkipWatch skill you installed.
- `pack` writes a `.skillpack.zip` with a checksum for every file. `install` verifies the pack before it writes anything.
- `share` writes a thank-you post that credits the creator.
- `resume` continues an interrupted run without downloading again.
- Replacing an installed skill makes a backup first.

## Install

Inside Claude Code:

```text
/plugin marketplace add robert-botto/skipwatch
/plugin install skipwatch@skipwatch
```

Or from a terminal, in one line:

```bash
claude plugin install skipwatch --marketplace robert-botto/skipwatch
```

Then run your first video:

```text
/skipwatch https://www.youtube.com/watch?v=<id>
```

The only requirement is [uv](https://docs.astral.sh/uv/getting-started/installation/). SkipWatch sets up its own Python environment the first time a session starts. You never run pip or create a virtualenv.

To pin a specific version:

```bash
claude plugin marketplace add robert-botto/skipwatch#v0.1.0
```

> [!NOTE]
> SkipWatch 0.1.0 is not released yet. These install lines work once the repository is public.

## Use it

```text
/skipwatch <url or path> [flags]      turn a video into a skill
/skipwatch doctor                     what this machine can do, and what to install next
/skipwatch list                       the SkipWatch skills you installed
/skipwatch pack <skill>               a .skillpack.zip to share
/skipwatch install <pack or url>      install someone else's pack, after checks and your review
/skipwatch share <skill>              a ready-to-post thank-you that credits the creator
/skipwatch resume                     continue an interrupted run
```

Flags:

| Flag | Effect |
|---|---|
| `--project` | install scope `project` (`./.claude/skills/<name>`) |
| `--agents` | install scope `agents` (`./.agents/skills/<name>`) |
| `--to <dir>` | install into `<dir>/<name>`; wins over the scopes |
| `--name <skill-name>` | skill name and work folder slug, instead of deriving them |
| `--thorough` | more frames: 5 per minute, up to 150 |
| `--yes` | install without the prompt, but only when safety flags, gaps and name collisions are all zero |
| `--keep-media` | keep the downloaded media after a successful install |
| `--no-frames` | no `assets/frames/` in the generated skill (the readers still read frames) |
| `--provider free\|treg\|auto` | content providers for a URL; `auto` uses treg too when you are logged in; `free` never makes a paid call |
| `--cookies-from-browser <browser>` | read private or login-only content you can open in that browser; the only way cookies are ever used |
| `--fast` | skip the critic; confidence is then at most `medium` |
| `--test` | test-run the skill before the review screen |
| `--lang source` | accepted; it has no effect in this version |

## How it works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/how-it-works-dark.svg">
  <img src="docs/assets/how-it-works.svg" alt="The pipeline: your link, ingest, transcribe and frames, read by frame-reader agents, distill, critique by skill-critic, check (provenance, redaction, safety, style, structure), review, install, your skill" width="100%">
</picture>

A deterministic engine (`skipwatch`, Python) does the mechanical work: download, transcribe, sample frames, check, install. Claude does the reading and writing in your session. `frame-reader` agents read the frames in parallel, and `skill-critic` reviews the draft. Claude itself never looks at a frame image, so untrusted pixels stay out of the session that can run commands.
