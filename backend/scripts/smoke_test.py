"""Smoke test script for data correctness."""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from datetime import date, timedelta

import httpx


def main():
    """Run end-to-end smoke tests: /health, /history for NVDA+AAPL, /forecast, /backtest."""
    base_url = "http://127.0.0.1:8000"
    ticker = "NVDA"
    end_date = date.today()
    start_date = end_date - timedelta(days=90)
    
    print("Running end-to-end smoke tests...")
    print()
    
    results = []
    
    # 1. Health check
    try:
        response = httpx.get(f"{base_url}/health", timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            # Verify core fields
            if data.get("status") == "healthy" and "data_source" in data:
                results.append(("✓", "Health check", f"status={data['status']}, source={data['data_source']}"))
            else:
                results.append(("✗", "Health check", "Missing core fields"))
        else:
            results.append(("✗", "Health check", f"Status {response.status_code}"))
    except Exception as e:
        results.append(("✗", "Health check", f"Error: {e}"))
    
    # 2. NVDA history
    try:
        response = httpx.get(
            f"{base_url}/history?ticker={ticker}&start={start_date}&end={end_date}",
            timeout=10.0
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("data") and len(data["data"]) > 0:
                last_close = data["data"][-1]["close"]
                last_date = data["data"][-1]["date"]
                
                # Check price range (plausible: $1-$1000)
                price_ok = 1.0 <= last_close <= 1000.0
                status = f"${last_close:.2f} ({last_date})" + (" ✓" if price_ok else " ⚠")
                results.append(("✓" if price_ok else "⚠", f"NVDA history", status))
            else:
                results.append(("✗", "NVDA history", "No data returned"))
        else:
            results.append(("✗", "NVDA history", f"Status {response.status_code}"))
    except Exception as e:
        results.append(("✗", "NVDA history", f"Error: {e}"))
    
    # 3. NVDA forecast
    try:
        response = httpx.get(f"{base_url}/forecast?ticker={ticker}", timeout=10.0)
        if response.status_code == 200:
            data = response.json()
            # Verify core fields are present
            direction = data.get("direction", "unknown")
            confidence = data.get("confidence", None)
            ticker_field = data.get("ticker", None)
            
            if direction in ["long", "flat", "short"] and confidence is not None and ticker_field:
                confidence_ok = 0.0 <= confidence <= 1.0
                status = f"direction={direction}, confidence={confidence:.2f}, ticker={ticker_field}"
                results.append(("✓" if confidence_ok else "⚠", "NVDA forecast", status))
            else:
                results.append(("✗", "NVDA forecast", f"Missing core fields: direction={direction}, confidence={confidence}"))
        else:
            results.append(("✗", "NVDA forecast", f"Status {response.status_code}"))
    except Exception as e:
        results.append(("✗", "NVDA forecast", f"Error: {e}"))
    
    # 4. NVDA backtest
    try:
        response = httpx.get(
            f"{base_url}/backtest?ticker={ticker}&start={start_date}&end={end_date}&preset=default",
            timeout=30.0
        )
        if response.status_code == 200:
            data = response.json()
            # Verify core fields are present
            if "metrics" in data and "equity_curve" in data:
                metrics = data["metrics"]
                cagr = metrics.get("cagr", 0.0)
                sharpe = metrics.get("sharpe", 0.0)
                max_dd = metrics.get("max_drawdown", 0.0)
                total_trades = metrics.get("total_trades", 0)
                # Verify trades list exists (should be empty by default)
                trades = data.get("trades", [])
                status = f"CAGR={cagr:.2%}, Sharpe={sharpe:.2f}, MaxDD={max_dd:.2%}, Trades={total_trades}, TradeHistory={len(trades)}"
                results.append(("✓", "NVDA backtest", status))
            else:
                results.append(("✗", "NVDA backtest", "Missing core fields (metrics or equity_curve)"))
        else:
            results.append(("✗", "NVDA backtest", f"Status {response.status_code}"))
    except Exception as e:
        results.append(("✗", "NVDA backtest", f"Error: {e}"))
    
    # 5. Cache isolation: NVDA vs AAPL
    try:
        nvda_response = httpx.get(
            f"{base_url}/history?ticker=NVDA&start={start_date}&end={end_date}",
            timeout=10.0
        )
        aapl_response = httpx.get(
            f"{base_url}/history?ticker=AAPL&start={start_date}&end={end_date}",
            timeout=10.0
        )
        
        if nvda_response.status_code == 200 and aapl_response.status_code == 200:
            nvda_data = nvda_response.json()
            aapl_data = aapl_response.json()
            
            if nvda_data.get("data") and aapl_data.get("data"):
                nvda_close = nvda_data["data"][-1]["close"]
                aapl_close = aapl_data["data"][-1]["close"]
                
                diff_pct = abs(nvda_close - aapl_close) / min(nvda_close, aapl_close) * 100
                isolated = diff_pct > 10.0
                status = f"NVDA=${nvda_close:.2f}, AAPL=${aapl_close:.2f} (diff={diff_pct:.1f}%)"
                results.append(("✓" if isolated else "⚠", "Cache isolation", status))
            else:
                results.append(("⚠", "Cache isolation", "Insufficient data for comparison"))
        else:
            results.append(("✗", "Cache isolation", "Failed to fetch data"))
    except Exception as e:
        results.append(("✗", "Cache isolation", f"Error: {e}"))
    
    # Print results
    print("RESULTS:")
    for status, test, detail in results:
        print(f"  {status} {test:20s} {detail}")
    
    # Summary
    passed = sum(1 for s, _, _ in results if s == "✓")
    warnings = sum(1 for s, _, _ in results if s == "⚠")
    failed = sum(1 for s, _, _ in results if s == "✗")
    
    print()
    print(f"SUMMARY: {passed} passed, {warnings} warnings, {failed} failed")
    
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
