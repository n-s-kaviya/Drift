# Smart Market Watchlist

A full-stack market watchlist that answers one question: **what meaningfully changed since you last looked?**

Instead of hardcoding "a 2% move is big," each stock's own history defines normal behavior via streaming clustering. A lightweight online classifier learns which regime shifts you actually care about — with safeguards against cold-start feedback loops.

## Architecture

```
Market data → Ingestion (rolling features, staleness tags, tick validation)
           → Regime detection (DBSTREAM per instrument, shared across users)
           → Change event store (PostgreSQL)
           → Personalization (Hoeffding tree + bootstrap/epsilon-greedy) + Watchlist API
           → React dashboard (Vite)
```

## Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI, SQLAlchemy, River, PostgreSQL |
| Frontend | React 19, Vite, TypeScript, Tailwind CSS |
| Data | Finnhub (live) → yfinance → demo fallback |
| ML | DBSTREAM clustering, Hoeffding tree classifier |

**PostgreSQL is required.** SQLite is not supported.

---

## Setup

### Prerequisites

| Tool | Notes |
|------|-------|
| **Python 3.11+** | [python.org/downloads](https://www.python.org/downloads/) — check "Add Python to PATH" on Windows |
| **Node.js 18+** | [nodejs.org](https://nodejs.org/) |
| **PostgreSQL 16** | [postgresql.org/download](https://www.postgresql.org/download/) — or use Docker (below) |
| **Git** (optional) | For cloning/updating the repo |

### Project structure

```
Drift/
├── backend/
│   ├── app/
│   ├── requirements.txt
│   └── .env                 ← you create this
├── frontend/
│   ├── src/
│   ├── package.json
│   └── .env                 ← optional
├── docker-compose.yml       ← optional (Postgres via Docker)
└── README.md
```

---

### 1. Start PostgreSQL

#### Option A — Docker

```bash
docker compose up -d
```

Creates user `watchlist`, password `watchlist`, database `watchlist` on port `5432`.

#### Option B — Local Postgres

Create the database once (pgAdmin or psql):

```sql
CREATE USER watchlist WITH PASSWORD 'watchlist';
CREATE DATABASE watchlist OWNER watchlist;
GRANT ALL PRIVILEGES ON DATABASE watchlist TO watchlist;
```

Default connection string:

```
postgresql+psycopg2://postgres:username@localhost:5432/watchlist
```

Tables are created automatically when the backend starts — no manual migrations needed.

---

### 2. Backend

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8765
```

#### Create `backend/.env`

```env
DATABASE_URL=postgresql+psycopg2://postgres:username@localhost:5432/watchlist

# Free key from https://finnhub.io/register
FINNHUB_API_KEY=your_actual_key_here

# auto = finnhub → yfinance → demo | finnhub | yfinance | demo
MARKET_DATA_PROVIDER=finnhub
```

**Tips:**
- Use `MARKET_DATA_PROVIDER=finnhub` for live demo day (recommended).
- Use `MARKET_DATA_PROVIDER=demo` if Finnhub/yfinance fail on your network.

---

### 3. Frontend

#### Linux / macOS / Windows

```bash
cd frontend
npm install
npm run dev
```

Open http://192.168.1.39:43123/

---

### 4. First use

1. **Register** a new account (email + password, min 6 characters).
2. **Add stocks** — type a symbol (e.g. `AAPL`) or pick from **Browse by category** (Tech, Finance, etc.).
3. Hit **Refresh** a few times — alerts need ~8 data ticks per symbol before they appear (cold start).
4. Use **Auto-refresh** in the header to enable/disable price updates and pick an interval (15s–2min).
5. **Refresh** runs a full update (alerts + prices). Auto-refresh only updates prices.

---

### Troubleshooting

| Problem | Fix |
|---------|-----|
| `column instruments.last_event_times does not exist` | Use latest `backend/app/database.py` — auto-migrates on startup |
| `router is not defined` | Use latest `backend/app/routers/dashboard.py` |
| Backend won't start / DB error | Confirm Postgres is running; check `DATABASE_URL` in `.env` |
| No live prices | Add `FINNHUB_API_KEY`; set `MARKET_DATA_PROVIDER=finnhub` |
| No volume alerts | Finnhub needs latest `market_data.py` (fetches daily candle volume) |
| Frontend can't reach API | Backend must run on port **8765**; check `VITE_API_URL` |
| `python` not found (Windows) | Use `py -m venv venv` and `py -m uvicorn ...` |

---

## Edge cases handled

### Personalization anti-feedback-loop
- **Bootstrap phase** (first ~3 weeks or &lt;5 feedback samples): always surface top-N events by raw severity regardless of classifier score.
- **Epsilon-greedy** (10%): occasionally surface low-relevance events so the model can be corrected.

### Market mechanics
- **Corporate actions**: large overnight price gaps and yfinance split data → `corporate_action` event, not regime shift.
- **Trading calendar**: weekend/holiday reopen gaps are not flagged as anomalies.
- **Trading halts**: no ticks during market hours → `trading_halted` event; stale price is not silently shown as current.
- **Bad ticks**: sanity bounds on return, volume z-score, and spread before feeding the streaming model.

### Cold start
- **Minimum observations** (default 8) before any `ChangeEvent` is emitted for an instrument.
- **New watchlist items**: alerts respect when each symbol was added to your watchlist.

### Concurrency & ordering
- **`SELECT … FOR UPDATE`** on instrument rows during ingestion.
- **Optimistic `state_version`** column — concurrent writers get a conflict instead of a lost update.
- **Out-of-order ticks**: rejected if tick timestamp is older than last processed (separate from `is_stale`).

### Alert quality
- **Per-type cooldown** (`last_event_times` JSON on each instrument) — regime shifts and volume alerts don't clobber each other's cooldown windows.
- **Feed deduplication** — only the latest alert per symbol + type in the last 4 hours.

### Model lifecycle
- **`feature_schema_version`** on instruments — bump when feature vector shape changes to invalidate incompatible pickled state.

## Algorithm choices

| Algorithm | Why |
|-----------|-----|
| **DBSTREAM** (default) | Better than CluStream (O(M²) merges) and DenStream (DBSCAN on every predict) for repeated regime checks. |
| **STREAMKMeans** | Alternative via `REGIME_CLUSTERING_ALGO=streamkmeans`. |
| **Z-score fallback** | Reliable baseline when clustering is uncertain or data is stale. |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | Postgres URL | **Required** — no SQLite |
| `FINNHUB_API_KEY` | (empty) | Free key from [finnhub.io](https://finnhub.io/register) — enables live quotes |
| `MARKET_DATA_PROVIDER` | `auto` | `auto` (finnhub→yfinance→demo), `finnhub`, `yfinance`, or `demo` |
| `REGIME_CLUSTERING_ALGO` | `dbstream` | `dbstream`, `streamkmeans`, or `fallback` |
| `MIN_OBSERVATIONS_BEFORE_EVENTS` | `8` | Cold-start threshold |
| `EVENT_COOLDOWN_MINUTES` | `5` | Regime/outlier alert cooldown per symbol |
| `VOLUME_ANOMALY_COOLDOWN_MINUTES` | `5` | Volume alert cooldown per symbol |
| `FEED_LOOKBACK_HOURS` | `4` | How far back the alert feed looks |
| `PERSONALIZATION_BOOTSTRAP_DAYS` | `21` | Days before full personalization filtering |
| `EPSILON_GREEDY_RATE` | `0.10` | Exploration rate for low-relevance events |

## API overview

- `POST /api/auth/register` — create account
- `POST /api/auth/login` — get JWT
- `GET/POST/DELETE /api/watchlist` — manage symbols
- `GET /api/dashboard` — quotes + recent alerts (`?light=true` for quotes-only refresh)
- `POST /api/visit` — mark alerts as read
- `POST /api/feedback` — train personalization model
- `DELETE /api/feedback/{event_id}` — clear useful/not-useful selection
- `GET/POST/DELETE /api/mutes` — mute alert types per symbol

## Known limitations

- Finnhub free tier (60 calls/min); falls back to yfinance then demo if unavailable.
- US trading calendar only (NYSE holidays hardcoded).
- Corporate-action detection is heuristic — production needs a proper adjustment feed.
- Full split/dividend adjustment pipeline is stubbed; events are reclassified instead of prices being adjusted.
