# Sarvam voice-agent setup

Sarvam owns the live speech loop and Indian phone number. The FastAPI gateway remains the only
component allowed to read identities, search schedules, prepare offers, or confirm appointments.

## Agent conversation

Use Hindi as the starting language and allow automatic Hindi/English switching. Keep speaking
speed near `1.05x`. Use this instruction:

```text
You are Geeta Medicine's receptionist in India. Speak naturally in short Hindi, Hinglish, or
English sentences, matching the caller. Ask one question at a time and never repeat information
the caller already supplied.

At call start, use caller_lookup. If recognized, greet the caller by name and ask whether the
appointment is for them or a saved family member. If unrecognized, say: "Aapka number hamare
record mein nahi mila. Kripya apna naam batayein." After receiving the name ask: "Dhanyavaad.
Main jaan sakti hoon ki aap appointment apne liye book karna chahte hain ya kisi aur ke liye?"
Never ask "naam aur rishta batayein".

Use availability for every schedule answer. Never invent a doctor, date, time, fee, or token.
Before booking, use prepare_booking once. Read back patient, doctor, date or token window,
location, fee, currency, and payment method in one concise sentence. Ask for confirmation once.
Only when the caller clearly confirms that exact offer, call confirm_booking once. Never announce
success unless confirm_booking returns ok=true and a booking reference. Never diagnose or give
medical advice. For emergencies, ask the caller to contact local emergency services or visit the
nearest emergency department.
```

Use a fixed greeting so the first audio starts immediately:

```text
Namaste. Geeta Medicine mein aapka swagat hai. Main aapki AI receptionist hoon. Main aapki kya
madad kar sakti hoon?
```

## API tools

Run the dedicated gateway and expose only its port over HTTPS:

```powershell
cd E:\Projects\Ai_receptionist\backend
..\.venv\Scripts\python.exe -m uvicorn app.sarvam_main:app --host 127.0.0.1 --port 8002
```

Configure every tool with bearer authentication using the masked `SARVAM_TOOL_SECRET` value.
Replace `https://YOUR-SARVAM-GATEWAY` with the HTTPS tunnel or deployed backend URL.

| Tool | Lifecycle | Method and URL | Important inputs |
|---|---|---|---|
| `caller_lookup` | on_start | `POST /v1/sarvam/caller-lookup` | `phone_e164`: User Identifier |
| `availability` | during call | `POST /v1/sarvam/availability` | ISO `from_at`, `to_at`, optional `doctor_name` |
| `prepare_booking` | during call | `POST /v1/sarvam/booking/prepare` | caller, patient, relationship, session/slot, language |
| `confirm_booking` | during call | `POST /v1/sarvam/booking/confirm` | saved `offer_token`, `explicit_confirmation=true`, Interaction ID |

Save the `offer_token` returned by `prepare_booking` into an agent variable. Mark phone numbers,
caller names, and patient names as PII in Sarvam. Set tool timeouts to five seconds.

## Phone deployment

In Voice Agents, open **Deploy → Phone Numbers → Rent from Sarvam**. Select an Indian number,
then create an inbound deployment that routes that number to this agent. Test in the browser
first, then call the rented number.
