# Review screen

## Contents

- Example (the fixture run)
- Where each line comes from
- Extra lines
- Pack variant
- The prompt line
- Transcription offers
- Answers
- Old patterns

Print it exactly in this line order, with these prefixes:

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
- **Steps and gaps:** `counts` in `<W>/check-report.json`.
- **Unverified:** summarises the skill's `Unverified and gaps` section plus the run's
  degradations: each inferred step as `step N (<reason>)`, each degradation as recorded
  (for example `work folder moved into the project (<path>): home folder not writable`).
- **Unread frames:** frame ids a reader failed twice to cover, with the reason, for
  example `f006032 (reader failed twice)`; `none` when every frame was read. Unread frames
  are not gaps and never become `GAP:` lines. Unread frames never block `--yes`; the
  confidence reason says `frames unread`. The rules for `may hold a step` and for unread
  cue frames, which are gaps
  (`GAP: frame <id> at mm:ss was not read (cue: "<transcript window snippet>")`) and not
  repeated here, are in `distill-rules.md`.
- **Safety flags:** the safety result's `flags`, as `pipe_to_shell (high) at step 7`.
- **Confidence:** `confidence` in `<W>/staging/<name>/skipwatch.json`, then its reasons:
  the engine computes the grade, so never work it out yourself. The reason is
  `critic not run` only under `--fast`; when stage 7 gave up on the critic it is only
  `critic failed twice`, never `critic not run`. A critic score under 8 adds
  `critic score <s>` (`critic_score`, one decimal). Add every other reason that applies
  (`1 gap`, `no transcript`, `frames unread`).
- **Test run:** only after a test, one line directly after `Confidence:`, exactly as
  `validate-test` printed it:

      Test run: <completed | blocked at step N (reason) | ambiguous at step N (what)>

  Screens without a test keep the shape above.
- **Source:** `source` in `<W>/ingest.json`: title, author handle and post date; a local
  file is `local file` and `undated` unless it carries them.
- **Provider calls:** `provider_calls_line` in `<W>/check-report.json`, printed exactly;
  never compute it from `calls.json` or `treg balance`. Then a transcript reused from the
  cache adds `; transcript cached (<origin>)`, and audio sent to a cloud provider adds
  `; <provider> transcription (billed to your <ENV VAR> key)`.
- **Draft:** `<W>/staging/<name>/`. **Target:** always absolute.

## Extra lines

Each only when it applies, right after the `Draft:` line:

```
  video came from a linked post: <url>
  Fetched with your browser cookies: this skill cannot be packed for sharing.
  Cross-check: <similarity> against <origin>
  transcript sources disagree: <similarity>
```

- **Linked post:** copied exactly from `notes` in `<W>/ingest.json` (an older cache
  keeps it elsewhere: "Old patterns"). The `Source:` line and the attribution then
  names the linked post's author.
- **Cookies:** `fetched_with_cookies` true in `<W>/ingest.json`; such a skill is never
  packed or shared.
- **Cross-check:** `cross_check` in `transcript.json`: its `similarity` to 2 decimals and
  its `origin`.
- **Disagreement:** copy the `transcript sources disagree: <similarity>` part of the
  engine's `Transcribe: warning: transcript sources disagree:` line exactly; never
  compute the similarity yourself or warn without that line.

## Pack variant

Installing a pack (`sharing.md`) shows the same screen with `<W>` = `<work>`. These lines
differ:

- **Confidence:** `pack_confidence` in `<work>/check-report.json` (the engine's grade
  without a critic, never `high`). Print
  `<pack_confidence> (shared pack: critic not re-run here; the pack claims <claimed_confidence>, critic <claimed_critic_score or none>)`,
  then any other reason after `; `.
- **Unverified:** add `<k> quoted steps not re-verified (shared pack)` from the
  provenance result's info item in `<work>/check-report.json` (a pack's `[on-screen]`
  and `[written]` quotes cannot be re-checked here).
- **Source:** as usual, then `(from pack <file>, sha256 <12 hex>)`: `pack.file` and the
  first 12 hex characters of `pack.sha256` after `sha256:`.
