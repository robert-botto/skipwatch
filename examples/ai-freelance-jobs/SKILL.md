---
name: ai-freelance-jobs
description: Builds and runs a one-person AI-native creative service firm that takes repeat marketplace jobs (Upwork, Fiverr) and fulfils them with Astra orchestrating creative models through the Higgsfield API. Use when the user wants to turn freelance creative demand into an AI-fulfilled service business, for example "set up an AI agency that does Upwork jobs for me", "build a Studio Operator style job system with Astra and Higgsfield", "which Higgsfield model should I route this client job to", "how do I pick which AI service firm to start". Not for one-off image or video generation with no business around it, or for fully autonomous agents with no human approval step.
compatibility: Astra (OpenAI) and the Higgsfield API, as of September 2026, as shown in the source video.
metadata:
  source_url: "https://www.youtube.com/watch?v=e7s7jRgHWsg"
  source_author: "@GregIsenberg"
  source_title: "Take Upwork jobs, let AI do them (Astra etc). It's absurd."
  source_date: "2026-09-23"
  extracted_at: "2026-10-12"
  extracted_by: "skipwatch 0.1.0"
---

# Build an AI-native creative service firm that fulfils freelance jobs

## What this does

You end up with a semi-autonomous creative firm: an operating system built by Astra in six layered prompts that takes a messy client brief, prices it, routes each step to a Higgsfield model, checks the output, and stops for your approval before delivery. The steps come from the creator's own build of his "Studio Operator" app and the slides he shows for each of the six prompts.

## Prerequisites

- Access to Astra from OpenAI (as of September 2026).
- A Higgsfield API key; one key opens 50+ image, video and audio models (as of September 2026).
- The full text of the six prompts. They are not read out in the video; the creator links them in the video description as a prompt pack: https://startup-ideas-pod.link/Creative_prompt_pack [written]
- An account on a marketplace such as Upwork or Fiverr, or a source of direct leads.

## Procedure

Steps 3 to 8 quote the creator's on-screen summary slide for each prompt, one slide line per block. Use them to check the full prompts from the prompt pack, or as the brief for writing your own.

1. Find demand that already exists by listing the deliverables people buy again and again on marketplaces.

   > you can go to places like upwork Fiverr, Contra, or even just agency websites and just look at what people buy repeatedly, like product videos or localized campaigns or Amazon listing images.

   Expected: a list of repeated jobs, such as product videos, localized campaigns or listing images. [spoken 04:26]

2. Pick one narrow deliverable and package it so the system can learn to produce it repeatedly (see "Choose which firm to build" under Decision points).

   > if you pick one narrow deliverable, you package it up and teach the system, this operating system, how to produce it again and again, you don't really need to guess what people want to pay for anymore.

   Expected: one service with a clear unit, such as one SKU pack or one localized campaign. [spoken 04:40]

3. Send Astra prompt 1, "Build the firm", so the business gets an operating system instead of a chat window. It covers these ten parts:

   ```
   Service templates, Job inbox, Production stages, Client records, Deliverables, Costs, Margins, Approvals, Revisions, Delivery
   ```

   And it keeps this record for every job:

   ```
   A semi-autonomous firm needs a record of: What happened, What was approved, What it spent, What still needs a person
   ```

   ```
   Every job -> A clear state -> A next action
   ```

   Expected: an app where every job has a record, a clear state and a next action. [on-screen 20:37]

4. Send prompt 2, "Brief intake", so Astra can turn an unstructured brief from Upwork, Fiverr or a direct lead into a job.

   ```
   ASTRA EXTRACTS: Deliverables, Formats, Exact copy, Deadline, Supplied assets, Missing inputs, Risks
   ```

   ```
   LIKELY REVISION PROBLEMS: These matter most. Revisions eat the margin.
   ```

   ```
   CLIENT QUESTIONS: The smallest useful set
   ```

   ```
   RECOMMEND: Accept, Review, Reject
   ```

   ```
   Astra handles the judgment. Normal code handles price and margin.
   ```

   Expected: pasting a brief produces extracted fields, a short list of client questions and an accept, review or reject recommendation, with price and margin computed by ordinary code. [on-screen 21:20]

