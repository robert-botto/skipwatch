# Run: branches

## Contents

- Long video
- Long stages
- Probe and ingest exits
- Sources
- No transcript or silent video
- Frames exits
- Reader retries
- Resume

Read a section only when a run file sends you here. Placeholders and conventions are in
`run-engine.md`.

## Long video

When `long_video` is true, print `Long video: <mm:ss>, about <n> min to process.`
(`<n>` is `estimated_run_s` / 60 rounded up; if null, `Long video: <mm:ss>, time unknown.`)
and continue only under `--yes` or after the user says yes: without `--yes`, ask once
`Continue? [yes / cancel]`. Under `--yes` do not ask. Cancel stops with
`Cancelled before download.`

## Long stages

The expected time is probe's `estimated_run_s`, or for transcribe the duration times mlx
0.25, faster 0.6, cloud about 0.1, captions about 0. Above 500 s, run that stage with
`run_in_background`. You are notified when it exits, and its output ends with the `rc=`
line. Never call `sleep`. If you get a turn before then, Read `<W>/stages.json` once and
print one progress line, for example `Transcribing: still running (240s)`.

## Probe and ingest exits

Probe exits are handled as the same ingest exit, reading `<W>/logs/probe.log` where this
says `ingest.log`; nothing was downloaded.

- Exit 2: stop with `Unsupported source: <engine message>.`
- Exit 3: Read `<W>/logs/ingest.log` and print every route line and its reason, then
  the fix the engine names, and stop. You never offer `--provider treg` for Facebook:
  treg returns no Facebook media.
- Exit 4: the engine's message, then
  `Re-run with --cookies-from-browser <browser> if you can open it logged in.`; on
  Instagram `Instagram often needs a login. Re-run with --cookies-from-browser <browser>.`
- Exit 7: stop with `No usable content in <input>: no video, audio or text.` A page or
  post with no video says so itself; quote the engine's message instead:
  `SkipWatch 0.1.0 reads videos only. This page has no video or audio. Article support is planned for a later release.`
- Any other exit: the failure table in SKILL.md.

## Sources

- `--provider` on a local file is ignored: local ingest never consults content
  providers. Say so in one line if the user gave it or the cookie flag for a file.
- Linked video: when the video came from a linked post (the engine notes it and the
  review screen shows it), `source` describes the linked post and the requested
  post's text is in `context.thread`.
- Text source: not in 0.1.0. A page or post with no video exits 7 at probe or ingest
  (`## Probe and ingest exits`); no run reaches `source.kind` `"text"`.

## No transcript or silent video

- A `doctor.json` warning that a Whisper model is not downloaded yet: print it once
  before transcribe; the first transcription downloads it.
- Exit 8 (no captions and no local Whisper): do not ask; continue from frames only,
  note `no transcript: no captions and no Whisper backend (install: <command from the engine message>)`,
  print `Transcript: none, continuing from frames only (<n>s)` and run frames with
  `--dense`. Note the install command and each `cloud-keys` entry in `doctor.json` for
  the review screen's transcription offers. `--yes` never picks one of these options.
- Exit 7: the same degradation, noting `no transcript: <the engine's message>`,
  no offer. Exit 3 from transcribe is not a media download: a Whisper model could
  not be downloaded. Degrade the same way with the engine's message plus
  `(retry: /skipwatch resume <W> once online)`, no offer.
- Captions with no timed segments: transcribe falls back to local Whisper by itself and
  notes it. With no Whisper it exits 8 and has already noted
  `no transcript: <the engine's message>`: handle it as the exit 8 above, but note that
  exact line (a no-op) instead of the no-captions wording.
- Silent video: `"silent": true` in `<W>/transcript.json`: print
  `Silent video: leaning on frames and post text.`, run frames with `--dense`, and
  prefer `[on-screen]` and `[written]` tags in the outline.

## Frames exits

- Exit 7 (no media, or the video could not be read): stop with
  `No usable content: the video in <input> could not be read. Nothing was written.`
- An audio-only file exits 0 with an empty `frames.json`: note
  `no frames: audio-only file` and continue.
- With neither a transcript nor any frame, stop:
  `No usable content: no transcript and no readable frames. Nothing was written.` A text
  source is exempt.

## Reader retries

Exit 1: one line per bad batch, such as `batch 3: frames missing f000310` (Read the log
when more than 3 failed). Exit 7: `batches.json` is missing; re-run the plan step. Each
bad batch is re-dispatched once:

- `frames missing <ids>` and nothing else: dispatch one reader for just those frame ids,
  output path `notes_path` with `.json` replaced by `.retry.json` (for example
  `notes/batch-02.retry.json`), then fold it in:

      <ENGINE> --log "<W>/logs/merge-notes.log" merge-notes --work "<W>" --batch <id>

  and run validate-notes again. Never re-dispatch the whole batch for a few missing
  frames.
- anything else: re-dispatch the whole batch once with the same prompt.

A second failure (the retry fails, or `merge-notes` exits 7) marks those frames unread:
note them with
`<ENGINE> --log "<W>/logs/note.log" note --work "<W>" --unread "<frame ids> (reader failed twice)"`,
adding `; may hold a step` as `distill-rules.md` says.

## Resume

`/skipwatch resume [dir]` continues from the first stage that is not done; a stage left
`running` counts as not done.

1. Run stage 1, then, with `<dir>` absolute when given:

       <ENGINE> resume "<dir>" --json

   Without a folder, leave out `"<dir>"`; the engine picks the newest incomplete run. If
   that finds nothing and `<P>/.skipwatch/work` exists, run it once more as
   `<ENGINE> --home "<P>/.skipwatch" resume --json`.
2. Read `work`, `next_stage`, `completed`, `run`, `media_present`.
   - `next_stage` is null: print `SkipWatch: nothing to resume.` and stop.
   - Exit 2, or exit 64 with a message naming `<dir>` (a folder outside the home): print
     `SkipWatch: <dir> is not a SkipWatch work folder.` and stop.
   - Exit 7: print the engine's line, then `Start a new run with the original source.`
     and stop.
   - `run` is null: print
     `SkipWatch: <work> has no run.json; start a new run with the original source.` and stop.
3. Set `<W>` to `work` (under `<P>/.skipwatch`: pass `--home "<P>/.skipwatch"` as in
   `run-fallbacks.md`). `<input>` is `run.input`; read `run.flags` as if the user had
   typed them and `run.name` as `--name`. Print `Resuming <W> at <next_stage> (<k> stages
   done)`.
4. Continue from `next_stage` (noted degradations are already in the work folder):
   - `media_present` is false and the stage needs media (`ingest`, `transcribe`, `frames`):
     stage 3 step 3 (ingest) first.
   - `detect` or `ingest`: stage 3 from step 3; no probe or long-video question.
   - `transcribe`, `frames`, `plan`: that step of stage 3, then the rest.
   - `read` or `distill`: run `validate-notes` (stage 4) and re-dispatch readers only for
     batches whose notes file is missing or invalid, then stage 5.
   - `critique`: stage 7 when `<W>/staging/<name>/SKILL.md` exists, then stage 8;
     otherwise as `read`. `<name>` is `run.name` when set, otherwise the one folder under
     `<W>/staging/`.
   - `check`: stage 8 when that `SKILL.md` exists, otherwise stage 5.
   - `review` or `install`: stage 8 (staging may have been edited), then stage 9.
