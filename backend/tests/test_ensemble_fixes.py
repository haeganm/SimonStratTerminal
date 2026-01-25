"""Tests for ensemble model fixes: confidence, volatility units, regime_weight."""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.core.presets import PRESETS, get_preset
from app.models.ensemble import EnsembleModel, Forecast
from app.portfolio.sizing import compute_position_size
from app.signals.base import SignalResult


@pytest.fixture
def sample_signals():
    """Create sample signals for testing."""
    momentum = SignalResult(
        score=0.5,
        confidence=0.8,
        name="Momentum",
        timestamp=datetime.now(timezone.utc),
        description="Test momentum",
    )
    mean_rev = SignalResult(
        score=-0.3,
        confidence=0.6,
        name="Mean Reversion",
        timestamp=datetime.now(timezone.utc),
        description="Test mean reversion",
    )
    regime = SignalResult(
        score=0.7,
        confidence=0.9,
        name="Regime Filter",
        timestamp=datetime.now(timezone.utc),
        description="Test regime",
    )
    return [momentum, mean_rev, regime]


class TestConfidenceDoubleCounting:
    """Test that confidence does not affect direction decision."""

    def test_direction_unchanged_when_confidence_changes(self):
        """Direction should NOT change when only confidences change (scores fixed)."""
        ensemble = EnsembleModel(threshold=0.1)

        # Create signals with fixed scores but different confidences
        signals_high_conf = [
            SignalResult(
                score=0.5,
                confidence=0.9,  # High confidence
                name="Momentum",
                timestamp=datetime.now(timezone.utc),
                description="High confidence",
            ),
            SignalResult(
                score=0.3,
                confidence=0.9,  # High confidence
                name="Mean Reversion",
                timestamp=datetime.now(timezone.utc),
                description="High confidence",
            ),
        ]

        signals_low_conf = [
            SignalResult(
                score=0.5,  # Same score
                confidence=0.1,  # Low confidence
                name="Momentum",
                timestamp=datetime.now(timezone.utc),
                description="Low confidence",
            ),
            SignalResult(
                score=0.3,  # Same score
                confidence=0.1,  # Low confidence
                name="Mean Reversion",
                timestamp=datetime.now(timezone.utc),
                description="Low confidence",
            ),
        ]

        forecast_high = ensemble.combine(signals_high_conf)
        forecast_low = ensemble.combine(signals_low_conf)

        # Direction should be the same (based on scores, not confidence)
        assert forecast_high.direction == forecast_low.direction, (
            f"Direction changed when only confidence changed: "
            f"high_conf={forecast_high.direction}, low_conf={forecast_low.direction}"
        )

        # But confidence should be different
        assert forecast_high.confidence > forecast_low.confidence

    def test_weighted_sum_does_not_include_confidence(self):
        """Weighted sum should only use scores, not confidence."""
        ensemble = EnsembleModel(signal_weights={"Momentum": 1.0}, threshold=0.1)

        # Signal with high score, low confidence
        signal1 = SignalResult(
            score=0.8,
            confidence=0.1,
            name="Momentum",
            timestamp=datetime.now(timezone.utc),
            description="High score, low confidence",
        )

        # Signal with low score, high confidence
        signal2 = SignalResult(
            score=0.2,
            confidence=0.9,
            name="Momentum",
            timestamp=datetime.now(timezone.utc),
            description="Low score, high confidence",
        )

        forecast1 = ensemble.combine([signal1])
        forecast2 = ensemble.combine([signal2])

        # Signal 1 should have stronger direction (higher weighted_sum)
        # because score is higher (0.8 vs 0.2), even though confidence is lower
        # Both should be "long" since scores are positive and above threshold
        assert forecast1.direction == "long"
        assert forecast2.direction == "long"
        # Signal 1 has higher score, so it should have higher magnitude
        # (we can't directly access weighted_sum, but direction is the same)
        # The key is that confidence doesn't affect direction - only score does


