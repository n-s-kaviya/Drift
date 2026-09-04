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

## Quick start

### 1. Start PostgreSQL

```bash
docker compose up -d
# or use a local Postgres instance
```

Default connection: `postgresql+psycopg2://watchlist:watchlist@localhost:5432/watchlist`

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # add FINNHUB_API_KEY and DATABASE_URL
uvicorn app.main:app --reload --host 0.0.0.0 --port 8765
```

### 3. Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:43123

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
- **New watchlist items**: "since last visit" uses `max(last_visit_at, watchlist_item.added_at)` per symbol.

### Concurrency & ordering
- **`SELECT … FOR UPDATE`** on instrument rows during ingestion.
- **Optimistic `state_version`** column — concurrent writers get a conflict instead of a lost update.
- **Out-of-order ticks**: rejected if tick timestamp is older than last processed (separate from `is_stale`).

### Alert quality
- **Cooldown** (default 30 min per event type per instrument) prevents cluster-boundary chattering.

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
| `EVENT_COOLDOWN_MINUTES` | `30` | Anti-chatter window |
| `PERSONALIZATION_BOOTSTRAP_DAYS` | `21` | Days before full personalization filtering |
| `EPSILON_GREEDY_RATE` | `0.10` | Exploration rate for low-relevance events |
| `VITE_API_URL` | `http://127.0.0.1:8765` | Frontend → API |

## API overview

- `POST /api/auth/register` — create account
- `POST /api/auth/login` — get JWT
- `GET/POST/DELETE /api/watchlist` — manage symbols
- `GET /api/dashboard` — quotes + changes since last visit
- `POST /api/feedback` — train personalization model

## Known limitations

- Finnhub free tier (60 calls/min); falls back to yfinance then demo if unavailable.
- US trading calendar only (NYSE holidays hardcoded).
- Corporate-action detection is heuristic — production needs a proper adjustment feed.
- Full split/dividend adjustment pipeline is stubbed; events are reclassified instead of prices being adjusted.
