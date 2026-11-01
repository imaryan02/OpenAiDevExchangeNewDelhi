# Production Deployment Guide: Backend on Azure + Frontend on Vercel

**Architecture**:
- **Backend**: FastAPI + LangGraph + WebSockets on **Azure Container Apps** (Uses Azure credits, persistent telephony WebSockets, auto-scaling, built-in HTTPS/WSS).
- **Frontend**: React + Vite SPA on **Vercel** (Free global edge CDN, automatic deploys on `git push`, instant SSL).
- **Database**: Supabase PostgreSQL (Managed cloud DB).
- **Telephony**: VoiceLink (SIP/DID connecting to Azure WebSocket).

---

## Prerequisites
1. **Azure Account** with active credits ([portal.azure.com](https://portal.azure.com)).
2. **Vercel Account** ([vercel.com](https://vercel.com)) connected to your GitHub.
3. Your GitHub repository: [`https://github.com/imaryan02/Ai_voice_receptionist`](https://github.com/imaryan02/Ai_voice_receptionist).

---

## Part 1: Deploy Backend to Azure Container Apps (ACA)

You can deploy directly using the **Azure Portal** (no local Docker or CLI required — Azure will build the Dockerfile in the cloud for you):

### Step 1: Create an Azure Container App
1. Log in to [portal.azure.com](https://portal.azure.com).
2. In the top search bar, type **Container Apps** and click **Create**.
3. Fill in the **Basics** tab:
   - **Subscription**: Your active subscription with credits.
   - **Resource Group**: Create new (e.g., `rg-ai-receptionist`).
   - **Container App Name**: e.g., `ai-receptionist-api`.
   - **Region**: Choose a region close to India (e.g., `Central India` or `Southeast Asia`).
   - **Container Apps Environment**: Click **Create new** (e.g., `env-ai-receptionist`, default Consumption workload profile).

### Step 2: Configure Container Source (From GitHub)
4. In the **App settings / Container** section:
   - If deploying via **GitHub Actions** (Easiest):
     - Check **Build and deploy from source code** or select **GitHub**.
     - Repository: `imaryan02/Ai_voice_receptionist`
     - Branch: `main`
     - Build type: **Dockerfile**
     - Dockerfile path: `backend/Dockerfile`
     - Context path: `backend`
   - *Alternative (via Container Registry)*:
     - If you have an image in Docker Hub or Azure Container Registry (ACR), enter the image tag directly.

### Step 3: Configure Networking & Ingress (Crucial for WebSockets)
5. In the **Ingress** tab:
   - **Ingress**: Select **Enabled**.
   - **Ingress traffic**: Select **Accepting traffic from anywhere** (External).
   - **Ingress type**: **HTTP**.
   - **Target port**: `8002` (Matches the backend port).
   - **Transport**: `Auto` or `HTTP/1.1` (Azure Container Apps natively supports WebSocket upgrade requests).

### Step 4: Add Environment Variables
6. In the **Configuration / Environment Variables** section, add your backend secrets from your `backend/.env`:
   - `APP_ENVIRONMENT`: `production`
   - `DATABASE_URL`: `postgresql+asyncpg://...` (Your Supabase connection string)
   - `OPENAI_API_KEY`: `sk-...`
   - `OPENAI_MODEL`: `gpt-4o-mini`
   - `OPENAI_TRANSCRIPTION_MODEL`: `gpt-4o-mini-transcribe`
   - `OPENAI_TTS_MODEL`: `gpt-4o-mini-tts`
   - `OPENAI_TTS_VOICE`: `coral`
   - `OPENAI_TTS_SPEED`: `0.95` (normal conversational pacing; supersedes the earlier `0.85` setting)
   - `SUPABASE_URL`: `https://<your-project-ref>.supabase.co`
   - `SUPABASE_PUBLISHABLE_KEY`: `eyJ...`
   - `SUPABASE_JWT_SECRET`: `your-supabase-jwt-secret`
   - `CORS_ORIGINS`: `["*"]` *(Update to your Vercel URL once frontend is live)*
   - `VOICELINK_PHONE_NUMBER`: `+919429397279`
   - `VOICELINK_STREAM_SECRET`: `<your-random-secret>`
   - `VOICE_ORGANIZATION_ID`: `c562e817-bfae-4428-904d-15ac84b9acd7`
   - `VOICE_ACTOR_ID`: UUID of the authorized voice service actor
   - `VERIFICATION_CODE_PEPPER`: a stable random secret used for voice verification
7. Click **Review + Create**, then **Create**.
8. Once deployment completes, copy your **Application URL** from the overview page:
   `https://ai-receptionist-api.<unique-hash>.<region>.azurecontainerapps.io`
9. **Verify Health**:
   Open in browser: `https://ai-receptionist-api.<unique-hash>.<region>.azurecontainerapps.io/health/live`
   You should see: `{"status":"ok","detail":null}`.

### Step 5: Keep the phone backend running

In **Scale and replicas**, set **Minimum replicas** to **1** (or higher). A phone
carrier cannot reliably wait for a container to start after scaling to zero.
This keeps an idle replica allocated and consumes Azure credits even between calls.
The GitHub deployment workflow enforces a minimum of one on subsequent deployments.

For the existing deployment, run in Azure Cloud Shell:

```bash
az containerapp update --name ai-receptionist-backend --resource-group rg-ai-receptionist --min-replicas 1
az containerapp show --name ai-receptionist-backend --resource-group rg-ai-receptionist --query '{minimum:properties.template.scale.minReplicas,revision:properties.latestReadyRevisionName,traffic:properties.configuration.ingress.traffic}'
```

Check each active revision receiving traffic, especially if multiple-revision mode
is enabled. Old revisions can still have different secrets, images, and scale
settings. Make changes outside active calls: a revision replacement or restart
can terminate an established WebSocket. Configure Azure startup/liveness probes
against `/health/live` on port 8002; the Dockerfile healthcheck alone is not an
Azure probe configuration. Do not restart containers merely because an external
database or AI provider is temporarily unavailable.

---

## Part 2: Deploy Frontend to Vercel

### Step 1: Import Project in Vercel
1. Go to [vercel.com/new](https://vercel.com/new).
2. Find `imaryan02/Ai_voice_receptionist` and click **Import**.

### Step 2: Configure Build Settings
3. Configure the project settings:
   - **Framework Preset**: Select **Vite**.
   - **Root Directory**: Click **Edit** and choose `frontend`.
   - **Build Command**: `npm run build` (Default)
   - **Output Directory**: `dist` (Default)

### Step 3: Add Environment Variables
4. Expand **Environment Variables** and add:
   - `VITE_API_BASE_URL`: `https://ai-receptionist-api.<unique-hash>.<region>.azurecontainerapps.io` (Your Azure Backend URL without trailing slash)
   - `VITE_SUPABASE_URL`: `https://<your-project-ref>.supabase.co`
   - `VITE_SUPABASE_PUBLISHABLE_KEY`: `<your-supabase-publishable-key>`

### Step 4: Deploy
5. Click **Deploy**.
6. Vercel will build your app and give you your production URL (e.g. `https://ai-voice-receptionist.vercel.app`).
7. Open the URL and verify that the receptionist desk loads and connects to the backend!

---

## Part 3: Connect VoiceLink Live Telephony

Now that your backend is running on a permanent public URL on Azure with SSL:

1. Log in to your **VoiceLink Portal** ([voicelink.co.in](https://voicelink.co.in)).
2. Go to **Phone Numbers / DID Management** -> Select `+919429397279`.
3. In the **Media Stream / WebSocket URL** field, set:
   ```text
   wss://ai-receptionist-api.<unique-hash>.<region>.azurecontainerapps.io/v1/voicelink/media?token=<URL-encoded-VOICELINK_STREAM_SECRET>
   ```
4. Save the configuration.

The path must be `/v1/voicelink/media`, and the token must match the Azure
`VOICELINK_STREAM_SECRET`. If supported, set the call event callback to
`https://<your-azure-app>/v1/voicelink/events?token=<URL-encoded-VOICELINK_STREAM_SECRET>`.
Do not publish these token-bearing URLs or paste them into tickets.

---

## Part 4: Post-Deployment Lockdown (CORS)

Once your Vercel URL is known (e.g. `https://ai-voice-receptionist.vercel.app`):
1. Go to Azure Portal -> **ai-receptionist-api** -> **Configuration** / **Environment Variables**.
2. Update `CORS_ORIGINS`:
   ```json
   ["https://ai-voice-receptionist.vercel.app", "http://localhost:5173"]
   ```
3. Save and restart the revision.

---

## Verification & Live Test Checklist

- [ ] `https://<your-azure-app>.azurecontainerapps.io/health/live` returns `{"status":"ok"}`.
- [ ] `https://<your-azure-app>.azurecontainerapps.io/health/ready` returns `{"status":"ok"}`.
- [ ] Vercel dashboard shows green status and renders the Geeta Medicine Reception Desk.
- [ ] Call `+919429397279` from a cell phone:
  - Receptionist answers with greeting: *"Namaste, Geeta Medicine mein aapka swagat hai..."*
  - Complete a test booking.
  - Check the Vercel dashboard: the new booking appears within 6 seconds on the desk!
