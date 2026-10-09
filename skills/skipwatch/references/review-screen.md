# Review screen

The review screen has a fixed shape so users learn to scan it and tests can parse it.
Print it exactly in this line order, with these prefixes, every time:

```
Skill ready for review: <name>
  Triggers: "<t1>", "<t2>", "<t3>"
  Steps: <n> (<spoken> spoken, <on_screen> on-screen, <written> written, <inferred> inferred), <gaps> gaps
  Unverified: <list or "none">
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
- **Unverified:** each inferred step as `step N (<reason>)`, each unread frame range, and
  each degradation from the run (for example `no transcript: Whisper not installed
  (install: <command>)`, or `work folder moved into the project (<path>): home folder
  not writable`). `none` only when all three lists are empty.
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
- **Provider calls:** `W/calls.json`. Empty means `none (free route)`; otherwise list each
  as `<provider> <op> ($<cost>)` with the total. When `W/ingest.json` has `from_cache`
  true, the metadata came from the 7-day run cache (R-TR-3): append
  `; cached from <date>` (the date from the ingest log's cache line, else
  `cached from an earlier run`), for example `none (free route); cached from 2026-10-07`.
  Cached calls are not billed again. A transcript reused from the cache adds
  `; transcript cached (<origin>)`. Audio the user sent to a cloud provider adds
  `<provider> transcription (billed to your <ENV VAR> key)`.
- **Draft:** `W/staging/<name>/`.
- **Target:** always an absolute path; `--to` was resolved when the arguments were read.

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
  `<W>/logs/whisper-install.log`. On rc 0,
  run `<ENGINE> resume "<W>" --json` and continue from its `next_stage` (`transcribe`) as
  the `## Resume` section of `run-protocol.md` says; frames, readers, draft and check run
  again and this screen is shown anew. On any other rc, show the last log line and the
  prompt line again.
- **transcribe with <Provider> and re-run:** R-TR-2. Audio goes to a cloud provider only
  after the user said yes to that provider by name; picking this option, which names
  the provider, is that yes, and nothing else is. Print
  `Sending the audio to <Provider> for transcription.`, then run
  `<ENGINE> transcribe --work "<W>" --backend <openai|groq|deepgram>` with exactly the
  backend the user picked, never `auto`, timed as any stage. On exit 0, then continue
  from stage 3 step 5 of `run-protocol.md` (frames without `--dense`, then the rest);
  `resume` would run transcribe under `auto`, which never picks a cloud backend. Exit 8
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
- **cancel:** print `Cancelled. Draft kept at <W>/staging/<name>/.` and stop. Nothing is
  installed and `W` is kept.
- Anything else: re-show the prompt line once with the five answers.
