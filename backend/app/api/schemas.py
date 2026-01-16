"""Pydantic schemas matching frontend TypeScript types."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    data_source: str
    as_of: Optional[datetime] = None
    is_delayed: bool = False
    staleness_seconds: Optional[int] = None
    warnings: list[str] = Field(default_factory=list)


class HistoryBar(BaseModel):
    """Single OHLCV bar."""

    date: str  # ISO date string (YYYY-MM-DD)
    open: float
    high: float
    low: float
    close: float
    volume: float


class HistoryResponse(BaseModel):
    """Historical bars response."""

    ticker: str
    data: list[HistoryBar]
    data_source: str
    as_of: datetime
    is_delayed: bool = False
    staleness_seconds: Optional[int] = None
    warnings: list[str] = Field(default_factory=list)


class Signal(BaseModel):
    """Signal result."""

    name: str
    score: float = Field(ge=-1.0, le=1.0)  # -1 to 1
    confidence: float = Field(ge=0.0, le=1.0)  # 0 to 1
    timestamp: str  # ISO datetime string
    description: Optional[str] = None
    reason: Optional[str] = None  # Specific reason with numeric values
    components: Optional[dict[str, float]] = None  # Numeric components used


class SignalsResponse(BaseModel):
    """Signals response."""

    ticker: str
    signals: list[Signal]
    data_source: str
    as_of: datetime
    is_delayed: bool = False
    staleness_seconds: Optional[int] = None
    warnings: list[str] = Field(default_factory=list)


class ForecastExplanation(BaseModel):
    """Forecast explanation."""

    top_contributors: list[dict] = Field(default_factory=list)  # Each dict has "signal" (str) and "contribution" (float)
    regime_filter: Optional[str] = None


class ForecastResponse(BaseModel):
    """Forecast response."""

    ticker: str
    direction: str = Field(pattern="^(long|flat|short)$")
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_position_size: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    explanation: Optional[ForecastExplanation] = None
    data_source: str
    as_of: datetime
    is_delayed: bool = False
    staleness_seconds: Optional[int] = None
    warnings: list[str] = Field(default_factory=list)


class BacktestMetrics(BaseModel):
    """Backtest metrics."""

    cagr: float
    sharpe: float
    max_drawdown: float  # Negative value
    win_rate: float = Field(ge=0.0, le=1.0)
    turnover: float = Field(ge=0.0, le=1.0)
    exposure: float = Field(ge=0.0, le=1.0)
    total_trades: int
    profit_factor: Optional[float] = None


class EquityPoint(BaseModel):
    """Equity curve point."""

    date: str  # ISO date string
    equity: float
    drawdown: float


class Trade(BaseModel):
    """Trade record."""

    date: str  # ISO date string
    action: str = Field(pattern="^(buy|sell|hold)$")
    quantity: float
    price: float
    pnl: float
    position_after: float


class BacktestResponse(BaseModel):
    """Backtest response."""

    ticker: str
    preset: str
    metrics: BacktestMetrics
    equity_curve: list[EquityPoint]
    trades: list[Trade]
    data_source: str
    as_of: datetime
    is_delayed: bool = False
    staleness_seconds: Optional[int] = None
    warnings: list[str] = Field(default_factory=list)


class TickerInfo(BaseModel):
    """Ticker information for search results."""

    symbol: str
    name: str


class TickerSearchResponse(BaseModel):
    """Ticker search response."""

    tickers: list[TickerInfo]


class ApiError(BaseModel):
    """API error response."""

    detail: str
    status: int
