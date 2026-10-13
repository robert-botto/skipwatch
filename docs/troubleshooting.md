# Troubleshooting

Start with `/skipwatch doctor`. It reports what this machine can do, warns about tools that are too old, and prints the exact command that installs the next missing piece.

When a run stops, SkipWatch prints one line, keeps the run's work folder and prints its path. The folder's `logs/` subfolder has the details, and `/skipwatch resume` continues from the stage that stopped without downloading again. Work folders of stopped runs can hold unredacted text from the video.

## Exit codes

The engine (`skipwatch`) and the plugin's wrapper script use these exit codes. Inside Claude Code the skill turns each one into a message; outside it, read the code and the engine's last stderr lines.

| Exit | Name | Meaning | What to do |
|---|---|---|---|
| 0 | `OK` | Success | Nothing. |
| 1 | `CHECK_FAILED` | A check failed (frontmatter, structure, provenance, style), or the staged draft changed after it was checked, or `cache --clear` could not remove a folder | Inside Claude Code the skill repairs the draft and checks again once; a second failure lists the items. Outside it, fix the listed items and run `check` again. |
| 2 | `UNSUPPORTED_SOURCE` | No adapter for the link, an unknown or unreadable file type, a folder that is not a SkipWatch work folder, or a skill name `pack` or `share` cannot find | Use a link to one video (not a channel or page listing) or a supported file. `/skipwatch list` shows the installed skill names. |
| 3 | `DOWNLOAD_FAILED` | The download failed on every route (stderr lists each route and its reason), a Whisper model could not be downloaded, or a pack URL could not be fetched | Check the network. If doctor says yt-dlp is old, run the update command it prints. For a Whisper model, run once with network access. |
| 4 | `PRIVATE_CONTENT` | The content is private or behind a login, or the skill was made with browser cookies and so cannot be packed or shared | If you can open it in your browser while logged in, re-run with `--cookies-from-browser <browser>`. |
| 5 | `SAFETY_FLAGS` | The check passed except for safety flags, such as a download piped into a shell | Read the flagged steps on the review screen. The skill installs only after your yes; `--yes` never installs a flagged skill. |
| 6 | `TARGET_EXISTS` | A skill with that name is already installed there | The review screen asks whether to replace it (the old copy goes to `~/.skipwatch/backups/`) or rename the new one. Outside Claude Code, pass `--force` to replace. |
| 7 | `NO_CONTENT` | Nothing usable: no video in the post, a page under 200 words, no transcript and no frames, or a work file that is missing or unreadable | See the platform notes below. For a damaged work folder, start a fresh run. |
| 8 | `MISSING_DEPENDENCY` | A required piece is missing: ffmpeg, the Whisper backend you asked for, a local Whisper when captions are missing or produce no timed segments, a cloud transcription key the provider rejected, or treg under `--provider treg` | Run the install command the engine printed. A missing transcriber never stops a run: it continues from the frames and the review screen offers the install. |
| 9 | `PACK_INTEGRITY` | A pack failed verification: a checksum or manifest mismatch, or the pack is too large | Do not install it. Get the pack again and compare its sha256 with the one its author posted. |
| 64 | `USAGE` | The engine refused the command: a malformed command, an invalid `--work` folder, a `--log` path outside the work folder's `logs/`, a `--home` that is not a `.skipwatch` folder, or a `--to` that is a symlink or inside the SkipWatch home | Fix the argument the message names and run it again. |
| 70 | `INTERNAL_ERROR` | A bug in the engine, not something you did. It prints one line, `skipwatch: internal error: <type>: <message>`, with secrets removed; the full traceback is in the stage's log in the work folder's `logs/` | Please report it with the files in the work folder's `logs/`. Running the engine yourself with `SKIPWATCH_DEBUG=1` prints the traceback too. |
| 78 | wrapper: no environment | The wrapper could not create the plugin's Python environment; the engine never ran | Run the `uv sync` command the wrapper printed once in a terminal, outside any sandbox, then try again. |
| 127 | wrapper: uv missing | uv is not installed and the environment was never set up; the engine never ran | Install uv (the wrapper prints how; SkipWatch never runs an installer itself), then try again. |

Exit 2 with stderr starting `error: ` comes from uv itself: the engine never started, and the stderr lines say why.

## uv, sandboxes and the environment

- **You just installed uv.** Retry right away; there is no need to restart Claude Code. The standalone installers put uv in `~/.local/bin` (older ones in `~/.cargo/bin`), which only new shells have on `PATH`, so the wrapper checks both folders itself.
- **uv older than 0.9.29 on macOS.** It can panic inside the macOS sandbox Claude Code uses for Bash commands, before Python starts. `/skipwatch doctor` warns about it and prints the upgrade command for the way you installed uv (Homebrew, pipx, pip or the standalone installer).
- **The first run is slow.** The plugin's SessionStart hook, or the first run, creates the Python environment with `uv sync`. Once it is in sync with the plugin's lockfile, later runs skip uv entirely.
- **The environment cannot be refreshed.** If a sync fails but an older environment exists, the wrapper says so and uses it. If none exists, it exits 78 with the command to run.
- **The home folder is not writable.** When a sandbox will not let a run write to `~/.skipwatch`, the run moves its work into `<project>/.skipwatch` (with a `.gitignore` of `*`) and notes it on the review screen.
- **ffmpeg.** SkipWatch uses the ffmpeg on your `PATH`. Without one, it downloads a static build of about 70 MB on first use. Doctor reports which one it found.

## Platform notes

The full per-platform reference, including what treg adds at Tier 3, is [platforms.md](../skills/skipwatch/references/platforms.md).

| Platform | Without cookies | Common failure and fix |
|---|---|---|
| Local files | Works. A `.vtt` or `.srt` sidecar named after the file is used as captions. | No captions and no Whisper: the run continues from frames only, so no step can be `[spoken]`. Install a Whisper backend with the command doctor prints. |
| YouTube | Works. yt-dlp needs a JavaScript runtime (node 22+ or deno) for the full format list; doctor reports it. | A private video, or an error that names `--cookies` (exit 4): re-run with `--cookies-from-browser <browser>`. |
| X | Works for a public video post. A post that links or quotes another video post uses that post's video and credits its author. | A text-only post exits 7 on the free route: enable treg (Tier 3) to read text posts. Protected posts exit 4. |
| TikTok | Works. | None seen logged out. |
| Instagram | Works for recent reels of a public profile; older ones may need cookies. | A login wall exits 4: re-run with `--cookies-from-browser <browser>`. |
| Facebook | Works for a public page's video. | Page listings such as `/<page>/videos` exit 2: use one video's link. A login wall exits 4. |
| Other sites | archive.org and Wikimedia Commons work. Vimeo usually needs a login. | "Unsupported URL" exits 2; for an article page the text route may still read it. |
| Text pages | Read by the text route. | Under 200 words exits 7. |

`--cookies-from-browser` is the only way SkipWatch ever uses cookies. A skill made with them cannot be packed or shared.

## treg (Tier 3)

treg is off by default and paid. `/skipwatch doctor` says when it is logged in but off. Exit 8 under `--provider treg` means treg is not installed or not logged in: run `treg login`, or re-run with `--provider free`. Under `--provider auto` a missing treg is skipped.

See also: [README](../README.md), [Privacy](../README.md#privacy), [What gets installed where](../README.md#what-gets-installed-where).
