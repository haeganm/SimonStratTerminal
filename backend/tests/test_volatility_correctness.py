"""Tests for volatility calculation correctness."""

import numpy as np
import pandas as pd
import pytest

from app.features.volatility import realized_vol_20d


def test_volatility_math_synthetic():
    """Test volatility calculation with synthetic data."""
    # Generate synthetic price series with known volatility
    # Use random walk with known std to create target volatility
    
    # Target annualized volatility: 20% (0.20)
    target_annual_vol = 0.20
    target_daily_vol = target_annual_vol / np.sqrt(252)  # ~0.0126
    
    # Generate returns with target daily volatility
    np.random.seed(42)  # For reproducibility
    n_days = 252  # 1 year
    daily_returns = np.random.normal(0, target_daily_vol, n_days)
    
    # Generate price series (starting at 100)
    prices = [100.0]
    for ret in daily_returns:
        prices.append(prices[-1] * (1 + ret))
    
    close_series = pd.Series(prices[1:], name="close")
    
    # Compute volatility
    vol_series = realized_vol_20d(close_series)
    
    # Get the last volatility value (after enough data points for rolling window)
    if len(vol_series.dropna()) > 0:
        computed_vol = vol_series.dropna().iloc[-1]
        
        # Allow some tolerance due to sampling variation
        # For 20-day rolling window, expect some variance around target
        # Tolerance: within 5% of target (0.19 to 0.21)
        tolerance = 0.05
        
        assert abs(computed_vol - target_annual_vol) < (target_annual_vol * tolerance), \
            f"Computed vol {computed_vol:.4f} should be close to target {target_annual_vol:.4f}"
        
        # Verify it's not absurdly small (like 0.01% = 0.0001)
        assert computed_vol > 0.01, \
            f"Computed vol {computed_vol:.4f} should be realistic (>1%), not 0.01%"


def test_volatility_formatting():
    """Test that volatility values are in correct format (not percentage)."""
    # Volatility should be decimal (0.20 = 20%), not percentage (20.0 = 2000%)
    
    # Create simple price series
    prices = [100.0, 101.0, 102.0, 101.5, 102.5, 103.0, 102.0, 101.0, 102.0, 103.0]
    close_series = pd.Series(prices * 5, name="close")  # Repeat to get enough data
    
    # Compute volatility
    vol_series = realized_vol_20d(close_series)
    
    # Get non-null values
    vol_values = vol_series.dropna()
    
    if len(vol_values) > 0:
        # Verify values are in decimal format (0.0 to 1.0 range for reasonable volatilities)
        # Most stocks have vol between 0.10 (10%) and 1.0 (100%)
        for vol in vol_values:
            assert 0.0 <= vol <= 2.0, \
                f"Volatility {vol:.4f} should be in decimal format (0-2.0), not percentage format"
            
            # For realistic stock volatility, should be < 1.0 (100% annualized)
            # But allow up to 2.0 for high-volatility stocks
            # Just ensure it's not > 10 (which would indicate percentage formatting issue)


def test_volatility_calculation_steps():
    """Test that volatility calculation uses correct formula."""
    # Verify: returns = close.pct_change()
    # vol = returns.rolling(20).std() * sqrt(252)
    
    # Simple test series
    prices = [100.0, 101.0, 102.0, 101.0, 102.0]
    close_series = pd.Series(prices * 10, name="close")  # Repeat for rolling window
    
    # Manual calculation
    returns = close_series.pct_change(fill_method=None)
    rolling_std = returns.rolling(window=20).std()
    expected_vol = rolling_std * np.sqrt(252)
    
    # Function calculation
    computed_vol = realized_vol_20d(close_series)
    
    # Compare
    # Get last non-null values
    if len(expected_vol.dropna()) > 0 and len(computed_vol.dropna()) > 0:
        expected_last = expected_vol.dropna().iloc[-1]
        computed_last = computed_vol.dropna().iloc[-1]
        
        # Should match exactly (same calculation)
        assert abs(expected_last - computed_last) < 1e-10, \
            f"Manual calculation {expected_last:.6f} should match function {computed_last:.6f}"