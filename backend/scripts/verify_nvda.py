"""Standalone script to verify NVDA data correctness against Stooq."""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from datetime import date, timedelta

import httpx
import pandas as pd
from io import StringIO

from app.data.fetcher import DataFetcher
from app.data.stooq_provider import StooqProvider
from app.data.ticker_utils import canonical_ticker


def fetch_stooq_raw(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Fetch raw data directly from Stooq API."""
    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")
    url = f"https://stooq.com/q/d/l/?s={ticker}&d1={start_str}&d2={end_str}&i=d"
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            if response.status_code != 200:
                print(f"ERROR: Stooq API returned status {response.status_code}")
                return pd.DataFrame()
            
            # Check if CSV
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                print(f"ERROR: Stooq returned HTML instead of CSV for {ticker}")
                return pd.DataFrame()
            
            # Parse CSV
            df = pd.read_csv(StringIO(response.text), parse_dates=["Date"], date_format="%Y-%m-%d")
            return df
    except Exception as e:
        print(f"ERROR fetching raw Stooq data for {ticker}: {e}")
        return pd.DataFrame()


def main():
    """Verify NVDA data correctness."""
    ticker = "NVDA"
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    print(f"Verifying NVDA data correctness...")
    print(f"Date range: {start_date} to {end_date}")
    print()
    
    # Fetch via our system
    fetcher = DataFetcher()
    print(f"Fetching via DataFetcher for {ticker}...")
    our_bars, warnings = fetcher.get_bars(ticker, start_date, end_date)
    
    if our_bars.empty:
        print("ERROR: No data returned from our DataFetcher")
        return
    
    our_canonical = canonical_ticker(ticker)
    our_last_close = our_bars.iloc[-1]["close"] if "close" in our_bars.columns else None
    our_last_date = our_bars.index.max().date() if isinstance(our_bars.index, pd.DatetimeIndex) else pd.to_datetime(our_bars.index.max()).date()
    
    print(f"✓ Our system: {len(our_bars)} bars, canonical={our_canonical}, last_date={our_last_date}, last_close=${our_last_close:.2f}")
    if warnings:
        print(f"  Warnings: {', '.join(warnings)}")
    
    # Fetch raw from Stooq (try NVDA.US)
    print(f"\nFetching raw from Stooq for NVDA.US...")
    stooq_bars = fetch_stooq_raw("NVDA.US", start_date, end_date)
    
    if stooq_bars.empty:
        print("WARNING: No raw data from Stooq (might be offline or rate-limited)")
        print()
        print("SUMMARY:")
        print(f"  Our system last close: ${our_last_close:.2f}")
        print(f"  Price range check: {'✓' if 100.0 <= our_last_close <= 500.0 else '✗'} (expected $100-$500)")
        return
    
    stooq_last_close = stooq_bars.iloc[-1]["Close"]
    stooq_last_date = stooq_bars.iloc[-1]["Date"].date()
    
    print(f"✓ Stooq raw: {len(stooq_bars)} bars, last_date={stooq_last_date}, last_close=${stooq_last_close:.2f}")
    
    # Compare
    print()
    print("COMPARISON:")
    print(f"  Last date match: {'✓' if our_last_date == stooq_last_date else '✗'} ({our_last_date} vs {stooq_last_date})")
    
    if our_last_close and stooq_last_close:
        diff = abs(our_last_close - stooq_last_close)
        diff_pct = (diff / stooq_last_close * 100) if stooq_last_close > 0 else 0
        
        print(f"  Last close match: {'✓' if diff_pct < 0.1 else '✗'} (diff=${diff:.2f}, {diff_pct:.2f}%)")
        print(f"    Our: ${our_last_close:.2f}")
        print(f"    Stooq: ${stooq_last_close:.2f}")
        print(f"    Diff: ${diff:.2f} ({diff_pct:.2f}%)")
        
        if diff_pct > 0.1:
            print()
            print("⚠ WARNING: Price mismatch > 0.1% - possible symbol mapping issue")
    
    print()
    print("PRICE SANITY CHECK:")
    print(f"  Price range: {'✓' if 1.0 <= our_last_close <= 10000.0 else '✗'} (${our_last_close:.2f}, expected $1-$10000)")
    print(f"  NVDA typical range: {'✓' if 100.0 <= our_last_close <= 500.0 else '⚠'} (${our_last_close:.2f}, typical $100-$500)")
    
    if our_last_close < 100.0 or our_last_close > 500.0:
        print("  ⚠ WARNING: Price outside typical NVDA range - possible symbol mismatch")


if __name__ == "__main__":
    main()
