"""FastAPI route handlers."""

import logging
from datetime import date, datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.api.schemas import (
    BacktestResponse,
    ForecastResponse,
    HealthResponse,
    HistoryResponse,
    SignalsResponse,
    TickerInfo,
    TickerSearchResponse,
)
from app.backtest.engine import BacktestEngine
from app.backtest.metrics import compute_metrics
from app.core.config import settings
from app.core.exceptions import BacktestError, DataProviderError
from app.core.presets import get_preset
from app.core.timeutils import compute_staleness_seconds, now_utc
from app.data.fetcher import DataFetcher
from app.data.ticker_utils import canonical_ticker
from app.features.volatility import compute_all_features
from app.models.ensemble import EnsembleModel
from app.portfolio.sizing import compute_position_size
from app.signals.base import SignalResult
from app.signals.meanreversion_signal import MeanReversionSignal
from app.signals.momentum_signal import MomentumSignal
from app.signals.regime_signal import RegimeFilterSignal

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize components (can be overridden in tests)
_data_fetcher: Optional[DataFetcher] = None
_ensemble: Optional[EnsembleModel] = None
_signals: Optional[list] = None


def get_data_fetcher() -> DataFetcher:
    """Get data fetcher instance (allows dependency injection in tests)."""
    global _data_fetcher
    if _data_fetcher is None:
        _data_fetcher = DataFetcher()
    return _data_fetcher


def get_ensemble() -> EnsembleModel:
    """Get ensemble instance."""
    global _ensemble
    if _ensemble is None:
        _ensemble = EnsembleModel()
    return _ensemble


def get_signal_instances() -> list:
    """Get signals list."""
    global _signals
    if _signals is None:
        _signals = [
            MomentumSignal(),
            MeanReversionSignal(),
            RegimeFilterSignal(),
        ]
    return _signals


def _extract_last_bar_date(bars: pd.DataFrame) -> Optional[str]:
    """Extract the latest bar date as ISO string (YYYY-MM-DD)."""
    if bars.empty:
        return None
    
    try:
        if isinstance(bars.index, pd.DatetimeIndex):
            latest_date = bars.index.max().date()
        else:
            latest_date = pd.to_datetime(bars.index.max()).date()
        return latest_date.isoformat()
    except Exception:
        return None


def _get_staleness_info(bars: pd.DataFrame, ticker: str) -> tuple[bool, Optional[int], list[str]]:
    """Get data staleness information."""
    warnings = []
    is_delayed = False
    staleness_seconds = None

    if bars.empty:
        warnings.append(f"No data available for {ticker}")
        return is_delayed, staleness_seconds, warnings

    # Get latest bar date/datetime
    as_of = now_utc()
    
    if isinstance(bars.index, pd.DatetimeIndex):
        latest_bar_dt = bars.index.max()
        # Convert to date if it's a DatetimeIndex with time component
        if isinstance(latest_bar_dt, pd.Timestamp):
            latest_bar_dt = latest_bar_dt.to_pydatetime()
        elif hasattr(latest_bar_dt, 'date'):
            latest_bar_dt = latest_bar_dt.date()
        else:
            latest_bar_dt = pd.to_datetime(latest_bar_dt).date()
    else:
        # Try to get date from index or use today as fallback
        try:
            latest_bar_dt = pd.to_datetime(bars.index.max()).date()
        except Exception:
            latest_bar_dt = date.today()

    # Compute staleness using timeutils
    staleness_seconds = compute_staleness_seconds(latest_bar_dt, as_of)

    if staleness_seconds is not None:
        # Mark as delayed if more than 1 day old
        if staleness_seconds > 86400:  # 1 day
            is_delayed = True
        
        # Add clear warning if more than 1 day old
        if staleness_seconds > 86400:  # 1 day
            days_old = staleness_seconds / 86400.0
            latest_date_str = latest_bar_dt.strftime("%Y-%m-%d") if isinstance(latest_bar_dt, date) else str(latest_bar_dt)
            warnings.append(
                f"Data is delayed: last bar is {days_old:.1f} days old (last_bar={latest_date_str}). "
                f"Provider may not have real-time data."
            )

    return is_delayed, staleness_seconds, warnings


