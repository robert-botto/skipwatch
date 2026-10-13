---
name: build-with-jev
description: Builds an app that uses TypeSafe's Jev decision model through a coding agent such as Cursor, from getting an API key to a running demo. Use when the user wants to build something on the Jev API, for example "build an app with the Jev API", "set up Jev in my project", "use Jev to make fast decisions in my app", "improve my agent's memory with Jev". Not for apps that need a model to write text or code, or for training or fine-tuning a model.
compatibility: TypeSafe console and Jev API (model jev-1.13.0 on screen), Cursor with an agent chat, as shown in the source video.
metadata:
  source_url: "https://x.com/moritzkremb/status/2100715237267660873"
  source_author: "@moritzkremb"
  source_title: "Moritz Kremb - Full Jev Tutorial  What it is, how you can build with it and what new..."
  source_date: "2026-09-17"
  extracted_at: "2026-10-13"
  extracted_by: "skipwatch 0.1.0"
---

# Build an app on the Jev decision API with a coding agent

## What this does

You end up with a working demo app in which Jev makes the fast decisions (pick, classify, score, route) and plain code acts on its probabilities, built for you by a coding agent that has read the Jev docs. The steps come from a video tutorial that builds a voice-controlled browser and an improved agent memory system this way.

## Prerequisites

- Access to the TypeSafe console (waitlist at the time of the video, 2026-09-17).
- Cursor, or another coding agent that can read web docs and edit a project folder (as of the video).

## Procedure

1. Go to the TypeSafe website and join the waitlist, if you do not have console access yet.

   > go to typesafe.ai, their website here

   Expected: once let in, you can log into the console. [spoken 04:11]

2. In the console, open the API Keys tab and create a new key.

   ```
   TYPESAFE AI > API Keys
   ```

   Expected: the keys page at console.typesafe.ai/keys lists your new key. [on-screen 04:46]

3. Save the key in a local `.env` file in your project folder.

   > And then just go ahead and save your key somewhere in a local file so in your local.env file

   Expected: the key is stored in `.env`, not pasted into chat. [spoken 04:53]

4. Open Cursor and create a new, empty project folder for the Jev work.

   > I opened up Cursor
   > which is the application I use to code
   > and I created a new folder here

   Expected: an empty workspace with the agent chat open. [spoken 05:00]

5. Paste this prompt into the agent so it reads and compresses the Jev docs into the project.

   ```
   Read the documentation completely and save a compressed version or something locally in your folder, because we will be working with this model inside of this project. I want you to know everything about it so that we can work with it efficiently with the API: https://docs.typesafe.ai/introduction
   ```

   Expected: the agent saves a compressed copy of the docs in the folder and summarises it. [on-screen 05:08]

6. Tell the agent where your API key is saved.

   > it where your API key is saved

   Expected: the agent knows to load the key from `.env`. [spoken 05:47]

7. Describe the app you want, naming the Jev API. The creator's prompt for a voice-controlled browser starts like this; the spoken rest of it is quoted under "Unverified and gaps".

   ```
   I want you to build an an app using the Jev Api.

   It should be a web app where I can speak into, i
   ```

   Expected: the agent builds the app and reports how to run it. [on-screen 06:20]

8. Open the app the agent built and try it with a real input.

   ```
   localhost:8787
   ```

   Expected: the dashboard logs each Jev decision, for example `ACT - open wikipedia.org (silent 4001ms)`. [on-screen 07:05]

9. Ask the agent to explain how the app works.

   ```
   Can you explain in very simple terms how this actually works?
   ```

   Expected: a short explanation of which questions Jev answers and what code does with the answers. [on-screen 08:33]

10. Check that the design keeps the acting in plain code with thresholds on Jev's probabilities, as the explanation in the video does.

    ```
    3. Plain code decides and acts. The server has a handful of if statements with thresholds. If "is this a command" is below 0.5, ignore it. If "is the sentence finished" is below 0.6, wait for more words. If the intent is confident and the sentence is done, do it: Playwright, a browser automation library, actually clicks, types, or navigates in the controlled Chromium window and flashes a highlight so you can see what it did.
    ```

    Expected: the app asks Jev typed questions and code applies the thresholds. [on-screen 10:20]

