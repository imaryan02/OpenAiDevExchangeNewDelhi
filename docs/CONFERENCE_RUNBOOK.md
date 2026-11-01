# Geeta Medicine AI Receptionist — Conference Operations Runbook

**Document Date**: 12 September 2026  
**Audience**: Conference Presenters, Technical Operators, Receptionist Demo Staff  
**System Architecture**: VoiceLink Telephony DID + OpenAI STT/LLM/TTS + FastAPI Backend (Port 8002) + Supabase PostgreSQL + React/Fluent Dashboard (Port 5173)

---

## 1. System Overview & Pre-Flight Architecture

```text
[Carrier / Cell Phone]
       │
       ▼ (Dial Inbound DID)
[VoiceLink Telephony Cloud]
       │
       ▼ (wss://<tunnel-domain>/api/v1/voice/voicelink/stream)
[FastAPI VoiceLink Gateway (Port 8002)]
  ├── 8 kHz G.711 A-law Frame Ingest & Continuous VAD
  ├── Active Inbound Interruption / Barge-in Buffer Clear
  ├── OpenAI Transcription (`gpt-4o-mini-transcribe`)
  ├── LangGraph State Graph & Bounded Dialogue Contract
  │     ├── Server-Bound Caller Identity (`caller_phone_e164`)
  │     ├── PostgreSQL Transactional Tools (Discovery / Booking / Cancel / Reschedule)
  │     └── HMAC-Signed Booking Offers (CASH / DUE_AT_CLINIC)
  └── OpenAI Streaming TTS (`gpt-4o-mini-tts` / voice `coral`)
       │
       ▼ (Audio Playback)
[Caller Earphone]

[Receptionist Laptop / Browser (Port 5173)]
       │
       ▼ (Polling every 6s + Window Focus + Manual Refresh)
[PostgreSQL Database (Supabase)]
```

---

## 2. Pre-Flight Checklist

Before stepping onto the stage or beginning a demo session, complete these checks:

| Item | Requirement | Verification Command / Check | Status |
| :--- | :--- | :--- | :--- |
| **Python Environment** | Python 3.11+ virtual environment | `.venv\Scripts\python.exe --version` | Required |
| **OpenAI Credentials** | Valid key with transcription, chat, & TTS quotas | Check `OPENAI_API_KEY` in `backend/.env` | Required |
| **Database Connection** | Supabase PostgreSQL reachable | `python scripts/seed_demo_rehearsal.py` | Required |
| **Telephony Gateway** | VoiceLink inbound DID configured | DID mapped to public WebSocket URL | Required |
| **Public Ingress** | HTTPS/WSS tunnel active | Cloudflare Tunnel or ngrok | Required |
| **Staff Dashboard** | Frontend built & running | `http://localhost:5173` loads queue desk | Required |
| **Conference Fixtures** | Demo doctors, sessions & caller seeded | `python scripts/seed_demo_rehearsal.py` | Required |

---

## 3. One-Command Seeding & Reset

Run the rehearsal seed script to populate or reset all conference fixtures idempotently:

```powershell
.venv\Scripts\python.exe scripts/seed_demo_rehearsal.py
```

### Seeded Fixtures Summary:
- **Clinic**: Geeta Medicine (Main Branch, Asia/Kolkata)
- **Primary Rehearsal Caller**: Aryan Gupta (`+918529586946`)
- **Saved Family Contacts**:
  - `Bibha Gupta` (Mother)
  - `Ramesh Gupta` (Father)
- **Active Doctors & Consultations**:
  - **Dr. Amit Kumar**: General Medicine — Fee: ₹500 (CASH / Pay at Clinic)
  - **Dr. Sweta Gupta**: Gynaecology — Fee: ₹700 (CASH / Pay at Clinic)
