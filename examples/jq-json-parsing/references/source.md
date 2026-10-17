# Source evidence

Source: You've been parsing JSON Wrong (https://www.youtube.com/watch?v=YrVR09v78Dc), 2025-10-10.

Transcript from manual English captions (153 segments). The sponsor segment from 04:30 to 05:29 is not part of the workflow and was skipped.

## Step 1
- Transcript 02:42: "if somehow you don't already have jq installed there's binaries for download available for every package manager in existence"
- Frames: f000700 at 01:10 (jq README with Docker examples, reader confidence 0.8 and 0.7)

## Step 2
- Transcript 03:07: "JQ takes a reference in this case dot is entire object and the file to read or stream to input."

## Step 3
- Transcript 03:18: "Let's get the team for example. This is an array of members. Just by asking for team, we get the list surrounded by arrays brackets."
- Frames: f002080 at 03:28

## Step 4
- Transcript 03:24: "But jq comes with an iterator. Empty brackets is basically asking for all objects"
- Transcript 03:39: "leaving the index clear and then asking for a name, for example, gets the iterator to extract only relevant names"
- Frames: f002210 at 03:41

## Step 5
- Transcript 03:50: "stripping the result from surrounding quotes using the rod data flag like so"
- Transcript 05:29: "We've seen minus R for raw input, removing all surrounding notation."

## Step 6
- Transcript 04:02: "you can echo raw JSON then pipe it over to jq and you get a parsed structured color-coded data always."
- Transcript 04:08: "This becomes even more critical when fetching raw data with curl like the jq projects commits from GitHub for example."

## Step 7
- Transcript 04:20: "Take the first item and restructure the keys with your own object like a message holding the commit message or a name holding the commit.com.name."

## Step 8
- Transcript 05:35: "Hyphen C for compact compresses the structure back to its condensed line form."

## Step 9
- Transcript 05:40: "when addressing an array, you can select rangebased elements."
- Frames: f003480 at 05:48 (output: Dinesh Chugtai object)

## Step 10
- Transcript 05:45: "But JQ's real power is its internal functions. A useful one is the length of objects"

## Step 11
- Transcript 05:54: "picking the team members whose salary is over 115K and boom, Garedon is off the list. Flipping the operator does what you think it would."
- Transcript 06:07: "There's of course also the usual operators of equal not equal to work with when selecting and filtering."

## Step 12
- Transcript 09:03: "just like we plucked Jared from Pi Piper earlier"
- Frames: f003980 at 06:38 (reader confidence 0.6; grey autosuggestion visible)

## Step 13
- Transcript 06:35: "I can select the team's list, but delete the skills to clean the result. Much better. Want to clean further? Just pipe it on and delete more keys."

## Step 14
- Transcript 06:50: "jq allows you to set arguments. For example, we can define that n is for dh. Then select a name from the team where it matches the parameter n."
- Frames: f004180 at 06:58 (motion blur transition, unreadable)

## Step 15
- Transcript 07:02: "Keys gets you well the keys of an object which can also be applied to a nested item like a list."

## Step 16
- Transcript 07:13: "Let's use the pi piper team to build an object. I'll use a new key called person for the name. Then a skill would be they can do and pick a skill but only the first one on every list."

## Step 17
- Transcript 07:24: "The has function will return a boolean based on the existence of a key."

## Step 18
- Transcript 07:35: "if we want to select only team members who have the coding skill on their tool belt. We can use whatever is indexed for that."
- Frames: f004597 at 07:39 (partly typed), f004602 at 07:40, f004607 at 07:40 (output: Dinesh Chugtai)

## Step 19
- Transcript 08:07: "noticing we're looking at an array of messages."
- Frames: f005000 at 08:20 (first log object, level WARNING, nested details)

## Step 20
- Transcript 08:15: "We'll get the first object keys. Inside details, there's another nested object."
- Frames: f005000 at 08:20

## Step 21
- Transcript 08:31: "There is a way to count the objects themselves by piping a real countable data set, like an array, to the length function."
- Transcript 08:52: "An easy fix is to wrap the result in list brackets like so. Now, the length will count the number of returned objects, 66 of them."
- Frames: f005340 at 08:54

## Step 22
- Transcript 09:03: "this time we use the comparison operator for warning lines or errors."

## Decision points
- gojq: transcript 09:44 to 10:22; frames f005992 at 09:59, f006012 at 10:01
- yq: transcript 10:33 to 11:04; frame f006680 at 11:08
- jqp and gron: transcript 11:15 to 11:57
- Nushell: transcript 12:09 to 13:23; frame f007590 at 12:39
