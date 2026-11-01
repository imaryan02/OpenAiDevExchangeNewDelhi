# VoiceLink outbound: final diagnostic preparation

## Evidence

- Revision 77 accepted the media WebSocket and sent greeting audio.
- At 19:22:45 UTC, the provider sent `stop` about 937 ms after startup,
  before our gateway completed model initialization. Receiving media concurrently
  and sending greeting frames did not prevent the release.
- Enabling the provider's WebSocket API toggle removed the visible media
  connection, but the call still ended after about one second. The owner restored
  the toggle to OFF and saved it.
- During this investigation, Azure `/health/live` returned 200. VoiceLink's
  website, public documentation, and a read-only GET to its Add Lead URL timed
  out. No further real call was submitted during this pass.

## Unverified lead

Both the production adapter and probe send `call_limit: 1`. The meaning and unit
are unverified. Its numeric match with the connected duration is a hypothesis,
not proof. Do not increase it blindly: it could be a retry count.

The probe now supports `--omit-call-limit` to isolate this field using provider
defaults. This changes only the diagnostic request, not production callbacks.
The provider's default retry behavior also remains unverified.

Once the provider is reachable, the diagnostic command is:

```powershell
.venv\Scripts\python.exe personal-agent/scripts/voicelink_outbound_probe.py --national-number --omit-call-limit --call
```

This command makes one API submission to the registered owner. Do not rerun
after a timeout: acceptance may be unknown and the provider may still dial.
Compare the returned follow-up ID and provider call evidence against the
previous one-second calls before changing production.

Mock validation confirmed the default payload retains `call_limit: 1`, the
diagnostic omits that field, national formatting and signed callback binding
remain intact, and each invocation makes one submission. No live success is
claimed.
