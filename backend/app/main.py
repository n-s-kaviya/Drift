from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import SessionLocal, init_db
from app.models import WatchlistItem
from app.routers import auth, dashboard, mutes, symbols, watchlist
from app.schemas import HealthOut
from app.services.pipeline import pipeline


def _poll_market_data() -> None:
    db = SessionLocal()
    try:
        symbols = [row.symbol for row in db.query(WatchlistItem.symbol).distinct().all()]
        if symbols:
            pipeline.process_symbols(db, symbols)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        pipeline.load_persisted_models(db)
    finally:
        db.close()

    scheduler = BackgroundScheduler()
    scheduler.add_job(_poll_market_data, "interval", seconds=settings.market_poll_interval_seconds)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Smart Market Watchlist",
    description="Streaming regime detection + personalized change alerts",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(watchlist.router)
app.include_router(symbols.router)
app.include_router(dashboard.router)
app.include_router(mutes.router)


@app.get("/api/health", response_model=HealthOut)
def health():
    return HealthOut(
        status="ok",
        symbols_tracked=len(pipeline.regime.tracked_symbols()),
        clustering_algo=settings.regime_clustering_algo,
        market_data_provider=settings.market_data_provider,
        market_data_active=pipeline.market.active_provider(),
    )