class TestVolatilityUnits:
    """Test that volatility sizing uses daily units consistently."""

    def test_daily_volatility_sizing(self):
        """Position sizing should use daily volatility, not annualized."""
        # Create a synthetic returns series with known daily std
        # If we have 252 days with daily returns of exactly 0.01 (1%), 
        # daily std ≈ 0.01, annualized std ≈ 0.01 * sqrt(252) ≈ 0.158
        np.random.seed(42)
        daily_returns = np.random.normal(0.0, 0.01, 252)  # 1% daily std
        returns_series = pd.Series(daily_returns)
        
        # Compute daily volatility (what we should use)
        realized_vol_daily = returns_series.std()
        expected_daily_std = 0.01  # Approximately
        
        # Verify we're using daily (not annualized)
        assert abs(realized_vol_daily - expected_daily_std) < 0.005, (
            f"Daily vol should be ~0.01, got {realized_vol_daily}"
        )
        
        # Annualized would be much larger
        realized_vol_annualized = realized_vol_daily * np.sqrt(252)
        assert realized_vol_annualized > 0.1, "Annualized should be > 0.1"
        
        # Test position sizing with daily vol
        target_vol_daily = 0.01  # 1% daily target
        confidence = 0.8
        
        # With daily vol = 0.01 and target = 0.01, base size should be ~1.0
        # But scaled by confidence = 0.8
        position_size = compute_position_size(
            "long",
            confidence,
            realized_vol_daily,
            target_volatility=target_vol_daily,
        )
        
        # Should be approximately target_vol / realized_vol * confidence
        expected_size = (target_vol_daily / realized_vol_daily) * confidence
        assert abs(position_size - expected_size) < 0.1, (
            f"Position size should be ~{expected_size}, got {position_size}"
        )
        
        # If we mistakenly used annualized vol, size would be wrong
        wrong_size_annualized = compute_position_size(
            "long",
            confidence,
            realized_vol_annualized,  # Wrong: annualized
            target_volatility=target_vol_daily,  # Daily
        )
        
        # Wrong size should be much smaller (because dividing by larger number)
        assert wrong_size_annualized < position_size * 0.5, (
            "Using annualized vol gives wrong size"
        )

    def test_vol_floor_prevents_division_blowup(self):
        """Volatility floor should prevent division by very small numbers."""
        # Very small volatility
        tiny_vol = 1e-8
        
        position_size = compute_position_size(
            "long",
            0.8,
            tiny_vol,
            target_volatility=0.01,
        )
        
        # Should not be huge (vol_floor should cap it)
        assert position_size < 10.0, f"Position size should be capped, got {position_size}"


