# Golden set

Five public videos that SkipWatch is measured against (spec 11.5). They live in
`golden.json` with expected ranges for each. Run by hand before releases and after yt-dlp
upgrades; never in CI.

## Commands

```bash
# Metadata only: no download, no cookies. Exit 0 only when every video still resolves.
uv run python scripts/golden_check.py
uv run python scripts/golden_check.py --only G1,G5

# Full run (paid: one `claude -p` per video, up to 30 minutes each).
uv run python scripts/golden_run.py --only G1 --out /tmp/sw-golden

# Engine stages only (probe to plan) on the free provider; no Claude, nothing judged.
uv run python scripts/golden_run.py --engine-only --only G2 --stages probe,ingest,frames --out /tmp/sw-golden
uv run python scripts/golden_run.py --engine-only --only G1 --out /tmp/sw-golden
```

`golden_run.py` gives each video its own `SKIPWATCH_HOME` at `<out>/<id>/home` and judges the
staged draft (`<home>/work/*/staging/<id>-skill/SKILL.md`) and `check-report.json`, installed
or not. It prints `G1 PASS steps=11 inferred=0.09 gaps=0 flags=0 illegible_in_quotes=0
installed=yes`, or `FAIL` followed by each out-of-range value, for example
`steps=4 (want 6..20)`. `illegible_in_quotes` counts `[illegible` markers on blockquote lines
and inside fenced code blocks. Cookies are passed only when an entry has
`needs_cookies: true` and `SKIPWATCH_GOLDEN_COOKIES=chrome` is set.

`<out>` holds data fetched from the golden videos: the downloaded video (`work/*/media/`),
extracted frames (`work/*/frames/`), captions, transcripts, notes and the generated drafts.
By default `golden_run.py` deletes `media/` and `frames/` after judging each video (or after
the engine stages with `--engine-only`), success or failure; pass `--keep-media` to keep
them. Captions, transcripts and drafts stay so a run can be inspected; delete `<out>` when
done. Everything in `<out>` is for local testing only: never commit it or share it.

## Selection rules

- G1: a YouTube CLI tutorial, 5 to 15 minutes, manual English captions, a worked example that
  runs offline in a scratch directory with free, cross-platform tools; channel over 50k
  subscribers, upload over 6 months old. G1 alone carries `s2` (task and verify command) for
  success criterion S2.
- G2: a public X post with a native video tutorial, 1 to 5 minutes, account over 10k
  followers, no login wall when opened logged out. Carries `expected.context` (thread, author
  replies and links seen logged out) for M4.
- G3: a public TikTok tutorial with on-screen text, 30 s to 3 minutes.
- G4: a public Instagram reel tutorial, 30 s to 3 minutes (set `needs_cookies: true` when it
  cannot be fetched logged out).
- G5: a YouTube talk with slides, 25 to 40 minutes, captions present.
- Established creators or official accounts only; not age-gated or region-locked; no NSFW,
  medical, financial-advice or political content.

Ranges: G1 steps 6 to 20, inferred ratio at most 0.2, gaps at most 1; G2 to G4 steps 3 to
15, inferred at most 0.3, gaps at most 2; G5 steps 8 to 40, inferred at most 0.3, gaps at
most 3. Every video: zero safety flags (S4) and zero illegible markers in quotes (S3).

Replace a video when it disappears; keep the id.

## Videos, attribution and use

All five are public posts by their creators, linked here by URL only. No video, audio,
caption or frame is committed to this repository. They are fetched at run time on the
operator's machine for local testing of SkipWatch and nothing derived from them is
redistributed. Rights stay with the creators.

| Id | Creator | Title | Licence (platform) |
|---|---|---|---|
| G1 | DevOps Toolbox (`@devopstoolbox`), YouTube | You've been parsing JSON Wrong (2025-10-10) | Standard YouTube licence |
| G2 | Matt Pocock (`@mattpocockuk`), X | TypeScript Tip #11: Deep partials (2022-03-21) | X terms of service |
| G3 | GitHub (`@github`), TikTok | Get GitHub Copilot directly in your terminal (2026-04-02) | TikTok terms of service |
| G4 | GitHub (`@github`), Instagram | Just one command can help you stop leaking secrets (2026-10-02) | Instagram terms of use |
| G5 | Strange Loop Conference (`@StrangeLoopConf`), YouTube | Lessons from building GitHub code search, Luke Francl (2023-10-04) | Standard YouTube licence |

## Known compromises (2026-10-09)

- G4 is only a week old: logged-out Instagram lists only an account's 12 newest reels, so no
  reel older than 3 months was reachable without logging in (accepted by the orchestrator).
  This is a stability risk: the reel may be edited, archived or removed. If it stops
  resolving, swap in its `fallback_url` (another GitHub reel, a Dependabot review automation
  walkthrough, 2026-09-27, which also fetches without cookies) and keep the id G4. Logged
  out, the metadata and the 720p and 1080p formats load, but the duration is missing.
- G2 replaced the first pick (the @claudeai Cowork launch post), whose workflow needs a paid
  plan, so S3 could never complete. The TypeScript tip is reproducible for free with
  `npx tsc`. Its `replies_min` is 0: logged out, X shows two author self-thread posts
  (previous tip, next tip, each quoting a status link) but no author reply to another
  account.
