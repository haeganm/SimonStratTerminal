# Simons-Inspired Trading System

A local, open-source systematic trading research platform inspired by Renaissance Technologies' workflow. This system implements a Renaissance-style research process: ingest data → generate weak signals → ensemble forecasts → risk management → walk-forward backtesting → paper trading.

## Features

- **Data Ingestion**: Free historical data from Stooq (CSV downloads)
- **Signal Generation**: Momentum, mean reversion, and regime filter signals
- **Ensemble Forecasting**: Weighted combination of signals with walk-forward optimization
- **Risk Management**: Volatility targeting, position sizing, drawdown stops
- **Backtesting**: Leakage-safe engine with transaction costs and walk-forward evaluation
- **API & CLI**: FastAPI REST API and command-line tools
- **Frontend Integration**: Compatible with `signal-compass` React frontend

## Requirements

- Python 3.11+
- pip or poetry for dependency management

## Installation

1. Clone the repository:
```bash
cd backend
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -e .
pip install -e ".[dev]"  # For development dependencies
```

4. Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
```

Edit `.env` with your settings (defaults work for most use cases).

## Quick Start

### 1. Fetch Historical Data

```bash
python -m app.cli fetch AAPL --start 2020-01-01 --end 2024-01-01
```

### 2. Run a Backtest

```bash
python -m app.cli backtest AAPL --start 2020-01-01 --end 2024-12-31
```

For walk-forward evaluation:
```bash
python -m app.cli backtest AAPL --start 2020-01-01 --end 2024-12-31 --walkforward
```

### 3. Start the API Server

```bash
python -m app.cli serve
```

The API will be available at `http://127.0.0.1:8000`. Visit `http://127.0.0.1:8000/docs` for interactive API documentation.

## Frontend Integration

This backend is designed to work with the `signal-compass` frontend.

### Running Locally (Two Terminals)

**Terminal 1 - Backend:**
```bash
cd backend
.\.venv\Scripts\Activate.ps1  # Windows (or source venv/bin/activate on Mac/Linux)
python -m app.cli serve
```
Backend runs at: http://127.0.0.1:8000

**Terminal 2 - Frontend:**
```bash
cd ../signal-compass
npm install  # First time only
npm run dev
```
Frontend runs at: http://localhost:8080 (or check terminal output for actual port)

### Configuration

**Frontend Environment:**
Create `signal-compass/.env` (or copy from `.env.example`):
```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

**Backend CORS:**
CORS is configured in `backend/.env` (or uses defaults):
```env
CORS_ORIGINS=http://localhost:5173,http://localhost:8080,http://127.0.0.1:5173,http://127.0.0.1:8080
```

### Troubleshooting

- **CORS errors:** Ensure frontend URL is in `CORS_ORIGINS` env var
- **Connection refused:** Verify backend is running on port 8000
- **Wrong base URL:** Check `VITE_API_BASE_URL` in frontend `.env`
- **Port conflicts:** Change ports in config files if needed
- **Backend offline:** Frontend will show "Cannot connect to backend" message

## API Endpoints

- `GET /health` - Health check
- `GET /history?ticker=AAPL&start=2020-01-01&end=2024-01-01` - Get historical bars
- `GET /signals?ticker=AAPL&start=2020-01-01&end=2024-01-01` - Get signal history
- `GET /forecast?ticker=AAPL` - Get latest forecast
- `GET /backtest?ticker=AAPL&start=2020-01-01&end=2024-12-31&preset=default` - Run backtest

All endpoints return JSON responses with data staleness indicators (`is_delayed`, `staleness_seconds`, `warnings`).

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   CLI/API   │────▶│  Core Engine │────▶│ Data Layer  │
└─────────────┘     └──────────────┘     └─────────────┘
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
    ┌───────────┐   ┌──────────┐   ┌─────────────┐
    │ Signals   │   │Ensemble  │   │ Backtester  │
    └───────────┘   └──────────┘   └─────────────┘
```

