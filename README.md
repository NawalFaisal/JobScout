# JobScout

Automated scraper that monitors 13 Canadian company career sites for tech internship and co-op postings. Runs on a 30-minute schedule, deduplicates against a PostgreSQL database, scores each posting for relevance, sends Telegram notifications for recent postings, and exposes a REST API with an Excel export and a web dashboard.

---

## Architecture

Three Docker services orchestrated via Compose:

```
[APScheduler / FastAPI]  ──scrapes──>  [Playwright / Chromium]
        |                                       |
        |──writes──>  [PostgreSQL]  <──reads──  |
        |
        |──notifies──>  [Telegram Bot API]
        |
        └──serves──>  GET /dashboard, GET /export/excel, GET /api/*
```

- **backend** — FastAPI application. Runs the scraper, owns the database schema, serves all API endpoints and the dashboard HTML.
- **postgres** — PostgreSQL 15. Single `jobs` table plus an `applications` table for tracking application status.
- **telegram-bot** — Thin wrapper around python-telegram-bot. Queries the backend API; handles `/search`, `/latest`, and `/help` commands.

---

## Companies Monitored

| Banks | Telecom | Tech | Consulting |
|-------|---------|------|------------|
| RBC | Rogers | Amazon | Deloitte |
| TD | Telus | Microsoft | |
| CIBC | Bell | Shopify | |
| Scotiabank | | | |
| BMO | | | |
| Manulife | | | |

Each company has a dedicated scraper. Workday sites (`myworkdayjobs.com`) share a common scraper; RBC, TD, Taleo (Telus), Bell, Amazon, Microsoft, and Shopify each have site-specific implementations. A generic fallback handles anything else.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API framework | FastAPI + Uvicorn |
| Browser automation | Playwright (Chromium, headless) |
| Database | PostgreSQL 15, SQLAlchemy ORM |
| Scheduling | APScheduler (background, 30-minute interval) |
| Notifications | Telegram Bot API (`requests`) |
| Export | Pandas + openpyxl |
| Containerization | Docker, Docker Compose |

---

## Getting Started

**Prerequisites:** Docker and Docker Compose. A Telegram bot token is optional but required for notifications.

```bash
# 1. Clone
git clone https://github.com/NawalFaisal/JobScout.git
cd JobScout

# 2. Configure
cp .env.example .env
# Edit .env — see Configuration section below

# 3. Start
docker compose up --build -d

# 4. Verify
curl http://localhost:8000/health
# {"status":"healthy",...}
```

The scraper runs automatically every 30 minutes. To trigger a run immediately:

```bash
curl -X POST http://localhost:8000/scrape
```

---

## Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes (set automatically by Compose) |
| `TELEGRAM_BOT_TOKEN` | Token from @BotFather | No |
| `TELEGRAM_CHAT_ID` | Your chat ID from @userinfobot | No |

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Service info and list of monitored companies |
| GET | `/health` | Health check |
| GET | `/dashboard` | Web dashboard (HTML) |
| GET | `/jobs` | All saved jobs, ordered by posted date (limit 100) |
| GET | `/api/jobs/search` | Search jobs — params: `keyword`, `company`, `location` |
| GET | `/api/jobs/latest` | 5 most recent internship postings |
| GET | `/api/stats/summary` | Total jobs, last 24h, last 7d, top 5 companies |
| GET | `/stats` | Full per-company job counts |
| POST | `/scrape` | Trigger a background scrape |
| GET | `/export/excel` | Download jobs as a formatted .xlsx file |
| POST | `/jobs/{job_id}/status` | Update application status for a job |
| GET | `/test-scrape` | Synchronous test scrape (debug) |
| GET | `/db-test` | Database connectivity test |

---

## Filtering Logic

Jobs are kept only if the title matches at least one inclusion keyword (intern, co-op, coop, co op, new grad, junior, entry level, summer 2026, graduate) and contains a tech-related term. A separate exclusion list drops non-technical roles (mechanical, civil, sales, marketing, etc.).

Each saved job receives a relevance score (1–10) based on how many of the five core keywords appear in the title and description.

---

## Excel Export

`GET /export/excel` returns a multi-sheet workbook:

- **Summary** — total count, per-company breakdown, embedded bar chart
- **All Jobs** — full dataset, color-coded by posting age (red < 1h, yellow < 3h)
- **Per-company sheets** — one sheet per company with the same formatting

---

## Project Structure

```
JobScout/
├── backend/
│   ├── main.py              # FastAPI app, scrapers, scheduler, API endpoints
│   ├── Dockerfile
│   └── requirements.txt
├── telegram-bot/
│   ├── bot.py               # Telegram command handlers, queries backend API
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   └── dashboard.html       # Single-file dashboard, served at /dashboard
├── docker-compose.yml
└── .env
```

---

## Development

```bash
# Run backend locally without Docker
cd backend
pip install -r requirements.txt
playwright install chromium
DATABASE_URL=postgresql://... uvicorn main:app --reload

# Tail logs
docker compose logs -f backend

# Open a shell in the backend container
docker exec -it jobscout-backend bash
```

---

## Author

Nawal Faisal — [GitHub](https://github.com/NawalFaisal) · [LinkedIn](https://linkedin.com/in/nawalfaisal)