- **Provider calls:** the engine's line, `none (shared pack)`. **Unread frames:** `none`.

```
  Confidence: medium (shared pack: critic not re-run here; the pack claims high, critic 8.5)
  Source: "tutorial-60s" by local file, undated (from pack run-skipdemo-tutorial.skillpack.zip, sha256 3f2a9c41b7d0)
```

## The prompt line

- Normal: `Install to <target>? [yes / show draft / test it / rename / cancel]`
- Target exists (collision):
  `<target> exists. Replace it (a backup is made first)? [replace / show draft / test it / rename / cancel]`
- Under `--yes` with zero safety flags, zero gaps and no collision: print the screen
  without a prompt line, then `Installing (--yes, nothing to review)`, and install.
  Anything else under `--yes` shows the prompt and waits.

## Transcription offers

After transcribe exit 8 (no captions and no local Whisper), the prompt line gains these
offers at the end:

- No cloud key in `doctor.json`:
  `Install to <target>? [yes / show draft / test it / rename / cancel / install Whisper and re-run]`
- Each key under `cloud-keys` in `doctor.json` (`OPENAI_API_KEY` is OpenAI `openai`,
  `GROQ_API_KEY` Groq `groq`, `DEEPGRAM_API_KEY` Deepgram `deepgram`) adds
  `transcribe with <Provider> and re-run (sends the audio to <Provider>)`.

The collision prompt gains the same options. `--yes` never picks one of these options.

- **install Whisper and re-run:** the install command the engine printed. Run it only
  after the user picks it, with the Bash tool's `timeout: 600000` and its output
  redirected to `<W>/logs/whisper-install.log` (one redirect, nothing chained). On rc 0,
  delete the cached doctor report, `rm -f "${SKIPWATCH_HOME:-$HOME/.skipwatch}/doctor.json"`, run
  `<ENGINE> resume "<W>" --json` and continue from `next_stage` as `## Resume` in
  `run-review-install.md` says. On any other rc, show the last line of the stderr the Bash tool returned (the log
  holds stdout only), tell the user to
  run `! <command>` in Claude Code and then `/skipwatch resume <W>`, and show the prompt
  line again.
- **transcribe with <Provider> and re-run:** audio goes to a cloud provider only after
  the user said yes to that provider by name; picking this option, which names the
  provider, is that yes, and nothing else is. Print
  `Sending the audio to <Provider> for transcription.`, then run
  `<ENGINE> --log "<W>/logs/transcribe.log" transcribe --work "<W>" --backend <openai|groq|deepgram>`
  with exactly the backend the user picked, never `auto` (so not through resume). On
  exit 0, remove the `no transcript` entry from Unverified, then continue from stage 3
  step 5 in `run-engine.md`: frames without `--dense`, readers, outline and draft rebuilt
  from the new transcript, check, and this screen anew. Exit 8 or 3: show the engine's
  line and the prompt line again.

## Answers

- **yes / replace:** stage 10 in `run-review-install.md`; `--force` only for replace.
  No install happens without this explicit answer in this run, except the `--yes` case
  above.
- **show draft:** Read `<W>/staging/<name>/SKILL.md` and print it, then the prompt line.
- **test it:** stage 9b in `run-review-install.md` (it asks `Test it anyway?` first when
  there are safety flags), then the whole screen again with its `Test run:` line.
- **rename:** ask for the name, check it against the naming rule in `distill-rules.md`,
  set `name:` in the draft SKILL.md, redact the draft into `<W>/staging/<new name>/`,
  re-run check, and show the screen again with the new target.
- **cancel:** mark review done at once, so the run is not offered for resume:

      <ENGINE> --log "<W>/logs/mark.log" mark --work "<W>" --stage review --status done

  Then print `Cancelled. Draft kept at <W>/staging/<name>/.` and
  `Work files at <W> may hold unredacted text from the video.`, and stop.
- Anything else: re-show the prompt line last printed, once.

## Old patterns

- A bundle cached by an older engine carries `video came from a linked post: <url>` in
  `route.fallbacks` instead of `notes`. Read it there only when `notes` does not hold it.
