"""Time utilities for consistent UTC handling and staleness computation."""

from datetime import date, datetime, time, timezone


def now_utc() -> datetime:
    """
    Get current UTC datetime.

    Returns:
        Current datetime in UTC timezone
    """
    return datetime.now(timezone.utc)


def compute_staleness_seconds(last_bar_dt: datetime | date, as_of: datetime) -> int | None:
    """
    Compute staleness in seconds between last bar and reference time.

    For daily bars, last_bar_dt (if date) is treated as market close (20:00 UTC)
    for consistency. This assumes US market close at 4:00 PM ET = 20:00 UTC.

    Args:
        last_bar_dt: Last bar timestamp (datetime) or date
        as_of: Reference timestamp (typically now_utc())

    Returns:
        Staleness in seconds (positive integer) if last_bar_dt < as_of, else None
    """
    # Convert date to datetime at market close (20:00 UTC)
    if isinstance(last_bar_dt, date):
        # Treat date as market close: 20:00 UTC (4:00 PM ET)
        last_bar_dt = datetime.combine(last_bar_dt, time(20, 0, 0), tzinfo=timezone.utc)
    elif isinstance(last_bar_dt, datetime):
        # Ensure timezone-aware
        if last_bar_dt.tzinfo is None:
            # Assume UTC if naive
            last_bar_dt = last_bar_dt.replace(tzinfo=timezone.utc)
    else:
        # Invalid type
        return None

    # Compute delta
    delta = as_of - last_bar_dt

    # Return seconds if positive (stale), else None (future data)
    if delta.total_seconds() > 0:
        return int(delta.total_seconds())
    return None
