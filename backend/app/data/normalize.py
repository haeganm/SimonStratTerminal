"""OHLCV data normalization utilities."""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize OHLCV DataFrame to standard format.

    Args:
        df: DataFrame with date and OHLCV columns (case-insensitive matching)

    Returns:
        Normalized DataFrame with columns: date, open, high, low, close, volume
        Date set as index
    """
    df = df.copy()

    # Normalize column names (case-insensitive)
    column_mapping = {}
    for col in df.columns:
        col_lower = col.lower().strip()
        if col_lower in ["date", "time", "timestamp"]:
            column_mapping[col] = "date"
        elif col_lower in ["open", "o"]:
            column_mapping[col] = "open"
        elif col_lower in ["high", "h"]:
            column_mapping[col] = "high"
        elif col_lower in ["low", "l"]:
            column_mapping[col] = "low"
        elif col_lower in ["close", "c", "price"]:
            column_mapping[col] = "close"
        elif col_lower in ["volume", "vol", "v"]:
            column_mapping[col] = "volume"

    df = df.rename(columns=column_mapping)

    # Ensure required columns exist
    required_cols = ["date", "open", "high", "low", "close", "volume"]
    missing_cols = set(required_cols) - set(df.columns)
    if missing_cols:
        raise ValueError(f"Missing required columns after normalization: {missing_cols}")

    # Convert date to datetime if it's not already
    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # Remove rows with invalid dates
    df = df.dropna(subset=["date"])

    # Ensure numeric types for OHLCV
    numeric_cols = ["open", "high", "low", "close", "volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Remove rows with NaN in required numeric columns
    df = df.dropna(subset=numeric_cols)

    # Sort by date
    df = df.sort_values("date")

    # Set date as index
    df = df.set_index("date")

    # Ensure index is named "date" for consistency
    df.index.name = "date"

    # Reset index to get date as column for storage
    df = df.reset_index()

    # OHLCV sanity checks and validation
    warnings = []
    
    # Check for duplicate dates - drop duplicates, keep last
    initial_count = len(df)
    df = df.drop_duplicates(subset=["date"], keep="last")
    if len(df) < initial_count:
        duplicates_removed = initial_count - len(df)
        warnings.append(f"Removed {duplicates_removed} duplicate date entries (kept last)")
        logger.warning(f"Removed {duplicates_removed} duplicate dates from OHLCV data")
    
    # Sort by date ascending (ensure chronological order)
    df = df.sort_values("date").reset_index(drop=True)
    
    # OHLCV sanity checks: high >= max(open, close, low), low <= min(open, close, high)
    invalid_high = (df["high"] < df[["open", "close", "low"]].max(axis=1))
    invalid_low = (df["low"] > df[["open", "close", "high"]].min(axis=1))
    
    if invalid_high.any():
        invalid_count = invalid_high.sum()
        logger.warning(f"Found {invalid_count} rows with high < max(open, close, low) - fixing")
        # Fix: set high to max of open, close, low
        df.loc[invalid_high, "high"] = df.loc[invalid_high, ["open", "close", "low"]].max(axis=1)
        warnings.append(f"Fixed {invalid_count} rows where high < max(open, close, low)")
    
    if invalid_low.any():
        invalid_count = invalid_low.sum()
        logger.warning(f"Found {invalid_count} rows with low > min(open, close, high) - fixing")
        # Fix: set low to min of open, close, high
        df.loc[invalid_low, "low"] = df.loc[invalid_low, ["open", "close", "high"]].min(axis=1)
        warnings.append(f"Fixed {invalid_count} rows where low > min(open, close, high)")
    
    # Volume sanity check: volume >= 0
    negative_volume = df["volume"] < 0
    if negative_volume.any():
        invalid_count = negative_volume.sum()
        logger.warning(f"Found {invalid_count} rows with negative volume - setting to 0")
        df.loc[negative_volume, "volume"] = 0
        warnings.append(f"Fixed {invalid_count} rows with negative volume")
    
    # Check for large price jumps (>35% day-over-day) - potential split/adjustment issue
    if len(df) > 1:
        df_sorted = df.sort_values("date").copy()
        price_changes = df_sorted["close"].pct_change(fill_method=None).abs()
        large_jumps = price_changes > 0.35  # >35% change (may indicate split/adjustment)
        
        if large_jumps.any():
            jump_dates = df_sorted.loc[large_jumps, "date"].tolist()
            jump_pcts = (price_changes[large_jumps] * 100).tolist()
            logger.warning(
                f"Found {large_jumps.sum()} large price jumps (>35%): "
                f"{', '.join([f'{d}: {p:.1f}%' for d, p in zip(jump_dates[:5], jump_pcts[:5])])}"
            )
            warnings.append(
                f"Detected {large_jumps.sum()} large price jumps (>35% day-over-day) - "
                f"potential split/adjustment issue"
            )
    
    # Check for zero volume on trading days (may indicate data issue)
    zero_volume = df["volume"] == 0
    if zero_volume.any():
        zero_count = zero_volume.sum()
        logger.debug(f"Found {zero_count} rows with zero volume")
        # Don't warn for zero volume as it might be legitimate for some data sources
    
    # Price sanity checks: warn if prices are unusual for stocks
    if len(df) > 0:
        last_close = df["close"].iloc[-1]
        first_close = df["close"].iloc[0]
        
        # Check for unusual prices (< $1 or > $10000 for stocks)
        if last_close < 1.0 or last_close > 10000.0:
            logger.warning(
                f"Unusual close price detected: ${last_close:.2f} "
                f"(expected range: $1-$10000 for typical stocks). "
                f"This might indicate a symbol mismatch or data error."
            )
            warnings.append(
                f"Unusual close price: ${last_close:.2f} "
                f"(may indicate symbol mismatch or data error)"
            )
    
    # Log warnings if any
    if warnings:
        logger.info(f"OHLCV validation warnings: {', '.join(warnings)}")
    
    return df[required_cols]