5. Send prompt 3, "The production layer", to connect the Higgsfield API.

   ```
   Connect the Higgsfield API. One key opens 50+ models and workflows.
   ```

   ```
   HIGGSFIELD: THE HARNESS AROUND THE MODELS: Queuing, GPU scaling, Submit, check, download, Price and cost estimate before each run
   ```

   ```
   WHY: See the cost before each run. Protect the margin. 70-90% Gross margin target. No separate integration for each provider.
   ```

   ```
   The key stays on the server. Every request, result, failure, and charge stays attached to the client job.
   ```

   Expected: each job shows a cost estimate before a generation runs, and every request and charge is attached to that job. [on-screen 22:15]

6. Send prompt 4, "The model router", so Astra picks a model per step and explains why.

   ```
   ASTRA DECIDES: Which model fits each step, Why it fits, shown in Studio Operator
   ```

   ```
   THE OVERRIDE: Astra picks a model -> You override the pick -> Job economics update right away
   ```

   Expected: each production step names a model with a reason, and overriding it updates the job economics at once. [on-screen 23:15]

7. Send prompt 5, "QA and repair", so every output is checked against the approved brief.

   ```
   CHECKED FOR: Format, Duration, Copy, Product details, Required scenes, Brand rules, Motion, Audio, Anything else the client will approve
   ```

   ```
   ONE OF FOUR VERDICTS: READY, CONTROLLED EDIT, REGENERATE, HUMAN DECISION
   ```

   Expected: every output gets one of the four verdicts before it reaches you. [on-screen 24:00]

8. Send prompt 6, "Controls and approval gates", last, so the firm keeps moving inside limits you set.

   ```
   LIMITS ON EVERY JOB: Spending limits, Repair limits, Max attempts, Approved models, Client message rules, Approval gates
   ```

   ```
   ASTRA HANDLES: Drafts client updates, Reads routine feedback, Remembers client preferences
   ```

   ```
   COMES BACK TO YOU: Major scope changes, Final delivery
   ```

   ```
   THE AUDIT LOG: Decisions, Generations, Costs, Changes, Repairs. If something goes wrong, you can trace it back.
   ```

   Expected: per-job limits are enforced, major scope changes and final delivery wait for your approval, and an audit log records every decision and cost. [on-screen 24:52]

9. Before each generation, answer the creator's four routing questions, then pick the model from the table under Decision points.

   > So before choosing a model, I ask four things. Am I making a still image, a video, or something with speech? Am I creating something new or repairing an asset that is already close?

   Expected: one model lane is chosen for the step. The other two questions follow at 27:24: whether you are exploring cheaply or making the final version, and what absolutely cannot change (the product, the person, the words, or the movement). [spoken 27:11]

10. Launch with one narrow package and five customers, write down every lesson, and turn the lessons into rules.

    ```
    1 ONE NARROW PACKAGE: One SKU pack, one listing package, or one localized campaign
    ```

    ```
    2 FIVE CUSTOMERS: Stay close to the work
    ```

    ```
    3 WRITE IT ALL DOWN: Every missing input; Every mistake; Every revision; Every place the margin disappeared
    ```

    ```
    4 TURN LESSONS INTO RULES: Intake; Routing; QA; Approval rules
    ```

    Expected: each job feeds back into better intake, routing, QA and approval rules. [on-screen 47:17]

## Decision points

### Choose which firm to build (on-screen 44:05)

Start from a list of repeated jobs from Upwork, Fiverr, industry directories and agencies that serve a niche, then apply the four filters shown on screen:

```
1 Does someone already pay for it? An existing budget is easier to capture than a new category you must explain.
2 Is the unit obvious? One SKU pack. One localized campaign. One product video. Easy for the customer to buy, easy for the agent to understand.
3 Does the work repeat? The workflow improves, and you can sell a subscription. Recurring revenue raises the exit value.
4 Is there a concrete definition of correct? Taste is subjective. Product names, SKU numbers, claims, formats, and required scenes are checkable.
```

The creator's three example firms all pass these filters: an always-on ad studio selling a weekly creative pack for one SKU ("Friday Ads", 34:14), a franchise localization desk turning one national campaign into local versions for brands with 20 to 200 locations (37:40), and an industrial catalog service turning spec sheets into demos and sales graphics (42:30).

