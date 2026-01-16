"""CLI entry point for trading system."""

import logging
from datetime import date, datetime, timezone

import click
from fastapi import FastAPI
import uvicorn

from app.backtest.engine import BacktestEngine
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.data.fetcher import DataFetcher
from app.models.ensemble import EnsembleModel

# Ensure logging is configured
setup_logging()
logger = logging.getLogger(__name__)


@click.group()
def cli():
    """Simons Trading System CLI."""
    pass


@cli.command()
@click.argument("ticker")
@click.option("--start", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end", help="End date (YYYY-MM-DD), defaults to today")
def fetch(ticker: str, start: str, end: str | None):
    """Fetch and cache historical data for a ticker."""
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end) if end else date.today()

        click.echo(f"Fetching data for {ticker} from {start_date} to {end_date}...")

        fetcher = DataFetcher()
        bars, warnings = fetcher.get_bars(ticker, start_date, end_date, use_cache=True)

        if warnings:
            for warning in warnings:
                click.echo(f"Warning: {warning}", err=True)

        if bars.empty:
            click.echo(f"Error: No data found for {ticker}")
            return

        click.echo(f"Successfully fetched {len(bars)} bars for {ticker}")
        click.echo(f"Date range: {bars.index.min().date()} to {bars.index.max().date()}")

    except ValueError as e:
        click.echo(f"Error: Invalid date format - {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        logger.exception("Error in fetch command")
        raise click.Abort()


@cli.command()
@click.argument("ticker")
@click.option("--start", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end", help="End date (YYYY-MM-DD), defaults to today")
@click.option("--walkforward", is_flag=True, help="Use walk-forward evaluation")
def backtest(ticker: str, start: str, end: str | None, walkforward: bool):
    """Run backtest for a ticker."""
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end) if end else date.today()

        click.echo(f"Running backtest for {ticker} from {start_date} to {end_date}...")

        # Fetch data
        fetcher = DataFetcher()
        bars, warnings = fetcher.get_bars(ticker, start_date, end_date)

        if warnings:
            for warning in warnings:
                click.echo(f"Warning: {warning}", err=True)

        if bars.empty:
            click.echo(f"Error: No data found for {ticker}")
            raise click.Abort()

        # Ensure date index
        if "date" in bars.columns:
            bars = bars.set_index("date")

        # Run backtest
        ensemble = EnsembleModel()
        engine = BacktestEngine(ensemble=ensemble)

        if walkforward:
            click.echo("Using walk-forward evaluation...")
            from app.backtest.walkforward import WalkForwardEvaluator

            evaluator = WalkForwardEvaluator()
            metrics_list, equity_curve, trades = evaluator.evaluate(bars, start_date, end_date)

            click.echo(f"\nWalk-forward Results:")
            click.echo(f"Number of windows: {len(metrics_list)}")

            for i, metrics in enumerate(metrics_list):
                click.echo(f"\nWindow {i+1}:")
                click.echo(f"  CAGR: {metrics.cagr:.2%}")
                click.echo(f"  Sharpe: {metrics.sharpe:.2f}")
                click.echo(f"  Max Drawdown: {metrics.max_drawdown:.2%}")
                click.echo(f"  Win Rate: {metrics.win_rate:.2%}")
                click.echo(f"  Total Trades: {metrics.total_trades}")

            # Aggregate metrics
            avg_cagr = sum(m.cagr for m in metrics_list) / len(metrics_list) if metrics_list else 0.0
            avg_sharpe = sum(m.sharpe for m in metrics_list) / len(metrics_list) if metrics_list else 0.0
            avg_max_dd = sum(m.max_drawdown for m in metrics_list) / len(metrics_list) if metrics_list else 0.0

            click.echo(f"\nAggregated Results:")
            click.echo(f"  Avg CAGR: {avg_cagr:.2%}")
            click.echo(f"  Avg Sharpe: {avg_sharpe:.2f}")
            click.echo(f"  Avg Max Drawdown: {avg_max_dd:.2%}")

        else:
            equity_curve, trades, metrics = engine.run(bars, start_date=start_date, end_date=end_date)

            click.echo(f"\nBacktest Results:")
            click.echo(f"  CAGR: {metrics.cagr:.2%}")
            click.echo(f"  Sharpe: {metrics.sharpe:.2f}")
            click.echo(f"  Max Drawdown: {metrics.max_drawdown:.2%}")
            click.echo(f"  Win Rate: {metrics.win_rate:.2%}")
            click.echo(f"  Turnover: {metrics.turnover:.2%}")
            click.echo(f"  Exposure: {metrics.exposure:.2%}")
            click.echo(f"  Total Trades: {metrics.total_trades}")
            if metrics.profit_factor:
                click.echo(f"  Profit Factor: {metrics.profit_factor:.2f}")

    except ValueError as e:
        click.echo(f"Error: Invalid date format - {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        logger.exception("Error in backtest command")
        raise click.Abort()


@cli.command()
@click.option("--host", default=None, help="Host to bind to (default from config)")
@click.option("--port", default=None, type=int, help="Port to bind to (default from config)")
def serve(host: str | None, port: int | None):
    """Start the FastAPI server."""
    host = host or settings.api_host
    port = port or settings.api_port

    click.echo(f"Starting server on {host}:{port}...")
    click.echo(f"API documentation: http://{host}:{port}/docs")

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=True,
    )


if __name__ == "__main__":
    cli()
