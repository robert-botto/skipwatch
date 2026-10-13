# Recorded yt-dlp fixtures

Metadata and captions only, recorded with `scripts/record_fixture.py` (live, `SKIPWATCH_LIVE=1`,
never cookies, never media), scrubbed, and read by a human before commit.

## youtube/

- `manual-captions`: GitHub, "Beginner Git commands you need to know (WITH EXAMPLES)", 14:28,
  manual en-US captions (`manual-captions.en-US.json3`).
- `auto-only-nonenglish`: a German Git explainer whose only captions are automatic
  (`de-orig`, plus about 150 machine translations). Review Focus 2.
- `vertical-short` (handmade, `_handmade: true`): the manual fixture with a vertical
  576x1024 to 2160x3840 format list. Review Focus 1.
- `dubbed-audio` (handmade): the manual fixture with Spanish auto-dub audio twins next to
  the English original, to test that the original-language audio is chosen.

## generic/

- `wikimedia-commons`: "Wikipedia Edit 2014", Wikimedia Commons, manual captions in 25
  languages (`wikimedia-commons.en.vtt`).
- `archive-org`: "Big Buck Bunny" on archive.org, no captions, formats without codec fields.

The plan named a public Vimeo video for `generic/`. Vimeo now needs a login in yt-dlp
2026.8.19 ("The web client only works when logged-in"), so a Vimeo URL exits 4 without
`--cookies-from-browser`. archive.org and Wikimedia Commons are recorded instead.

## x/

- `captions-hls.m3u8`: the caption "file" yt-dlp 2026.08.19 lists for an X video (manual en
  track, `protocol: m3u8_native`, `ext: vtt`): an HLS media playlist with one WebVTT segment,
  recorded 2026-10-12 from a public post. The segment URL is a path on video.twimg.com with no
  query string or token.
- `captions-hls.segment.vtt`: the first six cues of that segment as X serves it, with X's
  `<X-word-ms>` per-word timing tags. No X-TIMESTAMP-MAP header (X sends none).
