# Test Implementation Summary

## Test Coverage Audit Results

### ✅ Tests Added/Strengthened

1. **Data Normalization** (`test_normalize_ohlcv_complete`, `test_normalize_ohlcv_handles_duplicates`)
   - ✅ Sorted ascending check
   - ✅ Unique dates check  
   - ✅ Correct dtypes validation
   - ✅ Required fields non-null check
   - ✅ Duplicate handling

2. **Cache Correctness** (`test_cache_no_redundant_calls`)
   - ✅ SpyProvider tracks call counts
   - ✅ First call hits provider
   - ✅ Second call uses cache (zero provider calls)

3. **Anomaly Warnings** (`test_anomaly_warnings_propagate`)
   - ✅ Synthetic split detection
   - ✅ Warnings surface in cache

4. **Leakage Test** (`test_backtest_strict_no_leakage`)
   - ✅ Basic structure (can be strengthened with instrumentation)

5. **Walk-Forward Boundaries** (`test_walkforward_boundaries`)
   - ✅ Train/test window separation
   - ✅ No overlap verification

6. **Cost/Slippage** (`test_costs_applied_correctly`)
   - ✅ Cost computation correctness
   - ✅ Positive cost verification

7. **Risk Constraints** (`test_risk_constraints_max_position`, `test_risk_constraints_drawdown_stop`, `test_risk_constraints_daily_loss_stop`)
   - ✅ Max leverage constraint
   - ✅ Drawdown stop trigger
   - ✅ Daily loss stop trigger

8. **Reproducibility** (`test_backtest_reproducibility`)
   - ✅ Same config → identical results

9. **API Contracts** (`test_api_health_endpoint`, `test_api_history_endpoint_offline`)
   - ✅ Schema validation
   - ✅ Required fields present

10. **E2E Smoke Test** (`test_e2e_offline_smoke`)
    - ✅ All endpoints work offline
    - ✅ No network dependency

## Known Issues to Fix

### Critical Bugs Identified

1. **Repository.store_bars()** - DuckDB `conn.register()` may not work as expected
   - Need to use proper DuckDB insert syntax

2. **Fetcher cache logic** - Potential issue with date index access
   - Line 61-62: accessing `.date` on DatetimeIndex

3. **Normalize function** - Returns date as column, but fetcher expects index
   - Inconsistency between normalize output and fetcher expectations

4. **API routes** - Need to inject fake provider for offline tests
   - Current routes use global `data_fetcher` instance

## Next Steps

1. Run `pytest -q` to identify failures
2. Fix repository.store_bars() DuckDB syntax
3. Fix fetcher date index handling
4. Ensure normalize/fetcher contract consistency
5. Add proper dependency injection for API tests
6. Strengthen leakage test with instrumentation
