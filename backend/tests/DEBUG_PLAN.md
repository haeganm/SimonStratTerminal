# Debug & Hardening Plan

## Test Coverage Audit - Top 10 Critical Tests

### Status Summary

| # | Test | Status | File | Notes |
|---|------|--------|------|-------|
| 1 | Data Normalization Correctness | ✅ ADDED | `test_critical_correctness.py` | `test_normalize_ohlcv_complete`, `test_normalize_ohlcv_handles_duplicates` |
| 2 | Cache Correctness + Zero Redundant Calls | ✅ ADDED | `test_critical_correctness.py` | `test_cache_no_redundant_calls` with SpyProvider |
| 3 | Corporate-Action/Anomaly Warnings | ✅ ADDED | `test_critical_correctness.py` | `test_anomaly_warnings_propagate` |
| 4 | Leakage Test (Strict) | ⚠️ WEAK | `test_critical_correctness.py` | `test_backtest_strict_no_leakage` - needs instrumentation |
| 5 | Walk-Forward Boundary Correctness | ✅ ADDED | `test_critical_correctness.py` | `test_walkforward_boundaries` |
| 6 | Cost/Slippage Correctness | ✅ ADDED | `test_critical_correctness.py` | `test_costs_applied_correctly` |
| 7 | Risk Constraints Correctness | ✅ ADDED | `test_critical_correctness.py` | 3 tests for max position, drawdown, daily loss |
| 8 | Backtest Reproducibility | ✅ ADDED | `test_critical_correctness.py` | `test_backtest_reproducibility` |
| 9 | API Contract & Schema Correctness | ✅ ADDED | `test_critical_correctness.py` | `test_api_health_endpoint`, `test_api_history_endpoint_offline` |
| 10 | E2E Smoke Test (Offline) | ✅ ADDED | `test_critical_correctness.py` | `test_e2e_offline_smoke` |

## Code Fixes Applied

### 1. Repository.store_bars() - DuckDB Insert Fix
**Issue**: `conn.register()` may not work correctly with DuckDB
**Fix**: Changed to use `INSERT ... ON CONFLICT DO UPDATE` syntax
**File**: `app/storage/repository.py`

### 2. Fetcher Date Index Handling
**Issue**: Potential failure when accessing `.date` on DatetimeIndex
**Fix**: Added type checking and fallback
**File**: `app/data/fetcher.py`

### 3. Fetcher Cache Date Range Check
**Issue**: Assumes DatetimeIndex without checking
**Fix**: Added type checking
**File**: `app/data/fetcher.py`

## Test Infrastructure Added

### Fixtures (`conftest.py`)
- `fake_provider`: Offline provider for testing
- `sample_bars_deterministic`: Reproducible test data
- `sample_bars_with_split`: Test data with synthetic split

### SpyProvider
- Tracks call counts for cache testing
- Returns deterministic fake data

## Next Steps

1. **Install Dependencies**:
   ```bash
   cd backend
   pip install -e ".[dev]"
   ```

2. **Run Tests**:
   ```bash
   pytest -q
   ```

3. **Run with Repetition** (if flaky):
   ```bash
   pytest -q --count=5
   ```

4. **Fix Failures** based on test output

5. **Strengthen Leakage Test** with instrumentation if needed

## Known Potential Issues

1. **DuckDB ON CONFLICT syntax** - May need adjustment based on DuckDB version
2. **API dependency injection** - Routes use global `data_fetcher`, may need refactoring for tests
3. **Leakage test instrumentation** - Current test is basic, may need deeper instrumentation

## Test Execution Order

1. Run all tests: `pytest -q`
2. Identify failures
3. Fix code based on failures
4. Re-run tests
5. Iterate until all pass deterministically
