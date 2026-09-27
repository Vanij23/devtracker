# DevTracker

A personal job/internship application tracker — replaces the spreadsheet with
a real dashboard. Track every application through Applied → OA → Interview →
Offer/Rejected, log interview rounds, get AI-generated prep tips and
feedback, and bulk-import applications from a pasted list.

## Features

- Signup/login with hashed passwords (Flask-Login + Werkzeug)
- Full CRUD on applications, scoped per user
- Kanban-style dashboard grouped by status, with quick "move to next stage"
- Interview rounds with scheduled date/time and per-round status
- **AI Copilot**: prep tips (Applied/OA/Interview), feedback (Rejected), or
  negotiation pointers (Offer) — generated per application
- **Ask DevTracker**: a floating assistant for general job-search questions
- **Bulk import**: paste a list of applications (e.g. from Internshala or
  LinkedIn) and have them parsed and created automatically
- All AI features fall back to safe placeholder text if no API key is set,
  so the app never crashes without one

## Tech stack

Python · Flask · SQLAlchemy · PostgreSQL (Neon) · Flask-Login · Jinja2 ·
Bootstrap · Anthropic API · deployed on Vercel

## Local setup

```bash
python -m venv venv
# Windows:
.\venv\Scripts\Activate.ps1
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # then fill in the values below
python init_db.py
python app.py
```

Open `http://127.0.0.1:5000`.

**Windows note:** if `psycopg2-binary` fails to build (needs a C compiler),
install everything else and skip it for local dev:
```powershell
pip install Flask Flask-SQLAlchemy Flask-Login python-dotenv Werkzeug gunicorn anthropic
```
Then use SQLite locally (see `.env` below) — `psycopg2-binary` is only
needed for a real Postgres connection, which Vercel's Linux build handles
without issue.

### `.env` values

```dotenv
SECRET_KEY=any-random-string
DATABASE_URL=sqlite:///devtracker.db     # local dev
ANTHROPIC_API_KEY=                        # optional — see below
```

For a real Postgres database (needed for deployment), get a free one at
[neon.tech](https://neon.tech) and use the connection string it gives you
instead of the SQLite URL.

### Enabling real AI responses

Without `ANTHROPIC_API_KEY` set, the AI Copilot, Ask DevTracker widget, and
Bulk Import all fall back to template-based responses instead of crashing.
To get real AI-generated answers, get a key at
[console.anthropic.com](https://console.anthropic.com) and add it to `.env`.

## Architecture

```
app.py          — Flask app factory + all routes
models.py       — User, Application, InterviewRound (SQLAlchemy models)
ai_helper.py    — AI Copilot, Ask DevTracker, and bulk-import parsing
extensions.py   — db and login_manager instances
config.py       — reads environment variables
templates/      — Jinja2 templates
static/css/     — stylesheet
api/index.py    — Vercel serverless entry point (wraps the Flask app)
vercel.json     — Vercel routing config
```

Each `Application` belongs to a `User`; each `InterviewRound` belongs to an
`Application` — a standard one-to-many relationship in both cases.

## Deploying to Vercel

1. Push this project to a GitHub repository (see steps below).
2. Create a free Postgres database at [neon.tech](https://neon.tech) and
   copy its connection string.
3. Run the schema against that database once, from your local machine:
   ```bash
   # temporarily point DATABASE_URL in .env at your Neon connection string
   python init_db.py
   ```
4. Go to [vercel.com](https://vercel.com) → New Project → import your GitHub
   repo.
5. In the project's Environment Variables settings, add:
   - `DATABASE_URL` — your Neon connection string
   - `SECRET_KEY` — a random string
   - `ANTHROPIC_API_KEY` — optional
6. Deploy. Every push to `main` redeploys automatically.

**Why Neon and not SQLite in production:** Vercel's filesystem is read-only
and ephemeral for serverless functions — a SQLite file wouldn't persist
between requests or deployments. Postgres is required for anything beyond
local development.
