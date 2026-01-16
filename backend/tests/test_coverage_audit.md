# Test Coverage Audit

## Top 10 Critical Tests Status

### 1. Data Normalization Correctness
**Status**: PARTIAL
- **Existing**: `test_normalize_ohlcv()` in `test_providers.py`
- **Gaps**: 
  - Missing: sorted ascending check
  - Missing: unique dates check
  - Missing: correct dtypes validation
  - Missing: required fields non-null check
- **Action**: Strengthen existing test

### 2. Cache Correctness + Zero Redundant Provider Calls
**Status**: MISSING
- **Existing**: None
- **Gaps**: Complete test missing
- **Action**: Add `test_cache_no_redundant_calls()` with SpyProvider

### 3. Corporate-Action/Anomaly Sanity Warnings
**Status**: MISSING
- **Existing**: None
- **Gaps**: Complete test missing
- **Action**: Add `test_anomaly_warnings_propagate()` with synthetic split

### 4. Leakage Test (Most Important)
**Status**: WEAK
- **Existing**: `test_backtest_no_future_data_access()` in `test_leakage.py`
- **Gaps**: 
  - Not strict enough (doesn't verify max_timestamp_used <= t)
  - No instrumentation of features/signals
- **Action**: Add strict leakage test with instrumentation

### 5. Walk-Forward Boundary Correctness
**Status**: MISSING
- **Existing**: None
- **Gaps**: Complete test missing
- **Action**: Add `test_walkforward_boundaries()` with strict date checks

### 6. Cost/Slippage Correctness
**Status**: MISSING
- **Existing**: None
- **Gaps**: Complete test missing
- **Action**: Add `test_costs_applied_correctly()` with deterministic fixture

### 7. Risk Constraints Correctness
**Status**: MISSING
- **Existing**: None
- **Gaps**: Complete test missing
- **Action**: Add tests for max position, leverage, drawdown, daily loss

### 8. Backtest Reproducibility
**Status**: MISSING
- **Existing**: None
- **Gaps**: Complete test missing
- **Action**: Add `test_backtest_reproducibility()` with same config

### 9. API Contract & Schema Correctness
**Status**: MISSING
- **Existing**: None
- **Gaps**: Complete test missing
- **Action**: Add API tests with TestClient

### 10. End-to-End Smoke Test (Offline)
**Status**: MISSING
- **Existing**: None
- **Gaps**: Complete test missing
- **Action**: Add `test_e2e_offline()` with FakeProvider
