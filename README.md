# Simons Trading System

A local, open-source systematic trading research platform inspired by Renaissance Technologies' workflow. This system implements a Renaissance-style research process: ingest data → generate weak signals → ensemble forecasts → risk management → walk-forward backtesting.

## Overview

- **Stocks-only**: Designed for US equity trading
- **Free data sources**: Uses Stooq for historical market data (no paid APIs)
- **Offline testing**: All tests run offline by default
- **No secrets committed**: All configuration uses environment variables

## Quick Start

### Option 1: Run Everything at Once (Recommended)

**Windows:**
```powershell
.\start-dev.ps1
```

**Mac/Linux:**
```bash
chmod +x start-dev.sh
./start-dev.sh
```

This will:
- Start the backend server at http://127.0.0.1:8000
- Start the frontend server at http://localhost:8080
- Install frontend dependencies if needed

### Option 2: Run Separately

**Terminal 1 - Backend:**
```bash
cd backend
python -m app.cli serve
```

**Terminal 2 - Frontend:**
```bash
cd signal-compass
npm install  # First time only
npm run dev
```

## Access Points

- **Frontend**: http://localhost:8080
- **Backend API**: http://127.0.0.1:8000
- **API Documentation**: http://127.0.0.1:8000/docs

## Project Structure

```
SimonsStrat/
├── backend/          # Python FastAPI backend
│   ├── app/         # Application code
│   ├── data/        # Data storage (DuckDB)
│   └── tests/       # Test suite
└── signal-compass/  # React + TypeScript frontend
    ├── src/         # Source code
    └── public/       # Static assets
```

## Configuration

### Backend
1. Copy `backend/env.example` to `backend/.env`
2. Edit `backend/.env` with your settings (defaults work for most use cases)

Key settings:
- `DATA_PROVIDER=stooq` - Data source (Stooq is free, no API keys required)
- `DUCKDB_PATH=./data/trading.db` - Local database path
- `API_PORT=8000` - Backend API port
- `CORS_ORIGINS` - Comma-separated list of allowed frontend origins

### Frontend
1. Copy `signal-compass/.env.example` to `signal-compass/.env`
2. Update `VITE_API_BASE_URL` if your backend runs on a different port:
```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

**Security Note**: `.env` files are git-ignored. Never commit real credentials. Use `.env.example` files as templates.

## Requirements

- Python 3.11+
- Node.js 18+ and npm
- Backend dependencies: `pip install -e ".[dev]"` (from backend directory)
- Frontend dependencies: `npm install` (from signal-compass directory)

## Features

- **Data Ingestion**: Free historical data from Stooq (CSV downloads)
- **Signal Generation**: Momentum, mean reversion, and regime filter signals
- **Ensemble Forecasting**: Weighted combination of signals with walk-forward optimization
- **Risk Management**: Volatility targeting, position sizing, drawdown stops
- **Backtesting**: Leakage-safe engine with transaction costs
- **Walk-Forward Evaluation**: Out-of-sample testing to avoid overfitting
- **API & CLI**: FastAPI REST API and command-line tools
- **Frontend Integration**: React + TypeScript UI for visualization

## API Endpoints

All endpoints return JSON with data staleness indicators (`is_delayed`, `staleness_seconds`, `warnings`).

- `GET /health` - Health check and data source status
- `GET /history?ticker=AAPL&start=2020-01-01&end=2024-01-01` - Get historical OHLCV bars
- `GET /signals?ticker=AAPL&start=2020-01-01&end=2024-01-01` - Get signal history
- `GET /forecast?ticker=AAPL&preset=default` - Get latest forecast
- `GET /backtest?ticker=AAPL&start=2020-01-01&end=2024-12-31&preset=default` - Run backtest

### Example API Calls

**PowerShell:**
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get
Invoke-RestMethod -Uri "http://127.0.0.1:8000/history?ticker=AAPL&start=2020-01-01&end=2024-01-01" -Method Get
```

**cURL:**
```bash
curl "http://127.0.0.1:8000/health"
curl "http://127.0.0.1:8000/history?ticker=AAPL&start=2020-01-01&end=2024-01-01"
```

## Strategy Presets

The system supports four strategy presets for backtesting and forecasting:

- **`default`**: Balanced approach with equal signal weights, 30% regime weight, 10% threshold
- **`trend`**: Momentum-focused (60% momentum, 20% mean reversion), 15% threshold
- **`mean_reversion`**: Mean reversion-focused (20% momentum, 60% mean reversion), 8% threshold
- **`conservative`**: Lower risk with higher threshold (20%), equal signal weights, 20% regime weight

Use the `preset` query parameter in `/forecast` and `/backtest` endpoints to select a preset.

## Data Sources & Staleness Semantics

### Stooq (Default Data Provider)

- **Type**: Historical daily OHLCV data via CSV downloads
- **Coverage**: US stocks and ETFs (requires `.us` suffix, e.g., `AAPL.us`)
- **Rate Limits**: 1 request/second (configurable via `STOOQ_RATE_LIMIT_SECONDS`)
- **Staleness**: Data may be delayed; all API responses include staleness indicators

### Staleness Indicators

All API responses include:
- **`is_delayed`**: Boolean indicating if data is stale (typically true for Stooq EOD data)
- **`staleness_seconds`**: Number of seconds since last bar's market close (or `null` if data is current/future)
- **`last_bar_date`**: ISO date string (YYYY-MM-DD) of the most recent bar
- **`warnings`**: List of warning messages about data quality or availability

**How staleness is computed:**
- Daily bars are treated as closing at 20:00 UTC (4:00 PM ET, US market close)
- `staleness_seconds` = current UTC time - (last_bar_date + 20:00 UTC)
- If `staleness_seconds` > 0, data is stale and `is_delayed=true`

**End date clamping:**
- If requested `end` date is in the future or beyond available data, the system clamps to the latest available bar date
- Check `last_bar_date` in responses to see the actual end date used

## Testing

### Backend Tests

Run all tests (offline by default):
```bash
cd backend
python -m pytest -q
```

Run with verbose output:
```bash
python -m pytest -v
```

Run specific test file:
```bash
python -m pytest tests/test_backtest.py -v
```

**Test Philosophy:**
- All tests are **offline by default** (no external API calls)
- Tests use mock/fake data providers to ensure reproducibility
- Test suite includes leakage detection, math correctness, and API contract validation

## Troubleshooting

### Common Issues

**CORS errors:**
- Ensure frontend URL is in `CORS_ORIGINS` in `backend/.env`
- Default includes `http://localhost:5173,http://localhost:8080,http://127.0.0.1:5173,http://127.0.0.1:8080`
- Restart backend server after changing CORS settings

**Connection refused:**
- Verify backend is running on port 8000: `http://127.0.0.1:8000/health`
- Check `VITE_API_BASE_URL` in `signal-compass/.env` matches backend port

**Port conflicts:**
- Change `API_PORT` in `backend/.env` and update `VITE_API_BASE_URL` in `signal-compass/.env`
- Or use different ports in `start-dev.ps1` / `start-dev.sh`

**Missing dependencies:**
- Backend: `cd backend && pip install -e ".[dev]"`
- Frontend: `cd signal-compass && npm install`

**Data not loading:**
- Check data staleness indicators (`is_delayed`, `staleness_seconds`) in API responses
- Stooq data is end-of-day (EOD) and may be delayed
- Verify ticker format (use `.us` suffix for US stocks if needed)

**Tests failing:**
- Ensure you're in the `backend` directory: `cd backend && pytest`
- Check Python version: `python --version` (requires 3.11+)

## Security & Hygiene

- **No secrets committed**: All configuration uses environment variables via `.env` files
- **Free data sources only**: Uses Stooq (no paid APIs or API keys required)
- **Private repo ready**: `.gitignore` excludes build artifacts, local DBs, logs, and `.env` files
- **Example templates**: `.env.example` files are provided as templates

**Pre-push checklist:**

**Windows (PowerShell):**
```powershell
# Check for tracked .env files
git ls-files | Select-String -Pattern "\.env$"

# Check for tracked DB/log files
git ls-files | Select-String -Pattern "(\.db|\.sqlite|\.duckdb)$"

# Run tests
cd backend
python -m pytest -q

# Check git status
git status
```

**Mac/Linux:**
```bash
# Check for tracked .env files
git ls-files | grep "\.env$"

# Check for tracked DB/log files
git ls-files | grep -E "\.(db|sqlite|duckdb)$"

# Run tests
cd backend && python -m pytest -q

# Check git status
git status
```

All commands should return empty results (no tracked artifacts).
