"""Strategy preset configurations."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class StrategyConfig:
    """Strategy configuration for ensemble model."""

    signal_weights: dict[str, float]
    regime_weight: float
    threshold: float
    name: str


# Preset configurations
PRESETS: dict[str, StrategyConfig] = {
    "default": StrategyConfig(
        signal_weights={},  # Empty dict means equal weights (handled by EnsembleModel)
        regime_weight=0.3,
        threshold=0.1,
        name="default",
    ),
    "trend": StrategyConfig(
        signal_weights={
            "Momentum": 0.6,
            "Mean Reversion": 0.2,
        },
        regime_weight=0.2,
        threshold=0.15,
        name="trend",
    ),
    "mean_reversion": StrategyConfig(
        signal_weights={
            "Momentum": 0.2,
            "Mean Reversion": 0.6,
        },
        regime_weight=0.2,
        threshold=0.08,
        name="mean_reversion",
    ),
    "conservative": StrategyConfig(
        signal_weights={},  # Equal weights
        regime_weight=0.2,
        threshold=0.2,  # Higher threshold = more conservative
        name="conservative",
    ),
}


def get_preset(name: Optional[str]) -> tuple[StrategyConfig, list[str]]:
    """
    Get preset configuration by name.

    Args:
        name: Preset name (None or unknown names fall back to default)

    Returns:
        Tuple of (StrategyConfig, warnings_list)
        Warnings list contains a message if preset was unknown and default was used.
    """
    warnings = []

    if name is None or name not in PRESETS:
        if name is not None:
            warnings.append(f"Unknown preset '{name}', using 'default'")
        return PRESETS["default"], warnings

    return PRESETS[name], warnings
