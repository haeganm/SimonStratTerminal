"""Data access layer for DuckDB."""

import logging
from datetime import date, datetime, timezone
from typing import Optional

import duckdb
import pandas as pd

from app.core.config import settings
from app.storage.schema import SCHEMA_SQL

logger = logging.getLogger(__name__)


class DataRepository:
    """Repository for market data storage and retrieval."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize repository with DuckDB connection."""
        self.db_path = db_path or str(settings.duckdb_path_obj)
        self._initialize_schema()

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Get DuckDB connection."""
        return duckdb.connect(self.db_path)

    def _initialize_schema(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.execute(SCHEMA_SQL)
            logger.info(f"Database schema initialized at {self.db_path}")

    def store_bars(
        self, ticker: str, bars: pd.DataFrame, source: str = "stooq"
    ) -> int:
        """
        Store bars in database with deduplication.

        Args:
            ticker: Stock ticker symbol
            bars: DataFrame with columns: date, open, high, low, close, volume
            source: Data source identifier

        Returns:
            Number of rows inserted/updated
        """
        # Debug logging
        import json
        from pathlib import Path
        debug_log_path = Path(__file__).parent.parent.parent.parent / ".cursor" / "debug.log"
        try:
            log_entry = {
                "timestamp": int(datetime.now().timestamp() * 1000),
                "location": "repository.store_bars:entry",
                "message": "store_bars called",
                "data": {"ticker": ticker, "bars_rows": len(bars), "bars_empty": bars.empty, "source": source},
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "C",
            }
            with open(debug_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            pass

        if bars.empty:
            return 0

        # Ensure required columns
        required_cols = ["date", "open", "high", "low", "close", "volume"]
        missing_cols = set(required_cols) - set(bars.columns)
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        # Add metadata columns
        bars_to_store = bars[required_cols].copy()
        bars_to_store["ticker"] = ticker
        bars_to_store["source"] = source
        bars_to_store["fetched_at"] = datetime.now(timezone.utc)
        
        # Debug: log before insert
        try:
            log_entry = {
                "timestamp": int(datetime.now().timestamp() * 1000),
                "location": "repository.store_bars:before_insert",
                "message": "About to insert",
                "data": {"rows_to_insert": len(bars_to_store), "date_type": str(type(bars_to_store["date"].iloc[0])) if len(bars_to_store) > 0 else "empty"},
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "C",
            }
            with open(debug_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            pass

        with self._get_connection() as conn:
            # DuckDB: Use INSERT OR REPLACE for efficient upsert
            # Register DataFrame temporarily and use INSERT OR REPLACE
            import json
            from pathlib import Path
            debug_log_path = Path(__file__).parent.parent.parent.parent / ".cursor" / "debug.log"
            
            try:
                # Create a temporary view
                conn.register("bars_temp_df", bars_to_store)
                
                # Use INSERT OR REPLACE (DuckDB shorthand for ON CONFLICT DO UPDATE)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO bars (ticker, date, open, high, low, close, volume, source, fetched_at)
                    SELECT ticker, date, open, high, low, close, volume, source, fetched_at
                    FROM bars_temp_df
                    """
                )
                inserted = len(bars_to_store)
                logger.info(f"Stored {inserted} bars for {ticker} from {source}")
                
                # Debug log success
                try:
                    log_entry = {
                        "timestamp": int(datetime.now().timestamp() * 1000),
                        "location": "repository.store_bars:success",
                        "message": "Insert successful",
                        "data": {"inserted": inserted},
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "C",
                    }
                    with open(debug_log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(log_entry) + "\n")
                except Exception:
                    pass
                
                return inserted
            except Exception as e:
                # Debug log error
                try:
                    log_entry = {
                        "timestamp": int(datetime.now().timestamp() * 1000),
                        "location": "repository.store_bars:error",
                        "message": f"DataFrame insert failed: {str(e)}",
                        "data": {"error_type": type(e).__name__, "error_msg": str(e)},
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "C",
                    }
                    with open(debug_log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(log_entry) + "\n")
                except Exception:
                    pass
                
                logger.error(f"Error storing bars using DataFrame approach: {e}")
                # Fallback: row-by-row insert
                inserted = 0
                for idx, row in bars_to_store.iterrows():
                    try:
                        # Ensure date is proper type
                        row_date = row["date"]
                        if isinstance(row_date, pd.Timestamp):
                            row_date = row_date.date()
                        elif not isinstance(row_date, date):
                            row_date = pd.to_datetime(row_date).date()
                        
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO bars (ticker, date, open, high, low, close, volume, source, fetched_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            [
                                str(row["ticker"]),
                                row_date,
                                float(row["open"]),
                                float(row["high"]),
                                float(row["low"]),
                                float(row["close"]),
                                float(row["volume"]),
                                str(row["source"]),
                                row["fetched_at"],
                            ],
                        )
                        inserted += 1
                    except Exception as row_error:
                        logger.warning(f"Error inserting row {idx}: {row_error}")
                        # Debug log row error
                        try:
                            log_entry = {
                                "timestamp": int(datetime.now().timestamp() * 1000),
                                "location": "repository.store_bars:row_error",
                                "message": f"Row insert failed: {str(row_error)}",
                                "data": {"row_idx": str(idx), "error": str(row_error)},
                                "sessionId": "debug-session",
                                "runId": "run1",
                                "hypothesisId": "C",
                            }
                            with open(debug_log_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps(log_entry) + "\n")
                        except Exception:
                            pass
                        continue
                return inserted

    def get_bars(
        self, ticker: str, start_date: date, end_date: date
    ) -> pd.DataFrame:
        """
        Retrieve bars for a ticker and date range.

        Args:
            ticker: Stock ticker symbol
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            DataFrame with date as index and OHLCV columns
        """
        # Debug logging
        import json
        from pathlib import Path
        debug_log_path = Path(__file__).parent.parent.parent.parent / ".cursor" / "debug.log"
        try:
            log_entry = {
                "timestamp": int(datetime.now().timestamp() * 1000),
                "location": "repository.get_bars:entry",
                "message": "get_bars called",
                "data": {"ticker": ticker, "start": str(start_date), "end": str(end_date)},
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "B",
            }
            with open(debug_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            pass
        
        with self._get_connection() as conn:
            result = conn.execute(
                """
                SELECT date, open, high, low, close, volume
                FROM bars
                WHERE ticker = ? AND date >= ? AND date <= ?
                ORDER BY date
                """,
                [ticker, start_date, end_date],
            ).df()

            if result.empty:
                logger.debug(f"No bars found for {ticker} from {start_date} to {end_date}")
                empty_df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
                empty_df.index.name = "date"
                return empty_df

            # Ensure date is datetime and set as index
            if "date" in result.columns:
                result["date"] = pd.to_datetime(result["date"])
                result = result.set_index("date").sort_index()
            result.index.name = "date"

            logger.debug(f"Retrieved {len(result)} bars for {ticker}")
            
            # Debug log success
            try:
                log_entry = {
                    "timestamp": int(datetime.now().timestamp() * 1000),
                    "location": "repository.get_bars:success",
                    "message": "Query successful",
                    "data": {"rows": len(result), "index_type": str(type(result.index))},
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "B",
                }
                with open(debug_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry) + "\n")
            except Exception:
                pass
            
            return result

    def get_latest_date(self, ticker: str) -> Optional[date]:
        """Get the latest date available for a ticker."""
        with self._get_connection() as conn:
            result = conn.execute(
                "SELECT MAX(date) as latest_date FROM bars WHERE ticker = ?",
                [ticker],
            ).fetchone()

            if result and result[0]:
                return result[0]
            return None

    def validate_bars(self, ticker: str, bars: pd.DataFrame) -> list[str]:
        """
        Validate bars for anomalies (splits, missing dates, duplicates).

        Returns:
            List of warning messages
        """
        warnings = []

        if bars.empty:
            return warnings

        # A) Normalize input so 'date' exists
        bars_copy = bars.copy()
        if "date" not in bars_copy.columns:
            if isinstance(bars_copy.index, (pd.DatetimeIndex, pd.PeriodIndex)) or bars_copy.index.name == "date":
                bars_copy = bars_copy.reset_index()
                if "date" not in bars_copy.columns:
                    # Find the datetime column or use first column
                    date_col = None
                    for col in bars_copy.columns:
                        if pd.api.types.is_datetime64_any_dtype(bars_copy[col]):
                            date_col = col
                            break
                    if date_col:
                        bars_copy = bars_copy.rename(columns={date_col: "date"})
                    elif len(bars_copy.columns) > 0:
                        first_col = bars_copy.columns[0]
                        bars_copy = bars_copy.rename(columns={first_col: "date"})
        
        if "date" in bars_copy.columns:
            bars_copy["date"] = pd.to_datetime(bars_copy["date"])
            bars_copy = bars_copy.sort_values("date")
            bars_copy = bars_copy.drop_duplicates(subset=["date"], keep="last")
        else:
            # No date info available, use index-based checks
            bars_copy = bars_copy.sort_index()

        # B) Add missing-values warning
        req = ["open", "high", "low", "close", "volume"]
        missing_cols = set(req) - set(bars_copy.columns)
        if missing_cols:
            warnings.append(f"Missing required columns: {missing_cols}")
        else:
            na_counts = bars_copy[req].isna().sum()
            if int(na_counts.sum()) > 0:
                warnings.append(f"Missing values in required columns: {na_counts.to_dict()}")

        # C) Check for price jumps > 35% (possible splits) - handle NaNs safely
        if "close" in bars_copy.columns:
            close = pd.to_numeric(bars_copy["close"], errors="coerce")
            rets = close.pct_change(fill_method=None).abs().dropna()
            if not rets.empty:
                max_ret = float(rets.max())
                if max_ret > 0.35:
                    warnings.append(f"Large price jump detected: max_abs_return={max_ret:.2f}")

        # Check for missing dates (gaps > 7 days)
        if "date" in bars_copy.columns:
            date_diffs = bars_copy["date"].diff().dropna()  # pandas Timedelta series
            large_gaps = date_diffs > pd.Timedelta(days=7)  # pandas boolean Series

            if large_gaps.any():
                warnings.append(
                    f"Large gaps detected: max_gap={date_diffs.max()} (count={int(large_gaps.sum())})"
                )

        # Check for duplicates
        if "date" in bars_copy.columns:
            duplicates = bars_copy["date"].duplicated()
        else:
            duplicates = bars_copy.index.duplicated()
        if duplicates.any():
            warnings.append(
                f"Found {duplicates.sum()} duplicate dates for {ticker}"
            )

        return warnings