### Key Components

- **Data Layer**: Provider abstraction (Stooq), DuckDB caching, normalization
- **Features**: Momentum, mean reversion, volatility/regime features
- **Signals**: MomentumSignal, MeanReversionSignal, RegimeFilterSignal
- **Ensemble**: Weighted signal combination with walk-forward weight optimization
- **Portfolio**: Volatility targeting, risk constraints (leverage, drawdown stops)
- **Backtest**: Leakage-safe engine with transaction costs and metrics

## Data Sources

### Stooq (Default)

- **Type**: Historical daily OHLCV data (CSV downloads)
- **Coverage**: US stocks, ETFs (requires `.us` suffix, e.g., `AAPL.us`)
- **Rate Limits**: 1 request/second (configurable)
- **Staleness**: Data may be delayed; all responses include staleness indicators
- **Limitations**: No real-time quotes via free CSV endpoint

## Configuration

Key settings in `.env`:

- `DATA_PROVIDER`: Data source (`stooq`)
- `DUCKDB_PATH`: Database file path (`./data/trading.db`)
- `API_PORT`: API server port (`8000`)
- `TARGET_VOLATILITY`: Target daily volatility (`0.01` = 1%)
- `TRANSACTION_COST_BPS`: Fixed transaction cost (`5.0` = 5 basis points)
- `WALKFORWARD_TRAIN_YEARS`: Training window size (`1`)
- `WALKFORWARD_TEST_MONTHS`: Test window size (`3`)
- `WALKFORWARD_STEP_MONTHS`: Step size (`1`)

## Testing

Run tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=app --cov-report=html
```

## Data Limitations

- **Free Sources Only**: Uses only free data sources (Stooq CSV)
- **Rate Limits**: Respects free tier limits; aggressive caching
- **Staleness**: Data may be delayed; check `is_delayed` and `staleness_seconds` in API responses
- **Coverage**: Historical data only; no real-time quotes via free tier

## Important Disclaimers

⚠️ **THIS IS NOT FINANCIAL ADVICE** ⚠️

- This software is for research and educational purposes only
- **Paper trading only** - No live trading capabilities (unless explicitly enabled)
- Past performance does not guarantee future results
- All trading involves risk of loss
- The authors and contributors are not responsible for any financial losses
- Use at your own risk

## Development

### Project Structure

```
backend/
├── app/
│   ├── api/          # FastAPI routes and schemas
│   ├── backtest/     # Backtest engine and metrics
│   ├── core/         # Configuration and logging
│   ├── data/         # Data providers and caching
│   ├── features/     # Feature engineering
│   ├── models/       # Ensemble models
│   ├── portfolio/    # Position sizing and constraints
│   ├── signals/      # Signal generation
│   └── storage/      # Database schema and repository
├── tests/            # Test suite
└── pyproject.toml    # Dependencies and configuration
```

### Code Quality

- Type hints throughout
- Pydantic models for API schemas
- Comprehensive error handling
- Logging configured
- Leakage-safe backtesting (critical for valid results)

## Walk-Forward Backtesting

The system supports walk-forward evaluation to avoid overfitting:

- **Training Window**: Default 1 year (configurable)
- **Test Window**: Default 3 months (configurable)
- **Step Size**: Default 1 month (configurable)

Weights are optimized on training data and evaluated on out-of-sample test data. This ensures realistic performance estimates.

## Future Enhancements (Phase 2)

- Alpaca paper trading adapter (if free tier available)
- Multi-ticker watchlist mode
- Pair trading (correlation + spread z-score)
- C extensions for performance-critical features
- WebSocket support for real-time updates

## License

This project is open-source. See LICENSE file for details.

## Contributing

Contributions welcome! Please ensure:
- Code follows existing style (type hints, docstrings)
- Tests pass (`pytest`)
- No data leakage in backtests (critical)

## Support

For issues, questions, or contributions, please open an issue on GitHub.