- **Pre-Booked Active Appointment** (for Lookup, Reschedule, or Cancel tests):
  - Patient: Bibha Gupta
  - Doctor: Dr. Sweta Gupta
  - Status: `CONFIRMED` (Token #1)

---

## 4. Startup Sequence (3-Step Launch)

Open 3 PowerShell terminals in `e:\Projects\Ai_receptionist`:

### Terminal 1: Backend API & VoiceLink Gateway
```powershell
e:\Projects\Ai_receptionist\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```
*Health Check*: Open `http://localhost:8002/health` in browser — should return `{"status": "ok"}`.

### Terminal 2: Public WebSocket Ingress Tunnel
Using Cloudflare Tunnel (recommended for zero latency jitter):
```powershell
cloudflared tunnel --url http://localhost:8002
```
Or using ngrok:
```powershell
ngrok http 8002
```
*Telephony Hookup*: Copy the assigned HTTPS forwarding URL (e.g. `https://demo.trycloudflare.com`), convert to `wss://demo.trycloudflare.com/api/v1/voice/voicelink/stream`, and set it in the VoiceLink DID media stream configuration.

### Terminal 3: Staff Receptionist Dashboard
```powershell
npm --prefix frontend run dev
```
Open `http://localhost:5173` on the presentation screen.

---

## 5. Live Rehearsal Dialogue Scripts (A to I)

The receptionist supports natural, bilingual conversations in **Hindi, English, and Hinglish**.

---

### Scenario A: Booking for Self (General Medicine)
- **Presenter**: *"Namaste, mujhe Dr. Amit ke paas appointment book karna hai."*
- **AI Receptionist**: *"Dr Amit Kumar General Medicine ke liye upalabdha hain. Aap kal subah 9 baje ya parso shaam 5 baje book karna chahte hain?"*
- **Presenter**: *"Kal subah 9 baje."*
- **AI Receptionist**: *"Dr Amit Kumar ke sath Main Branch mein kal subah 9 baje appointment book kiya ja raha hai. Token number session ke samay milega aur 500 rupaye clinic par dene honge. Kya main ise confirm kar doon?"*
- **Presenter**: *"Haan, bilkul confirm kar dijiye."*
- **AI Receptionist**: *"Dhanyawad! Aapka appointment confirm ho gaya hai. Aapka token number 2 hai aur booking reference GM-XXXXXXXXXX hai. Fee 500 rupaye clinic par jama karni hogi."*
- **Staff Screen**: Within 6 seconds, the new token appears on the dashboard with status `NOT_ARRIVED`.

---

### Scenario B: Booking for Family Member (Mother)
- **Presenter**: *"Hello, I want to book an appointment for my mother Bibha with Dr Sweta."*
- **AI Receptionist**: *"Bibha Gupta ji ke liye Dr Sweta Gupta Gynaecology ke paas kal subah 10 baje ka session available hai. Consultation fee 700 rupees clinic par pay karni hogi. Kya main book kar doon?"*
- **Presenter**: *"Yes please, book it."*
- **AI Receptionist**: *"Thank you! Appointment confirm ho gaya hai. Bibha Gupta ji ka token number 2 hai, booking reference GM-XXXXXXXXXX hai."*

---

### Scenario C: In-Flight Correction (Changing Day or Doctor)
- **Presenter**: *"Mujhe Dr Amit ke paas kal subah ka appointment chahiye."*
- **AI Receptionist**: *"Dr Amit Kumar ke liye kal subah 9 baje ka session available hai. Kya main confirm kar doon?"*
- **Presenter**: *"Nahi, kal nahi, parso shaam ko kar dijiye."*
- **AI Receptionist**: *"Theek hai, parso shaam 5 se 7 baje ka session available hai. Fee 500 rupaye clinic par deni hogi. Kya ise confirm karein?"*
- **Presenter**: *"Haan, yeh sahi hai."*
- **AI Receptionist**: *"Appointment confirm ho gaya hai..."*

---

### Scenario D: Ambiguous Doctor Disambiguation
- **Presenter**: *"I want to see the doctor for fever and cough."*
- **AI Receptionist**: *"General consultation ke liye hamare paas Dr Amit Kumar available hain. Kya aap unke sath appointment chahte hain?"*
- **Presenter**: *"Yes, Dr Amit."*
- *(Proceeds with Offer Readback -> Explicit Confirmation).*

---

### Scenario E: Existing Appointments Lookup
- **Presenter**: *"Mere kaunse appointments scheduled hain?"*
- **AI Receptionist**: *(Binds caller number `+918529586946` on server)* *"Aapke number par Bibha Gupta ji ke liye Dr Sweta Gupta ke sath appointment GM-8B5845F3C1 scheduled hai. Token number 1 hai."*

---

### Scenario F: Guarded Cancellation
- **Presenter**: *"Mujhe Bibha ji ka appointment cancel karna hai."*
- **AI Receptionist**: *"Bibha Gupta ji ka appointment GM-8B5845F3C1 cancel kiya ja raha hai. Kya aap confirm karte hain?"*
- **Presenter**: *"Haan, cancel kar do."*
- **AI Receptionist**: *"Aapka appointment GM-8B5845F3C1 cancel kar diya gaya hai."*
- **Staff Screen**: The record transitions to `CANCELLED` on the dashboard.

---

### Scenario G: Guarded Rescheduling
- **Presenter**: *"Mujhe apna appointment parso ke liye reschedule karna hai."*
- **AI Receptionist**: *"Aapka appointment Dr Amit ke sath parso shaam 5 se 7 baje ke session mein reschedule ho sakta hai. Kya main ise confirm kar doon?"*
- **Presenter**: *"Haan, reschedule kar dijiye."*
- **AI Receptionist**: *"Aapka appointment reschedule ho gaya hai. Naya token number 3 hai aur naya booking reference GM-XXXXXXXXXX hai."*
- **Staff Screen**: The previous booking is cancelled and a linked replacement booking is created.

---

### Scenario H: Live Telephony Barge-In (Interruption)
- **AI Receptionist**: *(Starts speaking)* *"Dr Amit Kumar General Medicine ke liye Main Branch mein kal subah 9 se 12 baje tak..."*
- **Presenter**: *(Speaks over the AI)* *"Haan theek hai, mujhe 9 baje hi chahiye!"*
- **System Action**: Inbound VAD detects speech during playback, immediately transmits `{"event": "clear"}` over the WebSocket, cuts telephone audio within ≤300ms, and transitions smoothly to the readback/confirmation.

---

### Scenario I: Human Fallback & Silence Recovery
- **Presenter**: *"Mujhe kisi human agent ya doctor se baat karni hai."*
- **AI Receptionist**: *"Kshama karein, is samay hamare sabhi staff doosre marizon ki dekhbhal mein vyast hain. Main aapka appointment book, check ya cancel karne mein madad kar sakti hoon."*
- **Presenter**: *(Stays completely silent for 8.5 seconds)*
- **AI Receptionist**: *"Kya aap sun pa rahe hain? Agar aapko appointment mein madad chahiye to kripya batayein."*

---

## 6. Staff Receptionist Desk Verification

During the live demonstration, have a secondary monitor or laptop open with the Receptionist UI:
1. Navigate to `http://localhost:5173/`
2. Select **Main Branch** from the location selector.
3. Observe live updates:
   - Polling automatically syncs every 6 seconds.
   - Clicking **"Refresh"** immediately pulls the latest state from the database.
   - New phone bookings appear instantly with Token Number, Patient Name, Assigned Doctor, and Payment Status (`DUE_AT_CLINIC`).
4. Click on an appointment to demonstrate desk workflows:
   - Mark `ARRIVED` -> Patient enters waiting queue.
   - Mark `IN_CONSULTATION` -> Patient is with doctor.
   - Mark `COMPLETED` -> Consultation finished.

---

## 7. Backup Presentation Path (Web Assistant)

If cellular carrier connectivity or telephone reception in the conference hall is degraded:
1. Navigate to `http://localhost:5173/assistant` in Google Chrome.
2. The Web Assistant provides the same underlying LangGraph agent, tools, server-side caller binding, and transactional engine.
3. You can demonstrate the exact same bilingual dialogue turns via text or microphone input without depending on cellular carrier towers.

---

## 8. Capacity & Operational Limits

| Resource | Verified Safe Tier | Operational Limit & Note |
| :--- | :--- | :--- |
| **Concurrent Calls** | **1 to 5 concurrent calls** | Safe operational tier for conference demo |
| **Call Duration Cap** | **10 minutes (600s)** | Automatic graceful disconnect to prevent runaway sockets |
| **Silence Timeout** | **8.5s** | 2-tier audio reprompt before idle disconnect |
| **Database Pool** | 5 connections (10 overflow) | Adequate for up to 15 concurrent transactional operations |
| **Barge-In Acoustic Cut**| **≤300 ms** | Dispatches WebSocket `clear` event on VAD trigger |
| **Emergency Boundary** | Medical Emergencies | Firm redirect to emergency helplines **112 / 102** |
