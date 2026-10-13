---
name: copilot-cli-setup
description: Installs GitHub Copilot CLI with npm and starts it in the terminal with a GitHub login. Use when the user wants to get Copilot running in their terminal, for example "install GitHub Copilot CLI", "set up Copilot in my terminal", "how do I start the copilot command". Not for Copilot in VS Code or other editors, or for using Copilot CLI on a codebase after it is running.
compatibility: Node with npm and a GitHub account, Copilot CLI version 0.0.410-1 as shown in the source video.
metadata:
  source_url: "https://www.tiktok.com/@github/video/7624273546776153377"
  source_author: "@github"
  source_title: "Get GitHub Copilot directly in your terminal. Here's how to set it up."
  source_date: "2026-04-02"
  extracted_at: "2026-10-12"
  extracted_by: "skipwatch 0.1.0"
---

# Install and start GitHub Copilot CLI

## What this does

You end up with the `copilot` command installed globally and signed in to your GitHub account, ready to use in any terminal. The steps come from a 35 second GitHub video that installs it with npm and launches it.

## Prerequisites

- Node with npm (as of 2026-04-02). The video says: "If you have Node, you can just open your terminal".
- A GitHub account to log in with.

## Procedure

1. Open a terminal and install Copilot CLI globally with npm.

   ```
   npm install -g @github/copilot
   ```

   Expected: npm finishes with a line such as `added 2 packages in 798ms` and returns to the prompt. [on-screen 00:07]

2. Start Copilot CLI by typing its command.

   ```
   copilot
   ```

   Expected: Copilot CLI starts in the terminal, and logging in (step 3) follows directly. [on-screen 00:19]

3. Log in with your GitHub account. The video does not show the login prompt or its options, so follow whatever login prompt Copilot CLI shows you.

   > log in with your GitHub account and away you go.

   Expected: the welcome banner reading "Welcome to GitHub" with the CLI version, shown on screen at 00:22 (the video shows `CLI Version 0.0.410-1`). [spoken 00:20]

## Decision points

- npm or another package manager: the video uses npm because Node is installed. Without Node, the creator says you can install with Homebrew, Winget or another package manager instead, and to "check their docs for the right command". The video does not show those commands.

## Gotchas

- The spoken audio garbles the package name; the command on screen is `npm install -g @github/copilot`. Use the on-screen form.
- The `-g` flag installs globally, so `copilot` works from any directory.

## Verification

Running `copilot` shows the "Welcome to GitHub" banner with a CLI version line, and after logging in you can use it in the terminal.

## Worked example

In a project folder such as `<your-project>`, run `npm install -g @github/copilot`, wait for npm to report the added packages, type `copilot`, log in with `<your-github-account>`, and the welcome banner appears.

## Unverified and gaps

GAP: 00:20 to 00:22, the login interaction is not shown; the terminal goes from typing copilot straight to the welcome banner

## Attribution

Distilled from Get GitHub Copilot directly in your terminal. Here's how to set it up. by @github (https://www.tiktok.com/@github/video/7624273546776153377), posted 2026-04-02, with SkipWatch. The workflow and wording are the creator's.
