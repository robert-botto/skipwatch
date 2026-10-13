# Source evidence

Source: Moritz Kremb - Full Jev Tutorial  What it is, how you can build with it and what new... (https://x.com/moritzkremb/status/2100715237267660873), 2026-09-17.

Post chapters: 0:00 Intro, 0:34 Jev explained, 4:06 API setup, 5:59 Demo 1: Voice-controlled browser, 11:33 Demo 2: AI memory, 17:27 Demo 3: YouTube predictor.

## Step 1
- Transcript 04:11: "go to typesafe.ai, their website here"
- Transcript 04:15: "you'll see here, join waitlist"

## Step 2
- Transcript 04:49: "so just go here to the API keys tab"
- Frames: f002860 at 04:46 (console.typesafe.ai/playground, "TYPESAFE AI > API Keys"), f002970 at 04:57 (console.typesafe.ai/keys)

## Step 3
- Transcript 04:54: "key somewhere in a local file"; 04:57: "so in your local.env file"
- Frames: f002970 at 04:57 (Finder window, ".env" read at confidence 0.5)

## Step 4
- Transcript 05:00: "I opened up Cursor"; 05:03: "and I created a new folder here"

## Step 5
- Transcript 05:10: "read the documentation completely and save a compressed version"
- Frames: f003083 at 05:08 (full prompt), f003103 at 05:10

## Step 6
- Transcript 05:45 to 05:49: "And then you would also want to tell", "it where your API key is saved"

## Step 7
- Transcript 06:04 to 06:39: "I want you to build an app", "using the Jeff API. It should be a web app", "transcribes", "what I say and controls the", "web browser for me. So I can say", "for example, open this website, click on this link", "and the browser just does", "all of that in real time"
- Frames: f003627 at 06:02 (empty prompt box), f003652 at 06:05, f003800 at 06:20 (quoted), f003912 at 06:31 and f003930 at 06:33 (longer, with part of "should" hidden by the cursor; f003930 reads "So i can say for exampel open this web")

## Step 8
- Transcript 06:57 to 07:03: "start Mike, and then it should be recording my voice", "Okay, go to wikipedia dot org"
- Frames: f004254 at 07:05, f004284 at 07:08, f004695 at 07:49, f004720 at 07:52, f005078 at 08:27 ("voice-browser · Jev decides, Playwright acts   model jev-1.13.0")

## Step 9
- Transcript 08:57: "Can you explain in very simple terms"
- Frames: f005130 at 08:33, f005520 at 09:12 (part 2, the questions Jev answers)

## Step 10
- Transcript 10:06 to 10:25: "then plain code decides and acts", "is below 0.5, ignore it", "is below 0.6, wait for more words"
- Frames: f006200 at 10:20, f006370 at 10:37

## Step 11
- Transcript 11:33 to 12:09: "So I'm going to paste this", "an improved Claudia memory system"
- Frames: f006955 at 11:35, f006957 at 11:35, f007270 at 12:07, f007370 at 12:17 (Clawdia folder with a memory subfolder)

## Step 12
- Transcript 13:21 to 14:07: "the first one says recall", "what's the current offer positioning?", "this request took almost eighty percent fewer tokens"
- Frames: f008090 at 13:29 (127.0.0.1:8777, tabs "Recall  Remember  Audit  Benchmarks  Questions & thresholds"), f008212 at 13:41, f008380 at 13:58 (the reader marks the percentage as partly covered: "9% fewer tokens" at confidence 0.6), f009800 at 16:20

## Step 13
- Transcript 14:13: "Okay, I asked for a quick explanation here"
- Frames: f008970 at 14:57, f009440 at 15:44

## Decision points and gotchas
- f000960 at 01:36 ("it can't write. it points at one of YOUR options. 0.1 seconds")
- f002130 at 03:33 (the trade slide)
- f010480 at 17:28 (subagents prompt and run commands)
- f012320 at 20:32 (ideate pipeline description)
- Transcript 04:16: "So right now, there's still a waitlist"; 11:09 to 11:12: "my Internet. My internet right now is a"
