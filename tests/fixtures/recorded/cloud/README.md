# Cloud transcription fixtures (doc-derived, not recorded)

These three files were written by hand on 2026-10-09. No request was ever sent to a provider:
no key exists on the build machine and paid calls are not allowed for builders. Each file
carries `"_handmade": "shape from provider docs and SDK types, 2026-10-09"`.

| File | Provider | Shape source |
|---|---|---|
| `openai_verbose.json` | OpenAI `POST /v1/audio/transcriptions`, `whisper-1`, `response_format=verbose_json`, `timestamp_granularities[]` word and segment | openai-python types `TranscriptionVerbose`, `TranscriptionSegment`, `TranscriptionWord` and `transcription_create_params` (the API reference page answers 403 to fetchers) |
| `groq_verbose.json` | Groq `POST /openai/v1/audio/transcriptions`, `whisper-large-v3-turbo`, same parameters | console.groq.com/docs/speech-to-text (segment fields; words carry only word, start, end) plus an `x_groq.id` request id |
| `deepgram_listen.json` | Deepgram `POST /v1/listen?model=nova-3&smart_format=true&punctuate=true&utterances=true&detect_language=true` | developers.deepgram.com listen-pre-recorded reference (`metadata`, `results.channels[].detected_language`, `alternatives[].words[]`, top-level `results.utterances[]`) |

Notes:

- OpenAI returns the language as a full name (`"english"`); the backend maps it to a code.
- Each file went through `scripts/scrub_fixture.py`. The scrubber drops Whisper's per-segment
  `tokens` arrays (the key contains the word "token"); the backends never read them.
- Times are seconds. Both Whisper fixtures hold two segments of five words; the Deepgram one
  holds two utterances, the second with one word lacking `punctuated_word`.
- When a real key becomes available, the live test `tests/live/test_live_cloud.py` checks the
  real shapes against the same mapping; replace these files with scrubbed real responses then.
