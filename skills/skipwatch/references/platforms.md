# Platforms

What each source kind needs and how it fails. M1 supports local files only; the other
headings are placeholders filled by later milestones.

## Local files (M1)

Local files: sidecar captions `<stem>.vtt|.srt|.<lang>.vtt|.<lang>.srt`; no captions means Tier 1 is needed (Whisper, M2).

- Extensions are matched case-insensitively (`.MOV`, `.M4A`, `.webm` all work).
- A sidecar whose `<lang>` starts with `en` is preferred, then a plain `<stem>.vtt` or
  `<stem>.srt`. yt-dlp writes the `<stem>.<lang>.vtt` form.
- The original file is read in place; it is never copied into the work folder, moved or
  deleted.
- Paths with spaces and non-ASCII characters are normal (macOS names screen recordings
  `Screen Recording 2026-10-09 at 14.02.11.mov`); quote them in every command.
- Without captions and without Whisper the run degrades to frames only: steps can be
  `[on-screen]`, `[written]` or `[inferred]`, never `[spoken]`, and the review screen
  names the install command.

## YouTube (M2)

## Generic yt-dlp URLs (M2)

## X (M3)

## TikTok (M3)

## Instagram (M3)

## Facebook (M3)

## Text posts (M3)
