# RedditPilot

RedditPilot is a local, human-in-the-loop Reddit editorial workspace. It uses Gemini to draft posts from an honest project brief and recorded community rules, then requires a person to review, edit, and approve the exact version before anything can be published. It never approves or publishes on its own.

The dashboard is a dark editorial-style React application served by the FastAPI backend. All data lives in a local SQLite database. No sample project is seeded: the workspace starts empty and everything in it is data you create.

## Why it is deliberately constrained

- AI output is always `Pending Review`.
- Approval is tied to a content hash. Editing, regenerating, archiving, or rejecting invalidates the approval.
- Publishing requires a valid approval and zero compliance blockers.
- The scheduler only creates review drafts. It cannot approve or publish.
- Manual publishing works without Reddit credentials. You submit on Reddit yourself and record the resulting URL.
- Reddit API publishing is optional, disabled by default, and requires three separate things: API mode, explicit API enablement, and a final confirmation for every submission.
- There is one publication record per draft, enforced by the database. Uncertain API results are recorded for manual resolution and are never retried automatically.
- The app does not scrape Reddit, mass-post, manipulate engagement, use multiple accounts, or help evade bans.
- Metrics are entered by hand. The app does not imply automatic Reddit analytics.

## Features

- **Overview** - pending approvals, blockers, weekly rhythm, upcoming slots, recent publications, manual metrics, activity journal, AI usage, and rules hygiene.
- **Content Studio** - project/community-aware brief, objective, post type, topic, link preference, and notes; Gemini returns structured JSON with title, body, disclosure, optional link, relevance, rule concerns, promotional intensity, and warnings.
- **Draft Queue** - search and status filters, full draft editor, revision history, compliance report, approve/reject/regenerate/duplicate/archive/restore/delete, manual publishing, and API publishing.
- **Subreddit Manager** - self-promotion policy, link policy, allowed post types, account age/karma guidance, recorded rules, notes, suitability status, and rules verification dates.
- **Publishing Calendar** - per-project weekly plan, month calendar, upcoming slots, pause/resume, manual tick, skip, and retry.
- **Published Posts** - publication records, manual metric snapshots, CTR, metric history, and resolution of uncertain API submissions.
- **Analytics** - weekly engagement, referral traffic, community breakdown, publishing-mode split, and only the data you recorded.
- **Projects** - complete product brief CRUD, archive/restore, and guardrails against deleting projects with history.
- **Settings** - Gemini key/model/test, generation preferences, publishing mode, encrypted Reddit credentials, weekly cadence, timezone, backup/export, activity log, and the app's non-negotiable boundaries.

## Requirements

- Windows 10 or 11 (the app is plain Python/Node and also runs on macOS/Linux).
- Python 3.12 or newer.
- Node.js 20 or newer with npm (only needed to build the dashboard).
- Optional: a Gemini API key from Google AI Studio.
- Optional: a legitimate Reddit API application and account.

Tested in this repository with Python 3.14.3 and Node 25.2.1.

## Quick start on Windows

From the project folder:

```bat
scripts\start.bat
```

The script will:

1. Create `.venv` and install `requirements.txt` if needed.
2. Copy `.env.example` to `.env` if `.env` is missing.
3. Build `frontend/dist` if it is missing.
4. Run `scripts/init_db.py` to create or upgrade the SQLite schema.
5. Open `http://127.0.0.1:8000` and start the FastAPI server.

Press `Ctrl+C` in the terminal to stop the server.

To change the host or port:

```bat
set RP_PORT=8080
scripts\start.bat
```

If you change frontend source, rebuild it:

```bat
cd frontend
npm run build
```

## Manual setup

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
copy .env.example .env

python scripts\init_db.py

cd frontend
npm install
npm run build
cd ..

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. API documentation is at `http://127.0.0.1:8000/docs`.

For frontend development with hot reload:

```bat
cd frontend
npm run dev
```

The Vite dev server runs on port 5173 and proxies `/api` to the backend on port 8000.

## First-run checklist