### Which model for which job (on-screen 29:39)

```
SOUL: Best: people + taste. Avoid: exact packaging
SEEDREAM / FLUX: Best: product scenes. Watch: labels + tiny text
IDEOGRAM / RECRAFT: Best: layouts + typography. Avoid: cinematic motion
QWEN: Best: precise repairs. Avoid: big art direction
Z-IMAGE / FAST MODELS: Best: cheap exploration. Avoid: final delivery
SEEDANCE: Best: long scenes + refs. Avoid: cheap scratchpad
KLING: Best: hero motion. Avoid: bulk testing
WAN / MINIMAX: Best: talking + audio. Watch: claims + labels
KLING MOTION: Best: copy movement. Watch: source quality
TOPAZ / LIPSYNC: Best: final delivery. Avoid: concepting
```

### Marketplace jobs or direct leads (spoken 19:41)

Marketplaces give validated demand but charge a channel fee. Direct leads, for example from your own X or Instagram account, avoid the fee and, in the creator's words, build "more enterprise value".

## Gotchas

- The video is sponsored by Higgsfield, which funded the episode and supplied the API credits (spoken 00:59). Weigh the model and API recommendations with that in mind.
- The firm is semi-autonomous: AI does the work and a person approves it. The creator keeps a human checking outputs for now (spoken 08:48).
- Include the marketplace channel fee in each job's price. The creator puts Upwork and Fiverr at 5 to 15% (spoken 16:48); the demo jobs show "Channel fee - 0%", so set it yourself.
- Revisions eat the margin; brief intake should flag likely revision problems first (on-screen 21:20).
- Give Astra one layer at a time, in order. The slide says "The order matters. Give Astra one layer at a time." (on-screen 26:27)
- Kling Motion Control needs a clean source image and motion reference, because bad inputs become part of the output (spoken 31:29).
- The Higgsfield API did not include Nano Banana at the time of recording (spoken 32:03).
- Studio Operator itself is not released; the creator offers to give it away only if the episode reaches 5,000 likes and comments (spoken 12:19). Build your own from the six prompts.

## Verification

- A pasted brief becomes a job with extracted deliverables, client questions and an accept, review or reject recommendation.
- The job's profitability panel shows the client price, generation estimate, contingency, channel fee and expected gross margin before you start a generation.
- Outputs reach you with a QA verdict, and nothing is delivered until you click approve.

## Worked example

The creator's Studio Operator demo, with the specifics as placeholders:

1. A direct lead asks for launch creative for `<client-product>`. With an Upwork or Fiverr job you would upload the job link instead, and Astra extracts the brief, reference assets and client notes (spoken 13:12).
2. The brief review sets the deliverables, for example PNG at a 3 by 4 ratio, lists questions for the client, and takes a production budget cap such as "no more than five cents" (spoken 13:25).
3. For a still image the client pays $10. The panel shows Soul 2, a generation estimate of $0.01 and an expected profit of $9.99 at 99.9% expected gross margin (on-screen 15:14).
4. For a five-second video at the same $10 price, Kling 3.0 Turbo is estimated at $0.70, and the panel shows 91.6% expected gross margin with a 20% contingency. Check this number before you click, since a 1.6% margin would not be worth running (on-screen 16:41).
5. Autonomy settings hold allowed model families, conditions that always pause, and client account memory for `<client-name>` with its logos, colors, fonts and rejected styles (on-screen 18:24).
6. When the output passes QA, click "Approve delivery" (on-screen 15:14).

## Unverified and gaps

GAP: 20:28 to 26:27, the full text of the six prompts is never shown or read; the video shows one summary slide per prompt and points to a prompt pack in the description, which SkipWatch did not fetch. Steps 3 to 8 quote those summary slides, not the prompts themselves.

## Attribution

Distilled from Take Upwork jobs, let AI do them (Astra etc). It's absurd. by @GregIsenberg (https://www.youtube.com/watch?v=e7s7jRgHWsg), posted 2026-09-23, with SkipWatch. The workflow and wording are the creator's.
