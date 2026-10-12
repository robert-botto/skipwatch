# Run: fallbacks

Read this only when a run file sends you here. Placeholders and conventions are in
`run-engine.md`.

## Move the work folder into the project

If `new-work` fails (any exit other than 64), move the home into the project. If that
Write is denied or fails, do the same:

1. If `new-work` succeeded, remove its folder, the exact path `new-work` printed, with
   `<ENGINE> discard-work --work "<W>"`. Then run
   `mkdir -p "<P>/.skipwatch"`, then Write `<P>/.skipwatch/.gitignore` with the content
   `*`, so the `<P>/.skipwatch/.gitignore` file containing `*` keeps work files out of
   commits.
2. Create the work folder under the project's home, `--home` before the command:

       <ENGINE> --home "<P>/.skipwatch" new-work --from "<input>" --json

   (or `--slug <name>` with `--name`). Take the new `<W>` and repeat the Write probe.
3. Pass `--home "<P>/.skipwatch"` to every `<ENGINE>` call for the new `<W>` for the rest
   of the run, before the command (with `--log` in either order), never as a
   `SKIPWATCH_HOME=` prefix. If
   doctor failed to write `doctor.json` for the same reason, rerun it once with `--home`.
4. Note `work folder moved into the project (<path>): home folder not writable` in the new
   `<W>` (`note --degradation`, with `--home`).

If a later Write is denied (notes, `outline.md`, a draft file), do steps 2 to 4 (not step
1: `discard-work` refuses a folder with finished stages). Read `<old W>/degradations.json`
once and note each line again in the new `<W>` (`--degradation` or `--unread`, with
`--home`). Close the old folder so resume never offers it. This one call runs without
`--home`, because the old folder is under the default home:

    <ENGINE> --log "<old W>/logs/mark.log" mark --work "<old W>" --stage review --status done

If it exits non-zero for any other reason, skip it.

Then re-run the engine stages already done into the new `<W>` with `--home`, re-dispatch
the readers with the new paths, and continue. Switch once; a second denial stops the run
with `SkipWatch: cannot write the work folder (<path>): <the denial message>.` Never work
around a denied Write with a shell redirect or heredoc.
