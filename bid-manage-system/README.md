# Bid Manage System

Responsive bid and job-application management for admins and bidders.

## Stack

- React, TypeScript, Vite, Ant Design
- FastAPI, SQLAlchemy, SQLite
- Database-backed bearer sessions and PBKDF2 password hashing

## Start

For Neon PostgreSQL, create `backend/.env` (this is ignored by Git):

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require
INITIAL_ADMIN_EMAIL=your-admin@example.com
INITIAL_ADMIN_USER_ID=your-admin-id
INITIAL_ADMIN_PASSWORD=use-a-strong-password
```

Without `DATABASE_URL`, the application uses local SQLite for development.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 9013
```

In a second terminal:

```powershell
cd frontend
npm install
npm.cmd run dev
```

Or run `./run.ps1` after dependencies have been installed.

- Frontend: `http://127.0.0.1:9012`
- Backend: `http://127.0.0.1:9013`

## Initial administrator

Set the three `INITIAL_ADMIN_*` environment values before the first startup. Credentials are never committed to source control.

## Vercel deployment

Import the repository into Vercel and set the project **Root Directory** to `bid-manage-system`. Add `DATABASE_URL`, `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_USER_ID`, and `INITIAL_ADMIN_PASSWORD` under Project Settings → Environment Variables, then deploy.
