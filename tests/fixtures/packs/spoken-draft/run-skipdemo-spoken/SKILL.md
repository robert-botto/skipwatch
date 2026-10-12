---
name: run-skipdemo-spoken
description: Use when the user wants to walk through the spoken skipdemo tutorial, for example "follow the skipdemo walkthrough", "do the spoken skipdemo steps", "run the skipdemo demo by ear". Not for other demo CLIs or for installing skipdemo itself.
compatibility: skipdemo as described in the source video.
metadata:
  source_url: ""
  source_author: ""
  source_title: "tutorial-60s"
  source_date: ""
  extracted_at: "2026-10-11"
  extracted_by: "skipwatch 0.1.0"
---

# Follow the spoken skipdemo tutorial

## What this does

Walks through the skipdemo tutorial using only what the narrator says. Steps come from a 60 second tutorial.

## Prerequisites

- A terminal with `skipdemo` installed (as of the video date).

## Procedure

1. Type the init command in the terminal and run it.

   > First, type this command in the terminal and run it.

   Expected: the words project ready. [spoken 00:09]

2. Paste your prompt into the prompt box.

   > Next, paste this prompt into the prompt box.

   Expected: the assistant answers. [spoken 00:24]

3. Put your API key in the settings panel.

   > Then copy your API key into the settings panel.

   Expected: the key is saved. [spoken 00:39]

4. Click run to see the result.

   > Finally, click run to see the result.

   Expected: the result appears. [spoken 00:49]

## Decision points

None shown in the video.

## Gotchas

None mentioned.

## Verification

The output shows "project ready" and the answer to your prompt.

## Worked example

Run step 1, then steps 2 to 4 with your own prompt.

## Unverified and gaps

None.

## Attribution

Distilled from the local recording tutorial-60s, with SkipWatch. The workflow and wording are the creator's.