11. To improve an existing system instead of building a new app, paste a prompt that points the agent at that system and asks for a demo dashboard.

    ```
    i wanto build an improved clawdia memory system.
    look into my memory system in the Clawdia folder. Come up with ways to improve my memory system using Jev. Build the improvemeent and build a dashboard to be able to demo exactly what improved and see the improvements.
    ```

    Expected: the agent builds the improvement and a dashboard to compare before and after. [on-screen 11:35]

12. Open the demo dashboard and run one of its example questions.

    ```
    asking Jev... (stage 1: which file · stage 2: which section)
    ```

    Expected: a before and after comparison, for example `2,756 vs 13,408` tokens and `ANSWERED  P(exists)=0.89 · top section P=0.96`. [on-screen 13:41]

13. Ask the agent for a plain explanation of what changed.

    ```
    explain what was before and how jev has improved it in simple terms
    ```

    Expected: a before and after summary of what Jev now decides. [on-screen 14:57]

## Decision points

- Jev versus an LLM: use Jev where the app picks, classifies, scores, ranks or routes among options you define, and an LLM where it must write. The video's summary slide (03:33) [on-screen 03:33]:

  ```
  CAN: + pick an action, + classify, + score / rank, + route, + at 100x the speed
  CAN'T: - write a sentence, - explain itself, - write code, - reason step by step
  ```

- Combining both: in the YouTube title demo an LLM generates and Jev ranks [on-screen 20:32]:

  ```
  An LLM writes candidate titles + thumbnail concepts (Jev does not generate). Jev featurizes each one, the model ranks them, and a final Jev Choice over the top 5 asks which a viewer would click and which is most honest.
  ```

- Several apps at once: the creator had the agent build three demo apps in parallel with this prompt, shown briefly at 17:28; the earlier message listing the three apps is not shown [on-screen 17:28]:

  ```
  lets build these 3 things. spin up subagents to build them in parallel in separate subfolders within this Jev folder. They should all be ready and demo-able apps at the end, fully tested and working. complete them until then end.
  ```

## Gotchas

- Jev does not return text. It returns a probability for each of the options you define, so every decision needs its options set up front [on-screen 01:36]:

  ```
  it can't write. it points at one of YOUR options. 0.1 seconds
  ```

- An app that acts on live pages (the voice browser clicks, types and navigates for real) should keep a check for risky actions. The video's app asks Jev this among its questions; keep that question and a threshold on it before acting [on-screen 09:12]:

  ```
  Would this action buy, delete or send something?
  ```

- Access was waitlist-only at the time of the video [spoken 04:16]:

  > So right now, there's still a waitlist

- Speed depended on the connection: the creator says the demo was slower than an earlier run because of their internet [spoken 11:10]:

  > my Internet. My internet right now is a

- The captions spell the model "Jeff"; the product and screen spell it "Jev".

## Verification

The app runs locally and shows Jev's decisions with probabilities next to the action taken, as in step 8 and step 12, and the agent's explanation (steps 9 and 13) names the typed questions Jev answers and the thresholds code applies.

## Worked example

1. Create a key in the TypeSafe console and save it in `<your-project>/.env`.
2. Open `<your-project>` in Cursor and paste the docs prompt from step 5, then tell the agent the key is in `.env`.
3. Ask: "I want you to build an app using the Jev Api. It should be a web app where `<what the user does>` and `<what the app decides>`."
4. Run the app at the address the agent gives (the video's was `localhost:8787`) and try `<a sample input>`.
5. Ask the step 9 question and check the answer against step 10.

## Unverified and gaps

- step 7: the typed prompt is readable only up to "It should be a web app where I can speak into, i"; later frames show more with part of a word hidden by the cursor. The creator speaks the rest while typing (06:16 to 06:42, transcript segments in order): "where", "I can record or I can speak into", "It automatically", "transcribes", "what I say and controls the", "web browser for me. So I can say", "for example, open this website, click on this link", "et cetera", "and the browser just does", "all of that in real time".
- GAP: 06:42, the video cuts from the typed voice-browser prompt to the finished app; any agent questions or approvals in between are not shown.
- GAP: 13:18, the video cuts from the memory prompt to the finished dashboard; the build is not shown.
- The YouTube predictor demo (17:27) is not a step: the prompt that built it is not shown.

## Attribution

Distilled from Moritz Kremb - Full Jev Tutorial  What it is, how you can build with it and what new... by @moritzkremb (https://x.com/moritzkremb/status/2100715237267660873), posted 2026-09-17, with SkipWatch. The workflow and wording are the creator's.
