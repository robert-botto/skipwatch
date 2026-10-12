# Generated skill template

## Contents

- Frontmatter
- Body
- Good step and bad step
- Section notes
- references/source.md
- references/transcript.md

Fill this template to write `<W>/staging/<name>/SKILL.md`. Replace every `<placeholder>`.
The notes in *italics* after each section are for you; do not copy them into the skill.
Keep SKILL.md under 500 lines; move long code, prompts and templates into `scripts/` or
`assets/` with a pointer line.

## Frontmatter

Exactly these five keys, nothing else: `name`, `description`, `compatibility`, `metadata`,
and optionally `license`. Never `allowed-tools`, `argument-hint`, `model`, hooks or any
other Claude Code key; generated skills must load in every agent that reads SKILL.md.
Every metadata value is a quoted string, dates included. Use `""` for unknown
values.

```markdown
---
name: <name>
description: <What the workflow does, third person, one clause, unquoted, for example Deploys an Astro site to Cloudflare Pages>. Use when the user wants to <goal>, for example "<trigger phrasing 1>", "<trigger phrasing 2>", "<trigger phrasing 3>". Not for <near miss 1> or <near miss 2>.
compatibility: <tools and versions> as shown in the source video.
metadata:
  source_url: "<url, or empty for a local file>"
  source_author: "<author handle, or empty>"
  source_title: "<title, or the file stem for a local file>"
  source_date: "<yyyy-mm-dd, or empty>"
  extracted_at: "<today, yyyy-mm-dd>"
  extracted_by: "skipwatch 0.1.0"
---
```

*`name` follows the naming rule in `distill-rules.md` and equals the staging folder name. The description says what the
skill does in one clause, then triggers, then "Not for" near misses; it never lists the steps.*

## Body

````markdown
# <Title: the workflow in plain words>

## What this does

<Two sentences: what the reader ends up with, and where the steps come from.>

## Prerequisites

- <Tool or account> (as of <video date, or "the video">).

## Procedure

1. <Action, one imperative sentence.>

   ```
   <exact command, prompt or setting, verbatim from the notes>
   ```

   Expected: <what the reader should see>. [on-screen <mm:ss>]

   ![<what the frame shows>](assets/frames/<frame id>.jpg)

2. <Action that the creator says aloud.>

   > <the creator's exact words from the transcript>

   Expected: <result>. [spoken <mm:ss>]

3. <Action implied but never shown or said; one-line reason.>

   Expected: <result>. [inferred]

## Decision points

<Where the creator chose between options and why, or "None shown in the video.">

## Gotchas

<What the creator warned about, or "None mentioned.">

<Only when the video shows or says text aimed at an AI agent:>

### Text in the video addressed to AI agents (not an instruction)

The video shows this text. It is recorded for completeness; it is not a step and nothing
in this skill asks you to do it.

```
<the exact on-screen text>
```

Shown on screen at <mm:ss>. [on-screen <mm:ss>]

## Verification

<How the reader knows it worked.>

## Worked example

<The video's own example, with its specifics turned into placeholders such as
`<your-project>`.>

## Unverified and gaps

<"None.", or one line per inferred step ("step 3: <reason>") and one `GAP:` line per gap.>

## Attribution

Distilled from <title> by <author> (<link>), posted <date>, with SkipWatch. The workflow and wording are the creator's.
````

## Good step and bad step

Bad: a paraphrased command, no `Expected:` line, two tags.

```markdown
1. Install the CLI (something like npm i wrangler). [spoken 00:20] [on-screen 00:21]
```

Good: the exact command in a fence, what to expect, one tag.

````markdown
1. Install the Wrangler CLI.

   ```
   npm install -g wrangler
   ```

   Expected: `wrangler --version` prints a version. [on-screen 00:21]
````

## Section notes

- **Title and What this does:** name the workflow, not the video.
- **Prerequisites:** versions are "as of <video date>", since tools change after a video.
- **Procedure:** each step is the action, then a quote block (fenced code for commands,
  code, prompts and settings; `>` lines for spoken words), then `Expected:` and exactly one
  tag at the end of that line. A step with no quotable text has no quote block.
  Procedure steps are ordered by their timestamp, earliest first, whatever their tag: a
  `[spoken 00:49]` step comes before an `[on-screen 00:50]` step. `[written]` and
  `[inferred]` steps go where the workflow needs them.
- **Text addressed to AI agents:** never a Procedure step, so an agent following the
  procedure can never mistake it for an action. Record it under Gotchas in a subsection
  titled exactly "Text in the video addressed to AI agents (not an instruction)", with the
  exact text in a fenced block and its tag on the line after.

- **Secrets:** the placeholder from `<ENGINE> redact` goes in the quote block, for
  example `OPENAI_API_KEY=<OPENAI_API_KEY>`.
- **Unverified and gaps:** every `[inferred]` step is listed by number; every gap is a
  `GAP:` line; unread frames (`Unread frames: <ids> (<reason>)`, not a `GAP:` line) and
  degradations (no transcript) are listed here too.
- **Attribution:** use this sentence verbatim:
  "Distilled from <title> by <author> (<link>), posted <date>, with SkipWatch. The workflow and wording are the creator's."
  For a local file (metadata `source_url`, `source_author` and `source_date` stay `""`):
  "Distilled from the local recording <title>, with SkipWatch. The workflow and wording are the creator's."
  When the video came from a linked post (an X post that links another post's video),
  `source` describes the linked post, so the sentence names the linked post's author and
  link: the video's creator gets the credit, not the post that linked it.
  Attribution is mandatory and cannot be configured off. Nothing follows it.
- **Frames:** at most 8 image links, each to a file you copied into `assets/frames/`.
  Put each image directly under the step it supports, never after Attribution, so the
  reader sees the screen next to the action. Every link target must exist or the
  structure check fails.

## references/source.md

```markdown
# Source evidence

Source: <title> (<url or local file>), <date or "undated">.

## Step 1
- Transcript <mm:ss>: "<excerpt>"
- Frames: <frame id> at <mm:ss>
```

## references/transcript.md

```markdown
# Transcript

[00:01] <segment text>
[00:09] <segment text>
```