1. Open **Settings** and add a Gemini API key, or put `GEMINI_API_KEY` in `.env`. Use **Test connection**.
2. Open **Projects** and create a project with a real website URL, audience, voice, disclosure, and restricted claims.
3. Open **Subreddit Manager** and add the communities you genuinely want to participate in. Read their current rules yourself, record the substance, set the policies, and use **Mark verified**. Unknown or stale rules produce warnings or blockers.
4. Open **Publishing Calendar**, choose the project, and save an enabled weekly plan. The default cadence is one post per week on Monday at 10:00 in `Asia/Kathmandu`; change it in **Settings**.
5. Generate a draft in **Content Studio** or let the scheduler create one inside its 72-hour lead window.
6. Review the exact content in **Draft Queue**, resolve blockers, approve it with the attestation checkbox, then publish manually or through the authorized API.

## Gemini configuration

The key can come from either source:

- `GEMINI_API_KEY` in `.env` (or the process environment).
- The **Settings** form, where it is encrypted with Fernet before being written to SQLite.

A key saved in the database takes precedence over the environment. The key is never returned by the API; the UI only learns whether a key is configured and where it came from.

The default model is `gemini-2.5-flash`. You can change it in Settings. Generation uses structured JSON output and validates the response before storing a `Pending Review` draft. No generated content is ever auto-approved.

## Optional Reddit API setup

Manual publishing is the default and needs no Reddit credentials. API publishing is a separate, explicit mode.

1. Create a Reddit API application at <https://www.reddit.com/prefs/apps>. A **web app** with a redirect URI such as `http://localhost:8080` is the most flexible choice. A **script** app can also work with a username/password.
2. In **Settings**, enter:
   - Client ID
   - Client secret
   - Reddit username (without `u/`)
   - Password, or preferably a refresh token
   - A descriptive user agent, for example `redditpilot/1.0 by u/yourname`
3. Save credentials. They are encrypted at rest and never returned by the API.
4. Select **Reddit API** mode, enable **API publishing**, and tick the acknowledgement. Save.
5. Use **Verify account**. Verification calls Reddit's identity endpoint and never submits a post. It requires API publishing to be enabled.

To obtain a refresh token with PRAW, create a web app with redirect URI `http://localhost:8080`, then run a one-off script like this in the project virtual environment:

```python
import praw

reddit = praw.Reddit(
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
    user_agent="redditpilot/1.0 by u/YOUR_USERNAME",
    redirect_uri="http://localhost:8080",
)
print(reddit.auth.url(["identity", "read", "submit"], "redditpilot", "permanent"))
# Open the printed URL, authorize, then copy the `code` query parameter.
print(reddit.auth.authorize("PASTE_CODE_HERE"))
```

Paste the resulting refresh token into Settings. Keep it secret. Reddit's API terms, rate limits, and commercial-use requirements are your responsibility. Use one legitimate account and only the communities where you are genuinely welcome.

### API publishing behavior

- Requires API mode, API enablement, stored credentials, a valid approval for the exact content hash, zero compliance blockers, and a suitable/eligible community.
- Re-validates the account identity before submission.
- Submits exactly one post through PRAW. There is no automatic retry.
- If the result is uncertain (for example a network failure after the request), the attempt is recorded as `uncertain`, the draft is marked failed, and the app tells you to check Reddit. Resolve it from **Published Posts**. If the post exists, record its URL; if it does not, remove the uncertain record and return the draft to `Approved` for a deliberate next decision.
- A draft can have only one publication record. The database unique constraint, a publish lock, and pre-flight checks prevent double publication.

## Publishing modes

| | Manual | Reddit API |
|---|---|---|
| Default | Yes | No |
| Needs Reddit credentials | No | Yes |
| Needs approval and clean compliance | Yes | Yes |
| Who submits | You, on Reddit | PRAW, after final confirmation |
| Final confirmation | Paste URL and confirm | Explicit acknowledgement and **Submit once** |
| Auto-retry | Not applicable | Never |

In manual mode the app prepares the exact title and body. **Copy & open Reddit** opens the prefilled submit page in one click and copies the body as a fallback, then you publish it yourself. **Paste** fills the URL field from your clipboard only when you click it; automatic clipboard detection is off. The URL must be a `reddit.com/r/<that-subreddit>/comments/...` URL, and the app validates it before recording the publication. Nothing is submitted on your behalf.

## Approval lifecycle

- Every generated or duplicated draft starts as `Pending Review`.
- Approval records the approver, note, timestamp, and the exact content hash.
- Any edit to title, body, disclosure, or link changes the hash, invalidates the approval, and returns the draft to `Pending Review`.
- Regeneration, rejection, and archiving also invalidate approval.
- Publishing re-evaluates compliance at the publish stage. An approval alone is not enough.
- The UI disables approval while compliance blockers exist.

