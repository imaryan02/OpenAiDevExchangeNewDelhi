# Phase 6 voice status

Updated: 2026-09-11

## First-call milestone implemented

- A dedicated FastAPI voice-only process exposes the Twilio webhook, stream-status callback,
  bidirectional media WebSocket, and liveness endpoint without exposing dashboard/patient APIs.
- Incoming webhook requests and WebSocket upgrades require Twilio signatures.
- Each media stream also carries a signed, short-lived binding for its call, caller, configured
  organization, and internal voice actor.
- Twilio `audio/x-mulaw` at 8 kHz is decoded for transcription; OpenAI 24 kHz PCM speech is
  downsampled and encoded back to raw 8 kHz mu-law frames.
- Silence-based turn finalization, bounded utterance buffering, playback marks, and basic
  barge-in clearing are implemented.
- Final transcripts use the existing LangGraph booking workflow. Caller ID is supplied only as
  a lookup hint and does not bypass private-record verification.
- OpenAI uses `gpt-4o-mini-transcribe` and `gpt-4o-mini-tts` by default, independently of the
  text-agent model.

## Current live development setup

- Local voice gateway: `127.0.0.1:8001`
- Temporary voice-only tunnel: `https://universities-manufacturer-size-floyd.trycloudflare.com`
- Twilio trial number webhook: configured by API and verified as `POST`
- Signed public webhook smoke test: passed
- Synthetic OpenAI TTS -> telephony codec -> STT round trip: passed

The account-less tunnel is temporary. If it exits or the computer restarts, create a new tunnel,
update `PUBLIC_BACKEND_URL` and `PUBLIC_WEBSOCKET_URL`, restart the voice gateway, then run
`scripts/configure_twilio_voice.py` again.

## Remaining after the first real call

- Tune speech threshold, silence timing, Hindi/Hinglish pronunciation, and perceived latency
  using real telephone audio.
- Add maximum call duration, silence reprompts, bounded repeated-error handling, and controlled
  human transfer.
- Persist call/session state beyond one process and add call event/audit records.
- Test exact-time and token bookings, verification, interruption, disconnect, and concurrent
  calls at 1/3/5 tiers.
