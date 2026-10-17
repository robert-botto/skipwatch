# Platforms

## Contents

- treg (Tier 3)
- Local files
- YouTube
- Generic yt-dlp URLs
- X
- TikTok
- Instagram
- Facebook
- Pages with no video

What each source kind needs without cookies, how it fails, and the exact line to tell the
user. The engine makes every download and every provider call; you never run yt-dlp or
`treg` yourself. The `treg (Tier 3)` notes apply only when treg is on: `--provider treg`,
or `[providers.treg] enabled = true` in `config.toml` (off by default).

## treg (Tier 3)

- treg is opt-in and paid. `auto` is the free route unless `config.toml` has
  `[providers.treg] enabled = true` (default `false`; doctor then reports
  `treg: logged in, off: set [providers.treg] enabled = true in config.toml, or pass --provider treg`).
  `--provider treg` forces it, `--provider free` never calls it. The engine makes, logs
  and caps every call to treg. Never run `treg` yourself or print its balance.
- Exit 8 under `--provider treg`: quote
  `` treg is not installed or not logged in: run `treg login` ``, then
  `or re-run with --provider free.` Under `auto` the engine skips a missing treg.
- `treg: cost cap reached` in `route.fallbacks` of `ingest.json`: add
  `, treg cost cap reached` to the ingest progress line.

## Local files

Local files: sidecar captions `<stem>.vtt|.srt|.<lang>.vtt|.<lang>.srt`; no captions means Tier 1 is needed (Whisper).

- Extensions are matched case-insensitively (`.MOV`, `.M4A`, `.webm` all work).
- A sidecar whose `<lang>` starts with `en` is preferred, then a plain `<stem>.vtt` or
  `<stem>.srt`.
- The original file is read in place; it is never copied into the work folder, moved or
  deleted.
- Paths with spaces and non-ASCII characters are normal (macOS names screen recordings
  `Screen Recording 2026-10-09 at 14.02.11.mov`); quote them in every command.
- Without captions and without Whisper the run degrades to frames only: steps can be
  `[on-screen]`, `[written]` or `[inferred]`, never `[spoken]`, and the review screen
  names the install command.

## YouTube

- Without cookies: works. yt-dlp needs a JS runtime (deno or node); doctor reports it.
- Captions: manual and automatic tracks are common.
- Fails: an error naming `--cookies` or a private video exits 4. Tell the user
  `Re-run with --cookies-from-browser <browser> if you can open it logged in.`

### treg (Tier 3)

- Calls: the transcript lookup, only when the video has no captions.
- Adds: the timed transcript as a hint only (`cross_check`); it is never the transcript
  and never a step source. No media fallback.

## Generic yt-dlp URLs

- Without cookies: archive.org and Wikimedia Commons work. Vimeo usually needs a login and
  exits 4 without `--cookies-from-browser`.
- Fails: a page with no video or audio (an article, a docs page) exits 7; see
  `## Pages with no video`.

## X

- Without cookies: works for a public video post.
- A post that only links or quotes another video post yields that other post's video. The
  engine says so in `notes` (`video came from a linked post: <url>`) and credits the
  linked post's author.
- Captions: none.
- Fails: a text-only post exits 7 with the video-only message (`## Pages with no video`),
  with or without treg. Protected posts exit 4.

### treg (Tier 3)

- Calls: the thread lookup (always), the author-replies lookup and the untimed
  transcript; links in the thread are fetched.
- Adds: the author's later posts in `context.thread`, the author's own replies (never
  anyone else's) in `context.author_replies`, expanded links, and the untimed transcript
  for the cross-check. When yt-dlp is blocked, the thread's video is the media fallback.

## TikTok

- Without cookies: works.
- Captions: none.
- Fails: none seen logged out.

### treg (Tier 3)

- Calls: the transcript lookup for video posts; the video lookup only as the media
  fallback.
- Adds: the transcript as a hint only (cross-check); a media fallback when yt-dlp is
  blocked.

## Instagram

- Without cookies: works for recent reels of a public profile; older ones may need cookies.
  The duration is unknown logged out, so probe prints `time unknown`.
- Captions: none.
- Fails: a login wall exits 4; tell the user
  `Instagram often needs a login. Re-run with --cookies-from-browser <browser>.`

### treg (Tier 3)

- Calls: the post lookup, only as the media fallback.
- Adds: a media fallback when yt-dlp is blocked, and never for post text: the lookup
  returns no caption, so Instagram text always comes from the free route.

## Facebook

- Without cookies: works for a public page's video.
- Captions: none.
- Fails: page listings such as `/<page>/videos` are "Unsupported URL" (exit 2): ask for
  one video's URL. A login wall exits 4 with the cookie line.

### treg (Tier 3)

- Calls: the post lookup, only when the free route found no post text.
- Adds: the post text in that case, and never a media fallback: the lookup returns no
  media, so never offer `--provider treg` for a Facebook download failure.

## Pages with no video

0.1.0 reads videos only. A URL with no video or audio (an article, a docs page, a text-only
post on any platform) exits 7 at probe or ingest with
`SkipWatch 0.1.0 reads videos only. This page has no video or audio. Article support is planned for a later release.`
Quote it and stop. Links inside a video post are still read as context (X, TikTok,
Instagram, Facebook).
