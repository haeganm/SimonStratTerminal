"""Ticker normalization utilities for canonical ticker representation."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def canonical_ticker(ticker: str, market: str = "US") -> str:
    """
    Convert ticker to canonical form for consistent caching and lookups.
    
    Canonical form:
    - Uppercase
    - Remove or normalize market suffixes (.US, .UK, .EU)
    - For US stocks: return base ticker (e.g., "NVDA" not "NVDA.US")
    
    Args:
        ticker: Input ticker symbol (e.g., "NVDA", "nvda", "NVDA.US", "NVDA.us")
        market: Default market if not specified (default: "US")
    
    Returns:
        Canonical ticker string (e.g., "NVDA")
    
    Examples:
        >>> canonical_ticker("NVDA")
        'NVDA'
        >>> canonical_ticker("nvda")
        'NVDA'
        >>> canonical_ticker("NVDA.US")
        'NVDA'
        >>> canonical_ticker("NVDA.us")
        'NVDA'
        >>> canonical_ticker("AAPL.UK")
        'AAPL'  # Note: may want to log warning for wrong market
    """
    if not ticker or not isinstance(ticker, str):
        raise ValueError(f"Invalid ticker: {ticker}")
    
    # Normalize to uppercase and strip whitespace
    ticker_normalized = ticker.strip().upper()
    
    # Remove common market suffixes for US stocks
    # If ticker has suffix like .US, .UK, .EU, extract base
    if "." in ticker_normalized:
        parts = ticker_normalized.split(".")
        base_ticker = parts[0]
        suffix = parts[1] if len(parts) > 1 else ""
        
        # For US stocks, remove .US suffix (it's implicit)
        # For other markets, keep base but log if it might be wrong
        if suffix == "US":
            return base_ticker
        elif suffix in ("UK", "EU", "JP", "DE", "FR", "CA", "AU"):
            # Other markets - for now, return base and log warning
            logger.warning(
                f"Ticker {ticker} has non-US suffix ({suffix}). "
                f"Returning base {base_ticker}. Verify market correctness."
            )
            return base_ticker
        else:
            # Unknown suffix - return base
            return base_ticker
    
    # No suffix - return as-is (uppercase)
    return ticker_normalized


def normalize_ticker_for_provider(ticker: str, market: str = "US") -> list[str]:
    """
    Generate ticker candidates for provider lookup (preserves original normalization logic).
    
    This is used by providers like Stooq to try multiple variations.
    Returns list of candidates in order of preference.
    
    Args:
        ticker: Input ticker symbol
        market: Target market (default: "US")
    
    Returns:
        List of ticker candidates to try (e.g., ["NVDA", "NVDA.US"])
    """
    ticker_normalized = ticker.strip().upper()
    
    candidates = []
    
    # If already has suffix
    if "." in ticker_normalized:
        candidates.append(ticker_normalized)
        # Also try with .US if it has different suffix
        base = ticker_normalized.split(".")[0]
        if not ticker_normalized.endswith(".US"):
            candidates.append(f"{base}.US")
    else:
        # No suffix - try as-is first, then with .US
        candidates.append(ticker_normalized)
        if market == "US":
            candidates.append(f"{ticker_normalized}.US")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_candidates = []
    for cand in candidates:
        if cand not in seen:
            seen.add(cand)
            unique_candidates.append(cand)
    
    return unique_candidates