def _normalize_bars_for_processing(bars: pd.DataFrame) -> pd.DataFrame:
    """Normalize bars DataFrame for processing (features, signals, backtest).
    
    - If 'date' missing but index is DatetimeIndex/PeriodIndex or index.name=='date', 
      reset_index into 'date' column
    - Coerce bars['date'] to datetime, sort by date, drop duplicates on date
    - Ensure required columns exist: open/high/low/close/volume
    - Returns DataFrame with 'date' as column (not index) for consistent processing
    """
    out = bars.copy()
    
    # Normalize date column
    if "date" not in out.columns:
        if isinstance(out.index, (pd.DatetimeIndex, pd.PeriodIndex)) or out.index.name == "date":
            out = out.reset_index()
            # After reset_index, the index column might have a different name
            # Find the datetime column and rename it to "date"
            date_col = None
            for col in out.columns:
                if pd.api.types.is_datetime64_any_dtype(out[col]):
                    date_col = col
                    break
            if date_col and date_col != "date":
                out = out.rename(columns={date_col: "date"})
            elif len(out.columns) > 0 and not pd.api.types.is_datetime64_any_dtype(out.columns[0]):
                # If first column is not datetime, check if index was datetime
                # The index column might be unnamed, so check all columns
                for col in out.columns:
                    if pd.api.types.is_datetime64_any_dtype(out[col]):
                        out = out.rename(columns={col: "date"})
                        break
    
    # Ensure date is datetime type and sort
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"])
        out = out.sort_values("date")
        out = out.drop_duplicates(subset=["date"], keep="last")
    
    return out