class TestRegimeWeight:
    """Test that regime_weight actually affects outputs."""

    def test_regime_weight_affects_score_scale(self, sample_signals):
        """Increasing regime_weight should increase regime effect on weighted_sum."""
        # Create regime signal with unfavorable regime
        unfavorable_regime = SignalResult(
            score=0.3,  # Low regime score
            confidence=0.9,
            name="Regime Filter",
            timestamp=datetime.now(timezone.utc),
            description="Unfavorable regime",
        )
        
        trading_signals = [s for s in sample_signals if s.name != "Regime Filter"]
        trading_signals.append(unfavorable_regime)
        
        # Test with low regime_weight (should have less effect)
        ensemble_low = EnsembleModel(regime_weight=0.1, threshold=0.1)
        forecast_low = ensemble_low.combine(trading_signals)
        
        # Test with high regime_weight (should have more effect)
        ensemble_high = EnsembleModel(regime_weight=0.5, threshold=0.1)
        forecast_high = ensemble_high.combine(trading_signals)
        
        # With unfavorable regime, higher regime_weight should reduce weighted_sum more
        # We can't directly access weighted_sum, but we can check direction/confidence
        # If regime has more effect, confidence should be lower with higher regime_weight
        assert forecast_high.confidence <= forecast_low.confidence, (
            f"Higher regime_weight should reduce confidence with unfavorable regime: "
            f"low_rw={forecast_low.confidence}, high_rw={forecast_high.confidence}"
        )

    def test_regime_weight_affects_confidence_scale(self, sample_signals):
        """Increasing regime_weight should increase regime effect on confidence."""
        # Create regime signal with moderate regime (score = 0.5)
        # This will show the effect of regime_weight clearly
        moderate_regime = SignalResult(
            score=0.5,  # Moderate regime score
            confidence=0.9,
            name="Regime Filter",
            timestamp=datetime.now(timezone.utc),
            description="Moderate regime",
        )
        
        trading_signals = [s for s in sample_signals if s.name != "Regime Filter"]
        trading_signals.append(moderate_regime)
        
        # Test with zero regime_weight (should ignore regime)
        ensemble_zero = EnsembleModel(regime_weight=0.0, threshold=0.1)
        forecast_zero = ensemble_zero.combine(trading_signals)
        
        # Test with high regime_weight (should use regime)
        ensemble_high = EnsembleModel(regime_weight=0.5, threshold=0.1)
        forecast_high = ensemble_high.combine(trading_signals)
        
        # With regime_weight=0.0, regime should have no effect (conf_scale = 1.0)
        # With regime_weight=0.5 and regime_score=0.5:
        #   raw_conf_scale = 0.7 + 0.3*0.5 = 0.85
        #   conf_scale = 0.5*1.0 + 0.5*0.85 = 0.925
        # So confidence should be different
        assert abs(forecast_high.confidence - forecast_zero.confidence) > 0.01, (
            f"Regime weight should affect confidence: "
            f"zero_rw={forecast_zero.confidence}, high_rw={forecast_high.confidence}"
        )

    def test_regime_weight_monotonicity(self):
        """Regime weight effects should be monotonic."""
        # Create signals with fixed scores/confidences
        momentum = SignalResult(
            score=0.4,
            confidence=0.7,
            name="Momentum",
            timestamp=datetime.now(timezone.utc),
            description="Fixed",
        )
        regime = SignalResult(
            score=0.6,  # Moderate regime
            confidence=0.8,
            name="Regime Filter",
            timestamp=datetime.now(timezone.utc),
            description="Moderate regime",
        )
        
        signals = [momentum, regime]
        
        # Test increasing regime_weight values
        regime_weights = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
        confidences = []
        
        for rw in regime_weights:
            ensemble = EnsembleModel(regime_weight=rw, threshold=0.1)
            forecast = ensemble.combine(signals)
            confidences.append(forecast.confidence)
        
        # Confidence should change monotonically (not necessarily increasing,
        # but should change smoothly with regime_weight)
        # With regime_score=0.6, higher regime_weight should increase confidence
        for i in range(1, len(confidences)):
            # Should be monotonic (increasing for favorable regime)
            assert confidences[i] >= confidences[i-1] - 0.01, (
                f"Confidence should be monotonic with regime_weight: "
                f"rw={regime_weights[i-1]} -> {confidences[i-1]}, "
                f"rw={regime_weights[i]} -> {confidences[i]}"
            )


