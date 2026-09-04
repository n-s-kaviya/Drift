from pydantic_settings import BaseSettings


# Bump when feature vector shape changes — invalidates pickled cluster state.
FEATURE_SCHEMA_VERSION = 1


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://watchlist:watchlist@localhost:5432/watchlist"
    secret_key: str = "dev-secret-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    market_poll_interval_seconds: int = 120
    feed_lookback_hours: int = 24
    stale_data_threshold_seconds: int = 300
    regime_clustering_algo: str = "dbstream"  # dbstream | streamkmeans | fallback
    dbstream_epsilon: float = 0.8
    dbstream_mu: float = 2.0
    streamkmeans_k: int = 4
    zscore_fallback_threshold: float = 2.5

    # Cold start & alert quality
    min_observations_before_events: int = 8
    event_cooldown_minutes: int = 5
    price_move_cooldown_minutes: int = 2
    price_move_threshold_pct: float = 0.25
    cooldown_magnitude_multiplier: float = 1.5

    # Personalization anti-feedback-loop
    personalization_bootstrap_days: int = 21
    bootstrap_top_n_by_magnitude: int = 5
    epsilon_greedy_rate: float = 0.10

    volume_anomaly_threshold_z: float = 2.0
    volume_anomaly_cooldown_minutes: int = 5

    # Tick validation bounds (reject garbage prints)
    max_abs_return_pct: float = 50.0
    max_volume_z: float = 20.0
    max_spread_pct: float = 30.0
    corporate_action_gap_pct: float = 35.0
    halt_no_tick_minutes: int = 60

    # Market data chain: finnhub → yfinance → demo (auto) | finnhub | yfinance | demo
    market_data_provider: str = "auto"
    finnhub_api_key: str = ""
    finnhub_retry_minutes: int = 15
    yfinance_retry_minutes: int = 60

    class Config:
        env_file = ".env"


settings = Settings()