def _json_safe_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to JSON-safe records (handle NaN, timestamps, numpy types).
    
    Uses _normalize_bars_for_processing() first, then converts for JSON output.
    """
    # First normalize using shared helper
    out = _normalize_bars_for_processing(df)
    
    # Convert date to string for JSON
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    
    # Identify numeric columns
    numeric_cols = set(out.select_dtypes(include=[np.number]).columns)
    
    # Convert to records and cast numpy types to Python types, handle NaN
    records = out.to_dict(orient="records")
    for record in records:
        for key, value in record.items():
            if key in numeric_cols:
                # For numeric columns: cast numpy types and replace NaN with 0.0
                if isinstance(value, (np.integer, np.floating)):
                    record[key] = float(value) if isinstance(value, np.floating) else int(value)
                elif pd.isna(value):
                    record[key] = 0.0
                else:
                    # Ensure it's a Python float/int, not numpy
                    record[key] = float(value) if not isinstance(value, (int, float)) else value
            else:
                # For non-numeric columns: convert NaN to None
                if pd.isna(value):
                    record[key] = None
                elif isinstance(value, (np.integer, np.floating)):
                    record[key] = float(value) if isinstance(value, np.floating) else int(value)
    
    return records


@router.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    now = now_utc()
    return HealthResponse(
        status="healthy",
        data_source=settings.data_provider,
        as_of=now,
        is_delayed=False,
        staleness_seconds=None,
        warnings=[],
    )


@router.get("/tickers/search", response_model=TickerSearchResponse)
async def search_tickers(q: str = Query(..., description="Search query (ticker symbol prefix)")):
    """Search for tickers by symbol prefix (case-insensitive, offline)."""
    import csv
    from pathlib import Path
    
    try:
        # Load symbols from CSV
        symbols_path = Path(__file__).parent.parent.parent / "data" / "symbols_us.csv"
        
        if not symbols_path.exists():
            logger.warning(f"Symbols file not found at {symbols_path}")
            return TickerSearchResponse(tickers=[])
        
        # Normalize query (uppercase, strip)
        query = q.strip().upper()
        
        if not query:
            return TickerSearchResponse(tickers=[])
        
        # Read CSV and filter by prefix match (case-insensitive)
        matches = []
        with open(symbols_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = row.get("symbol", "").strip().upper()
                name = row.get("name", "").strip()
                
                if symbol.startswith(query):
                    matches.append(TickerInfo(symbol=symbol, name=name))
        
        # Limit to top 20 matches
        matches = matches[:20]
        
        logger.info(f"Ticker search: q={q} -> {len(matches)} matches")
        
        return TickerSearchResponse(tickers=matches)
    
    except Exception as e:
        logger.error(f"Error in ticker search: {e}", exc_info=True)
        # Return empty results on error (don't fail the request)
        return TickerSearchResponse(tickers=[])


@router.get("/history", response_model=HistoryResponse)
async def get_history(
    ticker: str = Query(..., description="Stock ticker symbol"),
    start: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end: str = Query(..., description="End date (YYYY-MM-DD)"),
):
    """Get historical price data."""
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        
        # Validate date range
        if start_date >= end_date:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date range: start_date ({start_date}) must be before end_date ({end_date})"
            )

        # Fetch data
        fetcher = get_data_fetcher()
        
        # Clamp future end dates
        latest_available = fetcher.get_latest_available_date(ticker)
        if latest_available and end_date > latest_available:
            warnings = [f"End date {end_date} is in the future, clamped to {latest_available}"]
            end_date = latest_available
        else:
            warnings = []
        
        bars, fetch_warnings = fetcher.get_bars(ticker, start_date, end_date)
        warnings.extend(fetch_warnings or [])
        
        # Ensure warnings is always a list
        warnings = warnings or []

        if bars.empty:
            warnings.append(f"No data found for {ticker} from {start_date} to {end_date}")
        
        # Validate minimum bars required
        if not bars.empty and len(bars) < 20:
            warnings.append(f"Insufficient data: only {len(bars)} bars available (minimum 20 recommended)")

        # Get staleness info
        is_delayed, staleness_seconds, staleness_warnings = _get_staleness_info(bars, ticker)
        warnings.extend(staleness_warnings)
        
        # Ensure staleness_seconds is explicitly set (None or int)
        if staleness_seconds is not None:
            staleness_seconds = int(staleness_seconds)

        # Convert to response format (JSON-safe)
        history_bars = []
        if not bars.empty:
            # Normalize bars and select required columns
            required_cols = ["date", "open", "high", "low", "close", "volume"]
            bars_normalized = _normalize_bars_for_processing(bars)
            
            # Select only required columns that exist
            available_cols = [col for col in required_cols if col in bars_normalized.columns]
            if available_cols:
                history_bars = _json_safe_records(bars_normalized[available_cols])

        as_of_time = now_utc()
        
        # Ensure staleness_seconds is explicitly set (None or int)
        if staleness_seconds is not None:
            staleness_seconds = int(staleness_seconds)

        # Normalize ticker to canonical form for consistent responses
        canonical = canonical_ticker(ticker)
        
        # Extract last bar date
        last_bar_date = _extract_last_bar_date(bars)
        
        return HistoryResponse(
            ticker=canonical,
            data=history_bars,
            data_source=settings.data_provider,
            as_of=as_of_time,
            is_delayed=is_delayed,
            staleness_seconds=staleness_seconds,
            last_bar_date=last_bar_date,
            warnings=warnings,
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    except DataProviderError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error in /history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/signals", response_model=SignalsResponse)
async def signals_endpoint(
    ticker: str = Query(..., description="Stock ticker symbol"),
    start: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end: str = Query(..., description="End date (YYYY-MM-DD)"),
):
    """Get signal history for a ticker."""
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        
        # Validate date range
        if start_date >= end_date:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date range: start_date ({start_date}) must be before end_date ({end_date})"
            )

        # Fetch data
        fetcher = get_data_fetcher()
        
        # Clamp future end dates
        latest_available = fetcher.get_latest_available_date(ticker)
        if latest_available and end_date > latest_available:
            warnings = [f"End date {end_date} is in the future, clamped to {latest_available}"]
            end_date = latest_available
        else:
            warnings = []
        
        bars, fetch_warnings = fetcher.get_bars(ticker, start_date, end_date)
        warnings.extend(fetch_warnings or [])
        
        # Ensure warnings is always a list
        warnings = warnings or []
        
        # Normalize ticker to canonical form for consistent responses
        canonical = canonical_ticker(ticker)

        if bars.empty:
            return SignalsResponse(
                ticker=canonical,
                signals=[],
                data_source=settings.data_provider,
                as_of=now_utc(),
                is_delayed=False,
                staleness_seconds=None,
                last_bar_date=None,
                warnings=[f"No data found for {ticker}"],
            )

        # Normalize bars for processing (ensure date is column, sorted, deduplicated)
        bars_normalized = _normalize_bars_for_processing(bars)
        
        # Set date as index for feature computation (features expect date index)
        if "date" in bars_normalized.columns:
            bars_normalized = bars_normalized.set_index("date").sort_index()

        # Try to get features from cache
        from app.data.feature_cache import get_feature_cache
        feature_cache = get_feature_cache()
        features = feature_cache.get_features(ticker, start, end, "default")
        
        if features is None:
            # Compute features
            features = compute_all_features(bars_normalized)
            # Cache features
            feature_cache.set_features(ticker, start, end, features, "default")

        if features.empty:
            return SignalsResponse(
                ticker=canonical,
                signals=[],
                data_source=settings.data_provider,
                as_of=now_utc(),
                is_delayed=False,
                staleness_seconds=None,
                last_bar_date=_extract_last_bar_date(bars),
                warnings=["Insufficient data for feature computation"],
            )

        # Generate signals for each date in range
        signal_list = []
        dates = sorted([d for d in bars_normalized.index if start_date <= d.date() <= end_date])

        for current_date in dates:
            if current_date not in features.index:
                continue

            # Generate signals for this date
            for signal in get_signal_instances():
                try:
                    result = signal.compute(bars_normalized, features, current_date)
                    signal_list.append({
                        "name": str(result.name),
                        "score": float(result.score) if not pd.isna(result.score) else 0.0,
                        "confidence": float(result.confidence) if not pd.isna(result.confidence) else 0.0,
                        "timestamp": result.timestamp.isoformat() if hasattr(result.timestamp, 'isoformat') else str(result.timestamp),
                        "description": str(result.description) if result.description else None,
                        "reason": str(result.reason) if result.reason else None,
                        "components": result.components if result.components else None,
                    })
                except Exception as e:
                    logger.warning(f"Error computing signal {signal.name} for {current_date}: {e}")
                    continue
        
        # Sort signals by timestamp DESC (newest first)
        signal_list.sort(key=lambda x: x["timestamp"], reverse=True)

        # Get staleness info
        is_delayed, staleness_seconds, staleness_warnings = _get_staleness_info(bars, ticker)
        warnings.extend(staleness_warnings)
        
        # Ensure staleness_seconds is explicitly set (None or int)
        if staleness_seconds is not None:
            staleness_seconds = int(staleness_seconds)

        # Extract last bar date
        last_bar_date = _extract_last_bar_date(bars)

        return SignalsResponse(
            ticker=canonical,
            signals=signal_list,
            data_source=settings.data_provider,
            as_of=now_utc(),
            is_delayed=is_delayed,
            staleness_seconds=staleness_seconds,
            last_bar_date=last_bar_date,
            warnings=warnings,
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    except Exception as e:
        logger.error(f"Error in /signals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/forecast", response_model=ForecastResponse)
async def get_forecast(
    ticker: str = Query(..., description="Stock ticker symbol"),
    preset: str = Query("default", description="Strategy preset"),
):
    """Get latest forecast for a ticker."""
    try:
        # Get preset configuration
        config, preset_warnings = get_preset(preset)
        warnings = preset_warnings.copy()
        
        # Get recent data (last 252 trading days ~ 1 year)
        end_date = date.today()
        start_date = date(end_date.year - 1, end_date.month, end_date.day)

        # Fetch data
        fetcher = get_data_fetcher()
        bars, fetch_warnings = fetcher.get_bars(ticker, start_date, end_date)
        
        # Ensure warnings is always a list
        warnings.extend(fetch_warnings or [])

        if bars.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {ticker}")

        # Normalize bars for processing
        bars_normalized = _normalize_bars_for_processing(bars)
        
        # Set date as index for feature computation
        if "date" in bars_normalized.columns:
            bars_normalized = bars_normalized.set_index("date").sort_index()

        # Compute features
        features = compute_all_features(bars_normalized)

        if features.empty:
            raise HTTPException(
                status_code=400,
                detail="Insufficient data for feature computation",
            )

        # Get latest date
        latest_date = bars_normalized.index.max()

        # Generate signals for latest date
        signal_results = []
        for signal in get_signal_instances():
            try:
                result = signal.compute(bars_normalized, features, latest_date)
                signal_results.append(result)
            except Exception as e:
                logger.warning(f"Error computing signal {signal.name}: {e}")
                continue

        if not signal_results:
            raise HTTPException(status_code=500, detail="Failed to generate signals")

        # Create ensemble with preset configuration
        ensemble = EnsembleModel(
            signal_weights=config.signal_weights,
            regime_weight=config.regime_weight,
            threshold=config.threshold,
        )
        
        # Get forecast from ensemble
        forecast = ensemble.combine(signal_results)

        # Compute position size suggestion
        if bars_normalized.empty or len(bars_normalized) < 20:
            suggested_position_size = None
        else:
            # Compute realized volatility (DAILY, not annualized)
            returns = bars_normalized["close"].pct_change(fill_method=None)
            realized_vol_daily = returns.rolling(20).std().iloc[-1]  # Daily volatility
            if pd.isna(realized_vol_daily) or realized_vol_daily <= 0:
                realized_vol_daily = 0.2 / (252 ** 0.5)  # Default: convert 20% annual to daily

            suggested_position_size = compute_position_size(
                forecast.direction,
                forecast.confidence,
                realized_vol_daily,  # Pass daily volatility
            )

        # Build explanation (sanitize NaN values)
        explanation = None
        if forecast.explanation:
            from app.api.schemas import ForecastExplanation

            # Sanitize top_contributors - ensure signal is string, contribution is float
            top_contributors = []
            for c in forecast.explanation.get("top_contributors", []):
                signal_name = str(c.get("signal", "")) if c.get("signal") else ""
                contrib_val = c.get("contribution", 0.0)
                if pd.isna(contrib_val):
                    contrib_val = 0.0
                else:
                    contrib_val = float(contrib_val)
                top_contributors.append({
                    "signal": signal_name,
                    "contribution": contrib_val
                })

            # Add preset info to regime_filter description
            regime_filter_text = str(forecast.explanation.get("regime_filter")) if forecast.explanation.get("regime_filter") else None
            if regime_filter_text:
                regime_filter_text = f"{regime_filter_text} [Preset: {config.name}]"
            else:
                regime_filter_text = f"[Preset: {config.name}]"
            
            explanation = ForecastExplanation(
                top_contributors=top_contributors,
                regime_filter=regime_filter_text,
            )

        # Get staleness info
        is_delayed, staleness_seconds, staleness_warnings = _get_staleness_info(bars, ticker)
        warnings.extend(staleness_warnings)
        
        # Ensure staleness_seconds is explicitly set (None or int)
        if staleness_seconds is not None:
            staleness_seconds = int(staleness_seconds)

        # Sanitize confidence and suggested_position_size (handle NaN, numpy types)
        confidence_val = forecast.confidence
        if pd.isna(confidence_val) or confidence_val is None:
            confidence_val = 0.0
        else:
            confidence_val = float(confidence_val)
        
        position_size_val = suggested_position_size
        if position_size_val is not None:
            if pd.isna(position_size_val):
                position_size_val = None
            else:
                position_size_val = float(position_size_val)
        
        # Normalize ticker to canonical form for consistent responses
        canonical = canonical_ticker(ticker)
        
        # Extract last bar date
        last_bar_date = _extract_last_bar_date(bars)
        
        return ForecastResponse(
            ticker=canonical,
            direction=str(forecast.direction),
            confidence=confidence_val,
            suggested_position_size=position_size_val,
            explanation=explanation,
            data_source=settings.data_provider,
            as_of=now_utc(),
            is_delayed=is_delayed,
            staleness_seconds=staleness_seconds,
            last_bar_date=last_bar_date,
            warnings=warnings,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in /forecast: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/backtest", response_model=BacktestResponse)
async def run_backtest(
    ticker: str = Query(..., description="Stock ticker symbol"),
    start: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end: str = Query(..., description="End date (YYYY-MM-DD)"),
    preset: str = Query("default", description="Backtest preset"),
):
    """Run backtest for a ticker."""
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        
        # Validate date range
        if start_date >= end_date:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date range: start_date ({start_date}) must be before end_date ({end_date})"
            )

        # Get preset configuration
        config, preset_warnings = get_preset(preset)
        warnings = preset_warnings.copy()
        
        # Fetch data
        fetcher = get_data_fetcher()
        
        # Clamp future end dates
        latest_available = fetcher.get_latest_available_date(ticker)
        if latest_available and end_date > latest_available:
            warnings.append(f"End date {end_date} is in the future, clamped to {latest_available}")
            end_date = latest_available
        
        bars, fetch_warnings = fetcher.get_bars(ticker, start_date, end_date)
        
        # Ensure warnings is always a list
        warnings.extend(fetch_warnings or [])
        
        # Validate minimum bars required
        if not bars.empty and len(bars) < 60:
            warnings.append(f"Insufficient data: only {len(bars)} bars available (minimum 60 recommended for backtest)")

        if bars.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {ticker} from {start} to {end}")

        # Normalize bars for processing
        bars_normalized = _normalize_bars_for_processing(bars)
        
        # Set date as index for backtest (backtest expects date index)
        if "date" in bars_normalized.columns:
            bars_normalized = bars_normalized.set_index("date").sort_index()

        # Create ensemble with preset configuration
        ensemble = EnsembleModel(
            signal_weights=config.signal_weights,
            regime_weight=config.regime_weight,
            threshold=config.threshold,
        )
        
        # Run backtest
        engine = BacktestEngine(ensemble=ensemble)
        equity_curve, trades, metrics = engine.run(bars_normalized, start_date=start_date, end_date=end_date)

        # Convert equity curve to response format
        equity_points = []
        if not equity_curve.empty:
            for _, row in equity_curve.iterrows():
                equity_points.append({
                    "date": row["date"].strftime("%Y-%m-%d") if isinstance(row["date"], date) else pd.to_datetime(row["date"]).strftime("%Y-%m-%d"),
                    "equity": float(row["equity"]),
                    "drawdown": float(row["drawdown"]),
                })

        # Convert trades to response format
        # Trade History is not returned to client (trades DataFrame is still computed internally for metrics).
        trade_list = []  # Always return empty list

        # Get staleness info
        is_delayed, staleness_seconds, staleness_warnings = _get_staleness_info(bars_normalized, ticker)
        warnings.extend(staleness_warnings)
        
        # Ensure staleness_seconds is explicitly set (None or int)
        if staleness_seconds is not None:
            staleness_seconds = int(staleness_seconds)

        from app.api.schemas import BacktestMetrics

        # Normalize ticker to canonical form for consistent responses
        canonical = canonical_ticker(ticker)
        
        # Extract last bar date (use original bars, not normalized)
        last_bar_date = _extract_last_bar_date(bars)
        
        return BacktestResponse(
            ticker=canonical,
            preset=preset,
            metrics=BacktestMetrics(
                cagr=float(metrics.cagr),
                sharpe=float(metrics.sharpe),
                max_drawdown=float(metrics.max_drawdown),
                win_rate=float(metrics.win_rate),
                turnover=float(metrics.turnover),
                exposure=float(metrics.exposure),
                total_trades=int(metrics.total_trades),
                profit_factor=float(metrics.profit_factor) if metrics.profit_factor else None,
            ),
            equity_curve=equity_points,
            trades=trade_list,
            data_source=settings.data_provider,
            as_of=now_utc(),
            is_delayed=is_delayed,
            staleness_seconds=staleness_seconds,
            last_bar_date=last_bar_date,
            warnings=warnings,
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    except BacktestError as e:
        raise HTTPException(status_code=500, detail=f"Backtest error: {str(e)}")
    except Exception as e:
        logger.error(f"Error in /backtest: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/debug/nvda")
async def debug_nvda(
    start: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end: str = Query(..., description="End date (YYYY-MM-DD)"),
):
    """Debug endpoint to inspect NVDA data correctness and normalization path."""
    try:
        import pandas as pd
        from datetime import date
        
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        ticker = "NVDA"
        
        # Get fetcher
        fetcher = get_data_fetcher()
        
        # Normalize ticker
        from app.data.ticker_utils import canonical_ticker
        canonical = canonical_ticker(ticker)
        
        # Get provider candidates
        provider = fetcher.provider
        if hasattr(provider, '_normalize_ticker'):
            candidates = provider._normalize_ticker(ticker)
        else:
            candidates = [ticker]
        
        # Fetch data
        bars, fetch_warnings = fetcher.get_bars(ticker, start_date, end_date)
        
        # Get cache status
        cache = fetcher.cache
        cached_start, cached_end = cache.get_cached_date_range(canonical, start_date, end_date)
        cache_status = "hit" if cached_start is not None or cached_end is not None else "miss"
        
        # Extract data summary
        result = {
            "requested_ticker": ticker,
            "canonical_ticker": canonical,
            "provider_candidates": candidates,
            "cache_status": cache_status,
            "cached_range": {
                "start": str(cached_start) if cached_start else None,
                "end": str(cached_end) if cached_end else None,
            },
            "bars_summary": {
                "count": len(bars),
                "date_range": {
                    "first": str(bars.index.min().date()) if not bars.empty and isinstance(bars.index, pd.DatetimeIndex) else (str(pd.to_datetime(bars.index.min()).date()) if not bars.empty else None),
                    "last": str(bars.index.max().date()) if not bars.empty and isinstance(bars.index, pd.DatetimeIndex) else (str(pd.to_datetime(bars.index.max()).date()) if not bars.empty else None),
                },
                "first_close": float(bars.iloc[0]["close"]) if not bars.empty and "close" in bars.columns else None,
                "last_close": float(bars.iloc[-1]["close"]) if not bars.empty and "close" in bars.columns else None,
            },
            "warnings": fetch_warnings or [],
        }
        
        # If bars are empty, add warning
        if bars.empty:
            result["warnings"].append("No data returned from provider")
        
        # Check if price is unusual
        if not bars.empty and "close" in bars.columns:
            last_close = bars.iloc[-1]["close"]
            if last_close < 1.0 or last_close > 10000.0:
                result["warnings"].append(
                    f"Unusual close price: ${last_close:.2f} "
                    f"(expected range: $1-$10000 for typical stocks)"
                )
        
        return result
        
    except Exception as e:
        logger.error(f"Error in /debug/nvda: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Debug error: {str(e)}")