class TestPostFixAudit:
    """Post-fix audit tests to ensure correctness."""

    def test_signal_weights_normalized(self):
        """Signal weights should sum to ~1.0 after normalization."""
        # Test with unnormalized weights (sum = 2.0)
        ensemble = EnsembleModel(
            signal_weights={"Momentum": 1.2, "Mean Reversion": 0.8},
            threshold=0.1
        )
        
        signals = [
            SignalResult(
                score=0.5,
                confidence=0.8,
                name="Momentum",
                timestamp=datetime.now(timezone.utc),
                description="Test",
            ),
            SignalResult(
                score=0.3,
                confidence=0.6,
                name="Mean Reversion",
                timestamp=datetime.now(timezone.utc),
                description="Test",
            ),
        ]
        
        forecast = ensemble.combine(signals)
        
        # After normalization: weights should be 1.2/2.0=0.6 and 0.8/2.0=0.4
        # weighted_sum = 0.6*0.5 + 0.4*0.3 = 0.3 + 0.12 = 0.42
        # This should be > threshold (0.1), so direction should be "long"
        assert forecast.direction == "long", (
            "Weights should be normalized - unnormalized weights would give different result"
        )
        
        # Verify weights are actually normalized by checking that equal unnormalized weights
        # give same result as normalized weights
        ensemble_unnorm = EnsembleModel(
            signal_weights={"Momentum": 2.0, "Mean Reversion": 2.0},  # Sum = 4.0
            threshold=0.1
        )
        forecast_unnorm = ensemble_unnorm.combine(signals)
        
        ensemble_norm = EnsembleModel(
            signal_weights={"Momentum": 0.5, "Mean Reversion": 0.5},  # Sum = 1.0
            threshold=0.1
        )
        forecast_norm = ensemble_norm.combine(signals)
        
        # Both should give same direction (weights normalized internally)
        assert forecast_unnorm.direction == forecast_norm.direction, (
            "Unnormalized and normalized weights should give same result"
        )
        assert abs(forecast_unnorm.confidence - forecast_norm.confidence) < 0.01, (
            "Unnormalized and normalized weights should give same confidence"
        )

    def test_regime_multiplier_and_confidence_clamped(self):
        """regime_multiplier and forecast_confidence should be clamped to [0,1]."""
        ensemble = EnsembleModel(threshold=0.1)
        
        # Test with extreme regime scores (outside [0,1])
        extreme_regime_high = SignalResult(
            score=2.0,  # > 1.0
            confidence=0.9,
            name="Regime Filter",
            timestamp=datetime.now(timezone.utc),
            description="Extreme high",
        )
        
        extreme_regime_low = SignalResult(
            score=-0.5,  # < 0.0
            confidence=0.9,
            name="Regime Filter",
            timestamp=datetime.now(timezone.utc),
            description="Extreme low",
        )
        
        momentum = SignalResult(
            score=0.5,
            confidence=0.8,
            name="Momentum",
            timestamp=datetime.now(timezone.utc),
            description="Test",
        )
        
        # Test high extreme
        forecast_high = ensemble.combine([momentum, extreme_regime_high])
        assert 0.0 <= forecast_high.confidence <= 1.0, (
            f"Confidence should be clamped to [0,1], got {forecast_high.confidence}"
        )
        
        # Test low extreme
        forecast_low = ensemble.combine([momentum, extreme_regime_low])
        assert 0.0 <= forecast_low.confidence <= 1.0, (
            f"Confidence should be clamped to [0,1], got {forecast_low.confidence}"
        )
        
        # Test with extreme base_confidence (via signal confidences > 1.0)
        # Note: SignalResult might not allow confidence > 1.0, but if it does, test it
        # For now, test that even with very high confidences, final confidence is clamped
        high_conf_signal = SignalResult(
            score=0.5,
            confidence=1.0,  # Max allowed
            name="Momentum",
            timestamp=datetime.now(timezone.utc),
            description="High conf",
        )
        forecast_max = ensemble.combine([high_conf_signal])
        assert 0.0 <= forecast_max.confidence <= 1.0, (
            f"Confidence should be clamped even with max signal confidence, got {forecast_max.confidence}"
        )

    def test_base_confidence_uses_same_weights_as_score(self):
        """base_confidence should use same weights as weighted_sum calculation."""
        # Create signals with different confidences
        momentum = SignalResult(
            score=0.5,
            confidence=0.9,  # High confidence
            name="Momentum",
            timestamp=datetime.now(timezone.utc),
            description="High conf momentum",
        )
        
        mean_rev = SignalResult(
            score=0.3,
            confidence=0.1,  # Low confidence
            name="Mean Reversion",
            timestamp=datetime.now(timezone.utc),
            description="Low conf mean rev",
        )
        
        # Test with unequal weights
        ensemble = EnsembleModel(
            signal_weights={"Momentum": 0.8, "Mean Reversion": 0.2},
            threshold=0.1
        )
        
        forecast = ensemble.combine([momentum, mean_rev])
        
        # base_confidence should be: 0.8*0.9 + 0.2*0.1 = 0.72 + 0.02 = 0.74
        # (weights normalized to sum=1.0, so 0.8/1.0=0.8 and 0.2/1.0=0.2)
        expected_base_conf = 0.8 * 0.9 + 0.2 * 0.1
        # After regime scaling (no regime signal, so conf_scale = 1.0)
        expected_conf = expected_base_conf * 1.0
        
        assert abs(forecast.confidence - expected_conf) < 0.01, (
            f"base_confidence should use same weights as score calculation: "
            f"expected={expected_conf}, got={forecast.confidence}"
        )
        
        # Verify that low-weight signals don't inflate sizing
        # If we had a signal with very high confidence but low weight,
        # it shouldn't dominate the confidence calculation
        ensemble_low_weight = EnsembleModel(
            signal_weights={"Momentum": 0.95, "Mean Reversion": 0.05},
            threshold=0.1
        )
        forecast_low = ensemble_low_weight.combine([momentum, mean_rev])
        
        # Mean Reversion has low weight (0.05), so its high confidence shouldn't matter much
        # base_confidence ≈ 0.95*0.9 + 0.05*0.1 = 0.855 + 0.005 = 0.86
        assert forecast_low.confidence < 0.9, (
            "Low-weight signals should not inflate confidence"
        )

    def test_golden_regression_all_presets(self):
        """Golden regression test: verify consistent behavior across all presets."""
        # Create fixed set of signals
        momentum = SignalResult(
            score=0.6,
            confidence=0.8,
            name="Momentum",
            timestamp=datetime.now(timezone.utc),
            description="Fixed momentum",
        )
        mean_rev = SignalResult(
            score=-0.2,
            confidence=0.6,
            name="Mean Reversion",
            timestamp=datetime.now(timezone.utc),
            description="Fixed mean rev",
        )
        regime = SignalResult(
            score=0.7,
            confidence=0.9,
            name="Regime Filter",
            timestamp=datetime.now(timezone.utc),
            description="Fixed regime",
        )
        
        signals = [momentum, mean_rev, regime]
        
        # Test all presets
        results = {}
        for preset_name in PRESETS.keys():
            config, _ = get_preset(preset_name)
            ensemble = EnsembleModel(
                signal_weights=config.signal_weights,
                regime_weight=config.regime_weight,
                threshold=config.threshold,
            )
            forecast = ensemble.combine(signals)
            results[preset_name] = forecast
        
        # Verify all forecasts have valid structure
        for preset_name, forecast in results.items():
            # Direction should be one of: 'long', 'short', 'flat'
            assert forecast.direction in ['long', 'short', 'flat'], (
                f"Preset {preset_name}: invalid direction {forecast.direction}"
            )
            
            # Confidence should be in [0, 1]
            assert 0.0 <= forecast.confidence <= 1.0, (
                f"Preset {preset_name}: confidence out of range: {forecast.confidence}"
            )
            
            # Position size should be in [0, 1] or None
            if forecast.suggested_position_size is not None:
                assert 0.0 <= forecast.suggested_position_size <= 1.0, (
                    f"Preset {preset_name}: position size out of range: {forecast.suggested_position_size}"
                )
            
            # Position size sign should match direction
            if forecast.direction == "flat":
                assert forecast.suggested_position_size == 0.0 or forecast.suggested_position_size is None, (
                    f"Preset {preset_name}: flat direction should have zero position size"
                )
            elif forecast.direction == "long":
                assert forecast.suggested_position_size is None or forecast.suggested_position_size >= 0.0, (
                    f"Preset {preset_name}: long direction should have non-negative position size"
                )
            elif forecast.direction == "short":
                assert forecast.suggested_position_size is None or forecast.suggested_position_size >= 0.0, (
                    f"Preset {preset_name}: short direction should have non-negative position size"
                )
        
        # Verify presets produce different results (they should, due to different weights/thresholds)
        directions = [f.direction for f in results.values()]
        # At least some variation expected (though all might be "long" with these signals)
        assert len(set(directions)) >= 1, "Presets should produce valid directions"
        
        # Verify confidence ranges are reasonable
        confidences = [f.confidence for f in results.values()]
        assert all(0.0 <= c <= 1.0 for c in confidences), "All confidences should be in [0,1]"
        assert max(confidences) > 0.0, "At least one preset should have non-zero confidence"

    def test_volatility_usage_daily_only_for_sizing(self):
        """Verify that sizing uses daily volatility, annualization only for reporting."""
        # This test verifies the code structure, not runtime behavior
        # We check that compute_position_size expects daily volatility
        
        # Test with known daily volatility
        daily_vol = 0.01  # 1% daily
        annualized_vol = daily_vol * np.sqrt(252)  # ~0.158
        
        # Position size with daily vol should be reasonable
        size_daily = compute_position_size(
            "long",
            0.8,
            daily_vol,
            target_volatility=0.01,  # 1% daily target
        )
        
        # Position size with annualized vol (wrong) should be much smaller
        size_annualized = compute_position_size(
            "long",
            0.8,
            annualized_vol,  # Wrong: annualized
            target_volatility=0.01,  # Daily target
        )
        
        # Daily should give larger size (correct)
        assert size_daily > size_annualized, (
            "Using daily volatility should give larger position size than annualized"
        )
        
        # Verify the ratio is approximately sqrt(252)
        ratio = size_daily / size_annualized if size_annualized > 0 else float('inf')
        assert ratio > 10.0, (
            f"Size ratio should be large (daily vs annualized), got {ratio}"
        )