## Weekly scheduling

- The schedule is stored in the database (`scheduled_posts`); APScheduler is only a trigger that runs a tick every 15 minutes.
- Each tick is idempotent. Restarts do not duplicate slots.
- Slots are materialized for the current week and the next four weeks.
- A draft is generated only inside the 72-hour lead window for a slot.
- Slots older than six hours without a draft are marked skipped.
- Generation requires an enabled plan, an active project, a community, and a Gemini key.
- Pausing scheduling stops materialization, generation, and publication of scheduled drafts.
- **Run tick now** in the calendar is useful for testing; it still only creates review drafts.
- The scheduler never approves, never publishes, and never bypasses the queue.

## Compliance engine

The engine runs at review and publish stages. Publish-stage checks are stricter. It covers:

- Empty/short title or body; body over Reddit's 40,000-character self-post limit.
- Prohibited or restricted promotion, unknown promotion policy, and promotional intensity above your configured limit.
- Missing disclosure for promotional content.
- Links when the community does not allow them, restricted/unknown link policies, and links to a host other than the project website.
- Post types not recorded as allowed.
- Duplicate exact titles and highly similar bodies (blocker at publishing).
- All-caps and clickbait titles, excessive emoji, repetitive copy, and possible unverified statistical claims.
- Restricted claims from the project brief.
- Missing, aging (over 90 days), or stale (over 180 days) rules verification.
- Communities marked prohibited or not recommended.
- Weekly project limit reached (default 1 published post in the last 7 days; configurable to 3).
- Existing publication records and identical content already published elsewhere in the project.
- Missing or stale approval at publish time.

Recorded community rules are user-maintained notes. RedditPilot does not monitor Reddit for rule changes, and it cannot guarantee that a post complies with a community's live rules or Reddit's terms. You remain responsible for reading them.

## Data, backup, and restore

All application data is in `data/`:

- `data/redditpilot.db` - SQLite database (WAL mode).
- `data/.secret_key` - local Fernet key generated on first use if `APP_SECRET_KEY` is empty.
- `data/backups/` - backups created by the app or scripts.
- `logs/redditpilot.log` - rotating application log.

Create a consistent backup:

```bat
scripts\backup.bat
```

Or from the dashboard: **Settings > Data, backups & journal > Download backup**. The JSON export contains projects, communities, rules, drafts, revisions, approvals, schedules, publications, and metrics, but excludes secrets.

Restore procedure:

1. Stop the server.
2. Copy the backup file over `data/redditpilot.db`.
3. Restore the matching `.secret_key`, or set the same `APP_SECRET_KEY` in `.env`.
4. Start the server and run `scripts\init_db.py` to apply any pending migrations.

Without the matching encryption key, stored Gemini/Reddit credentials cannot be decrypted. Re-enter them in Settings; drafts and publications are unaffected.

Never commit `.env`, `data/.secret_key`, the database, or backups to source control. `.gitignore` already excludes them.

## Security notes

- This is a single-user local application. It has no login layer. Run it on `127.0.0.1` and do not expose it directly to the internet.
- If you need remote access, put it behind a reverse proxy with TLS and strong authentication, restrict access by network, and keep the database and encryption key private.
- Credentials are encrypted at rest, but anyone with both the database and the key can decrypt them.
- CORS is limited to local development origins. API docs are available at `/docs`.
- Logs avoid secrets. PRAW logging is reduced to warnings.
- API publishing must never be used to spam, mass-post, evade moderation, or operate fake accounts.

## Project structure

```text
app/
  main.py              FastAPI app, static dashboard serving, scheduler lifecycle
  config.py            environment configuration
  db.py                SQLAlchemy engine/session, UTC helpers
  models.py            projects, communities, rules, drafts, approvals, schedules, publications
  schemas.py           Pydantic request/response contracts
  security.py          Fernet credential encryption
  routers/             REST endpoints
  services/            Gemini, compliance, drafts, publishing, scheduling, serialization
migrations/            Alembic migration environment and initial schema
scripts/               init_db, backup_db, Windows start/backup helpers
frontend/              React + Vite dashboard (custom CSS, no component library)
tests/                 pytest suite with mocked Gemini/PRAW and a throwaway database
data/                  local runtime data (gitignored)
logs/                  rotating logs (gitignored)
```

## Tests

