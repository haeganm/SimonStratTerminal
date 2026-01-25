"""Application configuration using pydantic-settings."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Data Provider
    data_provider: str = "stooq"
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    # Storage
    duckdb_path: str = "./data/trading.db"
    cache_dir: str = "./data/cache"

    # API
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080"

    # Backtest
    walkforward_train_years: int = 1
    walkforward_test_months: int = 3
    walkforward_step_months: int = 1
    target_volatility: float = 0.01  # Target DAILY volatility (0.01 = 1% daily)
    max_position_size: float = 1.0
    max_leverage: float = 1.0
    transaction_cost_bps: float = 5.0
    slippage_factor: float = 0.001

    # Rate Limiting
    stooq_rate_limit_seconds: float = 1.0
    alpaca_rate_limit_seconds: float = 0.2

    # Logging
    log_level: str = "INFO"
    log_file: str = "./logs/trading_system.log"
    debug_mode: bool = False  # Enable detailed debug logging for data correctness (set via DEBUG=1 env var)

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def duckdb_path_obj(self) -> Path:
        """Get DuckDB path as Path object."""
        path = Path(self.duckdb_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def cache_dir_obj(self) -> Path:
        """Get cache directory as Path object."""
        path = Path(self.cache_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def log_file_obj(self) -> Path:
        """Get log file path as Path object."""
        path = Path(self.log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
