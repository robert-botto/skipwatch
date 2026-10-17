# Security policy

## Reporting a vulnerability

Please report security problems privately. Open the repository's Security tab, choose "Report a vulnerability", and describe what you found and how to reproduce it. Do not open a public issue for a vulnerability.

We acknowledge every report within 72 hours.

## Supported versions

Only the latest minor release gets security fixes.

## Scope

In scope:

- Prompt injection through video content: transcript, caption, post or frame text that makes SkipWatch act on instructions instead of treating them as data.
- Secret leakage: an API key, token, password or cookie reaching a generated skill, a pack, a log or a network request it should not.
- Dangerous commands: a generated skill or a test run executing or hiding a risky command that the checks should have flagged.
- Malicious packs: a `.skillpack.zip` that escapes its folder, overwrites files outside the target, or passes verification while carrying content the checks should have caught.

Out of scope: vulnerabilities in yt-dlp, Whisper, Claude Code or a video platform (report those upstream), and a skill doing something the user approved on the review screen.

## About pack hashes

A pack's checksums prove the files were not changed by accident. They do not prove who made it. The checks and your review of the review screen are what protect you, so read it before you say yes to a pack from someone you do not know.
