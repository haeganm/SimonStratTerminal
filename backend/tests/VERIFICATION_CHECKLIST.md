# Manual QA Verification Checklist

This checklist should be used for manual verification of correctness and reliability fixes.

## 1. NVDA Price Accuracy

- [ ] Fetch NVDA data via `/history?ticker=NVDA&start=...&end=...`
- [ ] Compare last close price with external source (Yahoo Finance, etc.)
- [ ] Verify price matches within 1% tolerance
- [ ] If price doesn't match, check warnings for "unusual close price" or "symbol mismatch"
- [ ] Verify no silent wrong values (should have warnings if data is incorrect)

## 2. Cache Isolation (NVDA vs AAPL)

- [ ] Fetch NVDA data: `/history?ticker=NVDA&start=...&end=...`
- [ ] Fetch AAPL data: `/history?ticker=AAPL&start=...&end=...`
- [ ] Verify last close prices differ significantly (>10% difference)
- [ ] If prices are identical or very close, this indicates cache collision bug
- [ ] Check that both responses have different `ticker` fields (canonical form)

## 3. Signal Sorting (Newest First)

- [ ] Fetch signals: `/signals?ticker=NVDA&start=...&end=...`
- [ ] Verify signals are sorted by timestamp DESC (newest first)
- [ ] Check that most recent signal appears at the top of the list
- [ ] Verify signal timestamps are in descending order

## 4. Forecast Correctness

- [ ] Fetch forecast: `/forecast?ticker=NVDA`
- [ ] Verify `direction` is one of: "long", "flat", "short"
- [ ] Verify `confidence` is between 0.0 and 1.0
- [ ] Verify `suggested_position_size` is between 0.0 and 1.0 (if present)
- [ ] Verify `ticker` field matches requested ticker (canonical form)
- [ ] Verify `as_of` timestamp is recent
- [ ] Check that forecast uses same latest bar as displayed in history endpoint

## 5. Backtest Metrics Reasonableness

- [ ] Run backtest: `/backtest?ticker=NVDA&start=...&end=...&preset=default`
- [ ] Verify `metrics.cagr` is a reasonable percentage (typically -50% to +100%)
- [ ] Verify `metrics.sharpe` is a reasonable value (typically -2 to +5)
- [ ] Verify `metrics.max_drawdown` is negative (e.g., -0.15 for 15% drawdown)
- [ ] Verify `metrics.win_rate` is between 0.0 and 1.0
- [ ] Verify `metrics.total_trades` is a non-negative integer
- [ ] Verify `equity_curve` has data points
- [ ] Verify equity curve shows reasonable progression (not flat or erratic)

## 6. Trade History Status

- [ ] Run backtest: `/backtest?ticker=NVDA&start=...&end=...&preset=default`
- [ ] Verify `trades` field exists in response
- [ ] Verify `trades` is an empty list `[]` by default (Trade History removed)
- [ ] If Trade History is enabled, verify:
  - [ ] P&L values are not all zeros
  - [ ] Trade prices match chart prices for same dates
  - [ ] P&L calculations are correct (positive for profitable trades)

## 7. Staleness Warnings

- [ ] Fetch data for a ticker: `/history?ticker=NVDA&start=...&end=...`
- [ ] If data is >1 day old, verify:
  - [ ] `is_delayed` flag is `true`
  - [ ] `staleness_seconds` is a positive integer
  - [ ] Warnings contain message: "Data is delayed: last bar is X days old"
- [ ] Verify warning message is clear and explains provider limitation
- [ ] Verify no false "real-time" claims when data is actually delayed

## 8. Signal Labels Clarity

- [ ] Fetch signals: `/signals?ticker=NVDA&start=...&end=...`
- [ ] Verify signal names are clear:
  - [ ] "Trend (recent price strength)" for momentum signal
  - [ ] "Pullback vs average" for mean reversion signal
  - [ ] "Market regime (trend/vol filter)" for regime filter signal
- [ ] Verify labels are not vague (e.g., not just "Momentum" or "Mean Reversion")

## 9. Date Range Handling

- [ ] Request future end date: `/history?ticker=NVDA&start=2024-01-01&end=2025-12-31`
- [ ] Verify end date is clamped to latest available bar
- [ ] Verify warning message: "End date YYYY-MM-DD is in the future, clamped to YYYY-MM-DD"
- [ ] Verify returned data ends at latest available date, not future date

## 10. OHLCV Integrity

- [ ] Fetch history: `/history?ticker=NVDA&start=...&end=...`
- [ ] Verify dates are sorted ascending (oldest to newest)
- [ ] Verify no duplicate dates in response
- [ ] Verify `high >= max(open, close, low)` for all bars
- [ ] Verify `low <= min(open, close, high)` for all bars
- [ ] Verify `volume >= 0` for all bars
- [ ] Check warnings for large price jumps (>35%) that might indicate split/adjustment issues

## Running Automated Tests

Before manual QA, run automated tests:

```bash
cd backend
python -m pytest tests/ -v
```

Key test files:
- `test_nvda_repro.py`: Deterministic repro for NVDA vs AAPL
- `test_data_correctness_integration.py`: Cache isolation, ticker normalization
- `test_math_correctness.py`: Volatility, CAGR, Sharpe calculations
- `test_nvda_data_verification.py`: NVDA-specific tests

## Running Smoke Test

```bash
cd backend
python scripts/smoke_test.py
```

This will test:
- `/health` endpoint
- `/history` for NVDA and AAPL (verifies prices differ)
- `/forecast` for NVDA (verifies core fields)
- `/backtest` for NVDA (verifies metrics present)
