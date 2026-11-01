# Friday callbacks through Twilio

VoiceLink continues handling inbound calls. Friday's outbound worker defaults to
Twilio. WhatsApp continues using Twilio's messaging configuration.

Set these values on the deployed backend and save a new Azure revision:

```dotenv
PERSONAL_AGENT_CALLBACK_PROVIDER=twilio
PERSONAL_AGENT_ENABLED=true
PERSONAL_AGENT_OUTBOUND_ENABLED=true
PERSONAL_AGENT_SCHEDULER_ENABLED=true
```

The GitHub deployment workflow sets the provider, outbound and scheduler flags,
and the verified Twilio caller number when deploying this change. Existing Azure
Twilio credentials and other settings are retained.

Keep the existing owner UUID, registered phone, database, OpenAI Realtime settings,
verification pepper, and `PUBLIC_BACKEND_URL`. Set `TWILIO_ACCOUNT_SID`,
`TWILIO_AUTH_TOKEN`, and `TWILIO_PHONE_NUMBER` from the verified voice account.
The successful reachability test used `+18312286492` as caller ID.

No Twilio Console incoming-number webhook change is needed. Each outbound API
request sets its own answer URL and lifecycle callback URL. The backend derives
the secure media URL from `PUBLIC_BACKEND_URL`, independently of the receptionist
`PUBLIC_WEBSOCKET_URL`.

The answer route verifies Twilio's signature and the registered destination.
The media start verifies the account, attempt signature and call-specific binding.
The database binds the call to the owner, generation and reminder. Friday uses
the same prompt, memory and tools as its VoiceLink conversation, with mu-law audio.
Carrier completion does not mark a reminder acknowledged; the owner must acknowledge it.

After deployment, save a fresh reminder. Old overdue reminders may become
`needs_attention` instead of dialing because the worker limits lateness.
The prior Twilio test proved telephone delivery only; this conversational route
still requires a deployed live call check. Trial restrictions and account geographic
permissions still apply.
