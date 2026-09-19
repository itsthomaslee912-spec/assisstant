# Auto AI Email Checker

Real-time Gmail / Outlook inbox classifier. New mail is ingested via provider webhooks, labeled with OpenAI, and pushed to a React dashboard over SSE.

**Branch:** `feature/auto-ai-email-checker`  
**Stack:** React (Vite) frontend · FastAPI backend · SQLite · OpenAI

Labels: `available` · `interview` · `assessment` · `rejected` · `applied` · `alert` · `others`

---

## Easy run (Windows)

One-time setup (creates `.env`, Python venv, npm install):

```bat
scripts\setup.bat
```

Start backend + frontend together (two console windows):

```bat
run.bat
```

Or from PowerShell:

```powershell
.\run.ps1
```

- Backend: http://127.0.0.1:8000  
- Frontend: http://127.0.0.1:5173  

Individual servers: `scripts\run-backend.bat` · `scripts\run-frontend.bat`

---

## Quick start

### 1. Environment

```bash
cp .env.example .env
```

Fill in at least:

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Classification (Chat Completions) |
| `OPENAI_MODEL` | Model id, default `gpt-4o-mini` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Gmail OAuth |
| `MICROSOFT_CLIENT_ID` / `MICROSOFT_CLIENT_SECRET` | Outlook OAuth |
| `GMAIL_PUBSUB_TOPIC` | e.g. `projects/PROJECT/topics/gmail-push` |
| `WEBHOOK_BASE_URL` | Public HTTPS URL (ngrok) for Graph + docs |
| `TOKEN_ENCRYPTION_KEY` | Fernet key (optional; a local fallback exists) |
| `MICROSOFT_WEBHOOK_CLIENT_STATE` | Shared secret for Graph notifications |
| `FRONTEND_ORIGIN` | `http://localhost:5173` |

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 2. Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Health check: [http://localhost:8000/api/health](http://localhost:8000/api/health)

### 3. Frontend

Requires Node.js 18+.

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). The Vite proxy forwards `/api` to the backend.

### 4. Public tunnel (required for webhooks)

```bash
ngrok http 8000
```

Set `WEBHOOK_BASE_URL` to the HTTPS URL (no trailing slash), e.g. `https://abc123.ngrok-free.app`, and restart the backend.

---

## Google (Gmail) setup

1. Create a Google Cloud project.
2. Enable **Gmail API** and **Cloud Pub/Sub API**.
3. Configure OAuth consent screen; create **OAuth client ID** (Web application).
4. Authorized redirect URI: `http://localhost:8000/api/auth/google/callback`
5. Create a Pub/Sub topic, e.g. `gmail-push`.
6. Grant `gmail-api-push@system.gserviceaccount.com` **Pub/Sub Publisher** on that topic.
7. Create a **push** subscription to  
   `https://YOUR_TUNNEL/api/webhooks/gmail`
8. Put the full topic name in `GMAIL_PUBSUB_TOPIC`:  
   `projects/YOUR_PROJECT/topics/gmail-push`

On Connect Gmail, the backend calls `users.watch` and stores `historyId`. Pub/Sub push → fetch new messages → classify → SSE.

---

## Microsoft (Outlook) setup

1. Register an app in [Azure Portal](https://portal.azure.com/) → Microsoft Entra ID → App registrations.
2. Add redirect URI: `http://localhost:8000/api/auth/microsoft/callback` (Web).
3. Create a client secret; copy Application (client) ID and secret into `.env`.
4. API permissions (delegated): `Mail.ReadWrite`, `User.Read`, plus OpenID (`openid`, `profile`, `email`, `offline_access`).
5. Grant admin consent if your tenant requires it.
6. Set `MICROSOFT_WEBHOOK_CLIENT_STATE` to a long random string.
7. Ensure `WEBHOOK_BASE_URL` is HTTPS (Graph requirement).

On Connect Outlook, the backend creates a Graph subscription on `me/mailFolders('Inbox')/messages`. Notifications hit `/api/webhooks/outlook` (validation handshake included). Subscriptions auto-renew hourly when close to expiry.

---

## API overview

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness |
| GET | `/api/auth/google/start` | Start Gmail OAuth |
| GET | `/api/auth/google/callback` | OAuth callback |
| GET | `/api/auth/microsoft/start` | Start Outlook OAuth |
| GET | `/api/auth/microsoft/callback` | OAuth callback |
| GET | `/api/mailboxes` | Connected accounts |
| DELETE | `/api/mailboxes/{id}` | Disconnect |
| POST | `/api/mailboxes/{id}/sync` | Fetch recent mail and classify |
| POST | `/api/mailboxes/{id}/reclassify` | Re-run OpenAI labels on stored mail |
| GET | `/api/emails?label=` | Classified inbox |
| GET | `/api/events` | SSE stream (`email.classified`) |
| POST | `/api/webhooks/gmail` | Pub/Sub push |
| POST | `/api/webhooks/outlook` | Graph notifications |

---

## Repo layout

```
backend/app/          FastAPI app, OAuth, Gmail/Outlook, classifier, webhooks, SSE
frontend/src/         React dashboard (connect + live inbox)
.env.example          Environment template
```

## How OpenAI classifies email

Classification runs on ingest (new mail / **Sync**) and again on **Reclassify**. The core function is `classify_email()` in `backend/app/classify/openai_classifier.py`.

```
Gmail/Outlook → ingest_normalized_message → classify_email
  → keyword heuristics + OpenAI chat.completions
  → merge (alert heuristic can override interview/available/applied)
  → email_messages.label → inbox badges
```

1. Fetch the message (subject, from, snippet, body).
2. Call `classify_email(...)` from `backend/app/services/ingest.py`.
3. Save `label`, `confidence`, and `openai_response_id` on `email_messages`.
4. Push an SSE `email.classified` event so the inbox updates live.

**Reclassify** (`POST /api/mailboxes/{id}/reclassify`) re-runs the same function on up to 200 existing emails without re-fetching from Gmail/Outlook.

### What is sent to OpenAI

Chat Completions with `temperature=0` and `response_format=json_object`:

- **System prompt:** the seven labels and rules (rejected, interview, assessment, applied, alert, available, others).
- **User payload:** `From`, `Subject`, `Snippet`, and the first 6000 characters of `body_text`.

Expected JSON:

```json
{"label":"alert","confidence":0.86}
```

Invalid labels become `others`. The old `tech` label maps to `assessment`.

If `OPENAI_API_KEY` is missing, only keyword heuristics run (or `others`).

### Heuristics vs the model

Rules run first on the combined subject/sender/body:

- Clear rejection / assessment / true interview-invite phrases
- Cold job-description blast (JD + send resume / unsubscribe / job portals) → **alert**

Then OpenAI labels the mail. If heuristics say **alert** but the model says **interview**, **available**, or **applied**, the app **keeps alert**. That is why a recruiter JD that mentions “F2F Interview” is not an interview.

### How to use it

1. Keep `OPENAI_API_KEY` in `.env` and restart the backend after changing it.
2. Click **Sync** to fetch and classify new mail.
3. Click **Reclassify** to relabel mail already in the database (needed after prompt or heuristic changes).

## Notes

- Bid Manage System is intentionally out of scope for this branch.
- Gmail watch lasts ~7 days; Outlook subscriptions ~3 days — the renewal loop refreshes both.
