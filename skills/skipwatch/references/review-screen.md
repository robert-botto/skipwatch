# Review screen

The review screen has a fixed shape so users learn to scan it and tests can parse it.
Print it exactly in this line order, with these prefixes, every time:

```
Skill ready for review: <name>
  Triggers: "<t1>", "<t2>", "<t3>"
  Steps: <n> (<spoken> spoken, <on_screen> on-screen, <written> written, <inferred> inferred), <gaps> gaps
  Unverified: <list or "none">
  Unread frames: <none | frame ids (reason)>
  Safety flags: <none | kind (severity) at step N, ...>
  Confidence: <high|medium|low> (<reason when not high, e.g. "critic not run">)
  Source: "<title>" by <author or "local file">, <date or "undated">
  Provider calls: <none (free route) | list with cost>
  Draft: <staging path>

Install to <target>? [yes / show draft / test it / rename / cancel]
```

## Example (the fixture run)

```
Skill ready for review: run-skipdemo-tutorial
  Triggers: "initialise a skipdemo project", "run the skipdemo tutorial", "set up skipdemo with a prompt"
  Steps: 4 (1 spoken, 3 on-screen, 0 written, 0 inferred), 0 gaps
  Unverified: none
  Unread frames: none
  Safety flags: none
  Confidence: medium (critic not run)
  Source: "tutorial-60s" by local file, undated
  Provider calls: none (free route)
  Draft: /Users/me/.skipwatch/work/tutorial-60s-20261009-142211/staging/run-skipdemo-tutorial/

Install to /Users/me/demo/installed/run-skipdemo-tutorial? [yes / show draft / test it / rename / cancel]
```

## Where each line comes from

- **Triggers:** the first three quoted phrasings in the description.
- **Steps and gaps:** `counts` in `W/check-report.json`.
- **Unverified:** each inferred step as `step N (<reason>)` and
  each degradation from the run (for example `no transcript: Whisper not installed
  (install: <command>)`, or `work folder moved into the project (<path>): home folder
  not writable`). `none` only when both lists are empty.
- **Unread frames:** the frame ids a reader failed twice to cover (run-protocol stage
  4), with the reason, for example `f006032 (reader failed twice)`; `none` when every
  frame was read. Unread frames are not gaps (section 15): they are not in the gap count
  and never become `GAP:` lines. Unread frames never block `--yes`; the screen says so
  and the confidence reason says `frames unread`. A frame whose `dhash` differs from both
  neighbours shows `may hold a step` in its reason. The exception is an unread cue frame
  (`reason` `cue` in `frames.json`): it may hold the only copy of a command, so it is a
  gap line in the skill,
  `GAP: frame <id> at mm:ss was not read (cue: "<transcript window snippet>")`, counts
  in `gaps` and blocks `--yes`, and it is not repeated on this line.
- **Safety flags:** the safety result's `flags` in `check-report.json`, as
  `pipe_to_shell (high) at step 7`. `none` when empty.
- **Confidence:** `confidence` in `W/staging/<name>/skipwatch.json`. Rule (4.3): `high` is
  no gaps, inferred under 15% of steps and critic score 8 or more; `medium` is one gap or
  inferred under 30%; otherwise `low`. With no `critique.json` the critic did not run, so
  confidence is capped at `medium` and the reason says `critic not run`. Add every other
  reason that applies (`1 gap`, `no transcript`, `frames unread`). A `low` skill is still
  installable; the reason says why it is low.
- **Source:** `source` in `W/ingest.json`; a local file has author `local file` and date
  `undated` unless the file carries them. A URL source shows its title, its author handle
  and its post date.
- **Provider calls:** `W/calls.json`, one row per call with `provider`, `op`, `cost_usd`,
  `ok`, `endpoint`, `call_id` and `review`. No rows means `none (free route)`. Otherwise
  `treg: <n> calls, $<total to 4 decimals> (<op> $<cost>, ...)`: `<n>` counts every row,
  each row shows its `op` and its `cost_usd` to 4 decimals, and the total is their sum,
  computed from `calls.json`, never from `treg balance`, which you never run or print. For
  example `treg: 3 calls, $0.0057 (x.thread $0.0040, x.comments $0.0005, x.transcript $0.0012)`.
  Rows without a `call_id` are not billed calls: `media.get` rows are the download of a
  treg media URL (`$0.0000`), and a row whose `error` is `cost cap` never ran: it shows
  as `<op> refused (cost cap)` and adds nothing to the total. When `route.fallbacks` in
  `W/ingest.json` has `treg: cost cap reached`, the run stopped calling treg at the per-run
  cap, `[providers.treg] max_cost_usd` in `config.toml` (default `$0.05`): append
  `; treg cost cap reached ($<max_cost_usd>)`, so the user knows some context may be
  missing and can raise the cap. When `W/ingest.json` has `from_cache`
  true, the metadata came from the 7-day run cache (R-TR-3): append
  `; cached from <date>` (the date from the ingest log's cache line, else
  `cached from an earlier run`), for example `none (free route); cached from 2026-10-07`.
  Cached calls are not billed again. A transcript reused from the cache adds
  `; transcript cached (<origin>)`. Audio the user sent to a cloud provider adds
  `<provider> transcription (billed to your <ENV VAR> key)`.
- **Draft:** `W/staging/<name>/`.
- **Target:** always an absolute path; `--to` was resolved when the arguments were read.

## Extra lines

Zero or more of these lines come right after the `Draft:` line, before the blank line,
each only when it applies:

```
  video came from a linked post: <url>
  Fetched with your browser cookies: this skill cannot be packed for sharing.
  Cross-check: <similarity> against <origin>
  transcript sources disagree: <similarity>
```

- **Linked post:** the run recorded that the video came from a linked post (stage 3 of
  `run-protocol.md`): the line is copied exactly from `route.fallbacks` in
  `W/ingest.json`. `source` describes the linked
  post, so the `Source:` line names the linked post's author, and so does the
  attribution.
- **Cookies:** `W/ingest.json` has `fetched_with_cookies` true (the user passed
  `--cookies-from-browser`, R-ING-5). The skill came from content only the user's login
  could see, so it is never packed or shared (section 10); the manifest records it.
- **Cross-check:** `transcript.json` has `cross_check` with a `similarity`: print it to 2
  decimals with its `origin` (for example `treg:anyapi.twitter.tweet_transcript`).
- **Disagreement:** the transcribe log has the engine's
  `Transcribe: warning: transcript sources disagree:` line; copy its
  `transcript sources disagree: <similarity>` part exactly. The engine warns only when
  two measures are both low, so never compute the similarity yourself or warn without
  that line. Steps still come from the timed transcript; the line tells the user to check
  the spoken steps.

## The prompt line

- Normal: `Install to <target>? [yes / show draft / test it / rename / cancel]`
- Target exists (collision):
  `<target> exists. Replace it (a backup is made first)? [replace / show draft / test it / rename / cancel]`
- Under `--yes` with zero safety flags, zero gaps and no collision: print the screen
  without a prompt line, then `Installing (--yes, nothing to review)`, and install.
  Anything else under `--yes` shows the prompt and waits (R-REV-1).

## Transcription offers

When transcribe exited 8 (no captions and no local Whisper, stage 3 step 4 of
`run-protocol.md`), the run went on from frames only and the offers wait here, never
mid-run (R-UX-1). The prompt line gains them at the end:

- No cloud key in `doctor.json`:
  `Install to <target>? [yes / show draft / test it / rename / cancel / install Whisper and re-run]`
- Each key listed under `cloud-keys` in `doctor.json` adds one option, naming the
  provider (`OPENAI_API_KEY` is OpenAI `openai`, `GROQ_API_KEY` is Groq `groq`,
  `DEEPGRAM_API_KEY` is Deepgram `deepgram`):
  `transcribe with <Provider> and re-run (sends the audio to <Provider>)`, for example
  `Install to <target>? [yes / show draft / test it / rename / cancel / install Whisper and re-run / transcribe with OpenAI and re-run (sends the audio to OpenAI)]`

The collision prompt gains the same options. `--yes` never picks one of these options:
under `--yes` a skill that qualifies installs from frames only, and the Unverified line
still names the install command.

- **install Whisper and re-run:** the install command the engine printed. Run it only
  after the user picks it (R-DOC-1), with the Bash tool's `timeout: 600000`, output to
  `<W>/logs/whisper-install.log`. On rc 0, delete the cached doctor report so the next
  doctor run is fresh: `rm -f "${SKIPWATCH_HOME:-$HOME/.skipwatch}/doctor.json"`. Then
  run `<ENGINE> resume "<W>" --json` and continue from its `next_stage` (`transcribe`) as
  the `## Resume` section of `run-protocol.md` says; frames, readers, draft and check run
  again and this screen is shown anew. On any other rc (the Bash sandbox or no network
  can stop it), show the last log line, then tell the user to run it themselves in
  Claude Code as `! <command>` and then `/skipwatch resume <W>`, and show the prompt
  line again.
- **transcribe with <Provider> and re-run:** R-TR-2. Audio goes to a cloud provider only
  after the user said yes to that provider by name; picking this option, which names
  the provider, is that yes, and nothing else is. Print
  `Sending the audio to <Provider> for transcription.`, then run
  `<ENGINE> transcribe --work "<W>" --backend <openai|groq|deepgram>` with exactly the
  backend the user picked, never `auto`, timed as any stage. On exit 0, remove the
  `no transcript` entry from Unverified, then continue from stage 3 step 5 of
  `run-protocol.md`: frames without `--dense`, readers, outline and draft rebuilt from
  the new transcript, check, and this screen anew, the same rebuild the Whisper path
  gets from resume. `resume` would run transcribe under `auto`, which never picks a
  cloud backend. Exit 8
  (key rejected) or 3 (request failed): show the engine's line and the prompt line again.

## Answers

- **yes / replace:** run install (stage 9 of `run-protocol.md`); add `--force` only for
  replace. No install happens without this explicit answer in this run, except the `--yes`
  case above.
- **show draft:** print `W/staging/<name>/SKILL.md` (Read it; never cat it through Bash), then the prompt line again.
- **test it:** print `Test runs arrive in M5` and re-show the prompt.
- **rename:** ask for the new name, check it against the naming rule in
  `distill-rules.md`, set `name:` in the draft SKILL.md, redact the draft into a new
  staging folder `W/staging/<new name>/` (stage 6 of `run-protocol.md`), re-run check,
  then show the whole screen again with the new target.
- **cancel:** mark review done at once, so the cancelled run is not offered for resume:

      <ENGINE> mark --work "<W>" --stage review --status done 2>>"<W>/logs/mark.log"

  Then print `Cancelled. Draft kept at <W>/staging/<name>/.` and stop. Nothing is
  installed and `W` is kept.
- Anything else: re-show the prompt line once with the five answers.