```bat
.venv\Scripts\python.exe -m pytest -q
```

The suite uses a temporary SQLite database, a generated test encryption key, `DISABLE_SCHEDULER=1`, and mocked Gemini/Reddit services. It does not make network calls or use real credentials. It covers approval requirements, compliance blockers, edit invalidation, manual/API publishing guards, double-publication prevention, scheduling idempotency and approval separation, settings/encryption, projects, communities, analytics, and Gemini response validation.

## Useful API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Health and scheduler status |
| GET | `/api/meta` | Objectives, post types, weekdays, statuses |
| GET/POST | `/api/projects` | List/create projects |
| GET/PATCH/DELETE | `/api/projects/{id}` | Project detail/update/delete |
| GET/POST | `/api/subreddits` | List/create communities |
| GET/PATCH/DELETE | `/api/subreddits/{id}` | Community detail/update/delete |
| POST | `/api/subreddits/{id}/verify` | Mark rules verified now |
| GET | `/api/drafts` | Filter/search draft queue |
| POST | `/api/drafts/generate` | Generate a Pending Review draft |
| GET/PATCH | `/api/drafts/{id}` | Detail/update (updates invalidate approval) |
| POST | `/api/drafts/{id}/approve` | Record human approval (attestation required) |
| POST | `/api/drafts/{id}/reject` | Reject with a reason |
| GET | `/api/drafts/{id}/publish/check` | Publishing eligibility and blockers |
| POST | `/api/drafts/{id}/publish/manual/prepare` | Get copy and submit URL |
| POST | `/api/drafts/{id}/publish/manual/confirm` | Record a manual publication URL |
| POST | `/api/drafts/{id}/publish/api` | Submit once through PRAW |
| GET | `/api/schedule` | Slots for the calendar |
| GET/PUT | `/api/schedule/plan/{project_id}` | Read/save the weekly plan |
| POST | `/api/schedule/tick` | Run one idempotent scheduling tick |
| GET | `/api/published` | Publication records |
| PATCH | `/api/published/{id}/metrics` | Append a manual metric snapshot |
| POST | `/api/published/{id}/resolve` | Resolve an uncertain API submission |
| GET | `/api/analytics` | Weekly and per-community analytics |
| GET/PATCH | `/api/settings` | Settings (secrets never returned) |
| POST | `/api/settings/test-gemini` | Test the Gemini key |
| GET | `/api/settings/export` | JSON export without secrets |
| GET/POST | `/api/settings/backup` | Download a SQLite backup |
| GET | `/api/settings/activity` | Activity journal |

## Troubleshooting

**The dashboard shows build instructions instead of the app.** Build it with `cd frontend && npm run build`, then restart the server.

**Gemini test fails with 502.** Check the key, model name, internet access, and the 90-second timeout. The key may be invalid or the model unavailable to your account.

**Generation says no API key.** Add a key in Settings or set `GEMINI_API_KEY` in `.env` and restart. A database key overrides the environment.

**The scheduler is idle.** Confirm scheduling is not paused, the project plan is enabled, a Gemini key exists, and the slot is within 72 hours. Use **Run tick now** and read the activity journal.

**Reddit verification fails.** Confirm client ID/secret, account, refresh token or password, user agent, app type, scopes (`identity`, `read`, `submit`), and that API publishing is enabled.

**Publishing is blocked.** Read the compliance report in the Draft Queue. Common blockers are missing disclosure, prohibited promotion, stale rules, duplicate content, a weekly limit, or a missing/stale approval.

**I lost the encryption key.** Re-enter Gemini and Reddit credentials in Settings. Existing drafts and publications are unaffected.

**Port 8000 is busy.** Start with another port: `set RP_PORT=8080` then `scripts\start.bat`, or run `uvicorn app.main:app --port 8080`.

## Limitations

- Metrics are manual; there is no Reddit analytics scraping or automatic tracking.
- Community rules are recorded notes, not a live feed. Verify them yourself.
- The scheduler drafts; it does not publish.
- Reddit API access, rate limits, and commercial-use approval are external prerequisites.
- This is a local single-user tool, not a multi-tenant hosted service.

## License and responsible use

Use RedditPilot only for genuine participation in communities where self-promotion is allowed and disclosed. Follow each community's rules, Reddit's content policy, and Reddit's API terms. The software is provided as-is; you are responsible for what you publish and for the credentials you store.
