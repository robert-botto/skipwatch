# Review screen

## Contents

- Printing the screen
- What to pass
- Format reference
- The prompt line
- Transcription offers
- Answers

## Printing the screen

The engine builds the screen from the run's files. Run it, as one command:

    <ENGINE> review --work "<W>" --skill "<W>/staging/<name>" [--test-run "<line>"]

Print its stdout exactly, never edited or rebuilt by hand. Then print the prompt line
below and, when they apply, the transcription offers; the engine never prints those.
Exit 7 names a missing or invalid run file: re-run check (stage 8 in `run-distill.md`)
once, then `review` again; a second exit 7 stops with the engine's line. Exit 64: a
`--test-run` value that is not the `validate-test` line.

For a pack install (`sharing.md`), use `--work "<work>" --skill "<staging>"`. The engine
prints the pack variant itself (`pack_confidence`, the pack's claim, the pack file and
checksum, `none (shared pack)`).

## What to pass

- `--test-run "<line>"`: only after a test run, the line `validate-test` printed.

Degradations and unread frames come from `<W>/degradations.json`, noted during the run
(`note` in `run-engine.md` conventions), so they survive a resume. `critic failed twice`,
once noted, replaces `critic not run`; under `--fast` the engine reports
`critic not run` itself. Unread frames are not gaps and never block `--yes`; they may
show `may hold a step`. An unread cue frame is a `GAP:` line in the skill instead
(`GAP: frame <id> at mm:ss was not read (cue: "<transcript window snippet>")`) and is
never noted.

Everything else (triggers, counts, confidence and its reasons, source, provider calls,
the linked-post, cookies, cross-check and disagreement lines) comes from the run's files.

## Format reference

The engine's screen has this shape (`Test run:` follows `Confidence:` after a test;
extra lines follow `Draft:`):

```
Skill ready for review: <name>
  Triggers: "<t1>", "<t2>", "<t3>"
  Steps: <n> (<spoken> spoken, <on_screen> on-screen, <written> written, <inferred> inferred), <gaps> gaps
  Unverified: <list or "none">
  Unread frames: <none | frame ids (reason)>
  Safety flags: <none | kind (severity) at step N, ...>
  Confidence: <high | medium (<reasons>) | low (<reasons>)>
  Source: "<title>" by <author>, <date or "undated">
  Provider calls: <provider_calls_line>
  Draft: <staging path>

Install to <target>? [yes / show draft / test it / rename / cancel]
```

The fixture run:

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

## The prompt line

- Normal: `Install to <target>? [yes / show draft / test it / rename / cancel]`
- Target exists (collision):
  `<target> exists. Replace it (a backup is made first)? [replace / show draft / test it / rename / cancel]`
- Under `--yes` with zero safety flags, zero gaps and no collision: print the screen
  without a prompt line, then `Installing (--yes, nothing to review)`, and install.
  Anything else under `--yes` shows the prompt and waits.

## Transcription offers

After transcribe exit 8 (no usable captions and no local Whisper), the prompt line gains these
offers at the end:

- No cloud key in `doctor.json`:
  `Install to <target>? [yes / show draft / test it / rename / cancel / install Whisper and re-run]`
- Each key under `cloud-keys` in `doctor.json` (`OPENAI_API_KEY` is OpenAI `openai`,
  `GROQ_API_KEY` Groq `groq`, `DEEPGRAM_API_KEY` Deepgram `deepgram`) adds
  `transcribe with <Provider> and re-run (sends the audio to <Provider>)`.

The collision prompt gains the same options. `--yes` never picks one of these options.
When either offer produces a transcript, remove the fixed problem from the screen:

    <ENGINE> --log "<W>/logs/note.log" note --work "<W>" --clear "no transcript:"

- **install Whisper and re-run:** the install command the engine printed. Run it only
  after the user picks it, as it is (no redirect), with the Bash tool's `timeout: 600000`.
  On rc 0, refresh the doctor report with `<ENGINE> doctor --json` (with `--home
  "<P>/.skipwatch"` when the run moved), then run `<ENGINE> resume "<W>" --json` and
  continue from `next_stage` as `## Resume` in `run-branches.md` says. On any other
  rc, show the last line of its stderr, tell the user to run `! <command>` in Claude Code
  and then `/skipwatch resume <W>`, and show the prompt line again.
- **transcribe with <Provider> and re-run:** audio goes to a cloud provider only after
  the user said yes to that provider by name; picking this option, which names the
  provider, is that yes, and nothing else is. Print
  `Sending the audio to <Provider> for transcription.`, then run
  `<ENGINE> --log "<W>/logs/transcribe.log" transcribe --work "<W>" --backend <openai|groq|deepgram>`
  with exactly the backend the user picked, never `auto` (so not through resume). On
  exit 0, clear the `no transcript:` line as above, then continue from stage 3
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
- **rename:** ask for the name and check it against the naming rule in
  `distill-rules.md`. Move the staged skill, frames included, and record the name for
  resume:

      <ENGINE> --log "<W>/logs/rename-staging.log" rename-staging --work "<W>" --to "<new name>"

  Exit 6: that name is taken; ask for another. Exit 64: the name breaks the rule; ask
  again. Then rewrite `name:` in the draft SKILL.md (Read, then Write), redact it into
  `<W>/staging/<new name>/SKILL.md`, re-run check, and show the screen again with the new
  target.
- **cancel:** mark review done at once, so the run is not offered for resume:

      <ENGINE> --log "<W>/logs/mark.log" mark --work "<W>" --stage review --status done

  Then print `Cancelled. Draft kept at <W>/staging/<name>/.` and
  `Work files at <W> may hold unredacted text from the video.`, and stop.
- Anything else: re-show the prompt line last printed, once.
