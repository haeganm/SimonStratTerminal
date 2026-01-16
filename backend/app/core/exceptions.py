"""Custom exceptions for the trading system."""


class TradingSystemError(Exception):
    """Base exception for trading system errors."""

    pass


class DataProviderError(TradingSystemError):
    """Error from data provider."""

    pass


class CacheError(TradingSystemError):
    """Error in data cache operations."""

    pass


class BacktestError(TradingSystemError):
    """Error during backtesting."""

    pass


class SignalError(TradingSystemError):
    """Error in signal computation."""

    pass
