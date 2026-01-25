# Systematic Trading Research Platform

A production-ready, open-source research terminal and backtester for systematic equity strategies. Features signal-based forecasting, ensemble models, and leakage-safe backtesting with walk-forward validation.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688.svg)
![React](https://img.shields.io/badge/React-18.3+-61dafb.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)
![Tests](https://img.shields.io/badge/tests-139%20passed-success)

---

## Table of Contents

- [Overview](#overview)
- [Disclaimer](#disclaimer)
- [Features](#features)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Architecture](#architecture)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

A systematic trading research platform designed for backtesting signal-based strategies on US equities. The system implements a complete research workflow: data ingestion → feature engineering → signal generation → ensemble forecasting → risk management → leakage-safe backtesting → walk-forward evaluation.

**Key Design Principles:**
- **Leakage-safe**: Backtests only use data available at each point in time
- **Production-ready**: Comprehensive test suite (139+ tests), input validation, error handling
- **Extensible**: Clean architecture with provider abstraction, signal plugins, preset system
- **Educational**: Well-documented codebase suitable for learning systematic trading concepts

**Data Source**: [Stooq](https://stooq.com/) (free, no API keys required). Provides daily end-of-day (EOD) historical data that may be delayed; no real-time quotes.

---

## ⚠️ Disclaimer

**This software is for research and educational purposes only. Not financial advice.**

Past performance does not guarantee future results. All trading involves risk of loss. The authors and contributors are not responsible for any financial losses. Use at your own risk.

Additionally, it is vital that you ensure the integrity of all math and data used - I am not perfect and this project likely includes potential mistakes or errors.
---

## Features

- 📊 **Data Ingestion & Caching**: Historical daily OHLCV data from Stooq with DuckDB caching for fast local access
- 📈 **Signal Generation**: Three signal types—momentum (trend-following), mean reversion, and regime filter (volatility/trend conditions)
- 🎯 **Strategy Presets**: Four pre-configured strategies (default, trend, mean_reversion, conservative) with tunable parameters
- 🔮 **Ensemble Forecasting**: Weighted signal combination with confidence scoring and regime-based filtering
- 🛡️ **Risk Management**: Volatility targeting, position sizing, leverage constraints, and drawdown stops
- ✅ **Leakage-Safe Backtesting**: Time-aware engine that prevents future data leakage, includes transaction costs and slippage
- 🔄 **Walk-Forward Evaluation**: Out-of-sample testing framework to avoid overfitting and validate strategy robustness
- 🌐 **REST API**: FastAPI backend with OpenAPI documentation, request logging, and comprehensive error handling
- 💻 **Web UI**: Modern React + TypeScript frontend with real-time charts, signal tables, and backtest visualization
- 🧪 **Comprehensive Testing**: 139+ tests covering logic correctness, security, edge cases, and provider failures

---

## Quick Start

### Option A: One-Command Setup (Recommended)

**Windows:**
```powershell
.\start-dev.ps1
```

**macOS/Linux:**
```bash
chmod +x start-dev.sh
./start-dev.sh
```

This automatically starts both backend (port 8000) and frontend (port 8080) servers.

**Access points:**
- 🌐 Frontend UI: http://localhost:8080
- 🔌 Backend API: http://127.0.0.1:8000
- 📚 API Docs: http://127.0.0.1:8000/docs

### Option B: Manual Setup

**Terminal 1 - Backend:**
```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -e ".[dev]"
python -m app.cli serve
```

**Terminal 2 - Frontend:**
```bash
cd signal-compass
npm install
npm run dev
```

---

## Installation

### Requirements

- **Python**: 3.11 or higher
- **Node.js**: 18 or higher (and npm)

### Backend Setup

1. Navigate to `backend/` directory
2. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -e ".[dev]"
   ```
   This installs the package in editable mode with development dependencies (pytest, black, mypy).

### Frontend Setup

1. Navigate to `signal-compass/` directory
2. Install dependencies:
   ```bash
   npm install
   ```

---

## Configuration

### Backend Configuration

1. Copy `backend/env.example` to `backend/.env`
2. Default settings work for most use cases (no changes needed)

**Key Settings:**
- `DATA_PROVIDER=stooq` - Data source (free, no API keys)
- `API_PORT=8000` - Backend server port
- `DUCKDB_PATH=./data/trading.db` - Local database path
- `TARGET_VOLATILITY=0.01` - Target daily volatility (1% = 0.01)
- `CORS_ORIGINS` - Comma-separated frontend URLs (default includes common ports)

### Frontend Configuration

1. Copy `signal-compass/.env.example` to `signal-compass/.env` (if it exists)
2. Default `VITE_API_BASE_URL=http://127.0.0.1:8000` works if backend runs on port 8000

**Note**: `.env` files are git-ignored. Never commit real credentials. Use `.env.example` files as templates.

---

## Usage

### API Examples

**PowerShell:**
```powershell
# Health check
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get

# Get forecast with default preset
Invoke-RestMethod -Uri "http://127.0.0.1:8000/forecast?ticker=AAPL&preset=default" -Method Get

# Run backtest
Invoke-RestMethod -Uri "http://127.0.0.1:8000/backtest?ticker=AAPL&start=2020-01-01&end=2024-12-31&preset=default" -Method Get
```

**cURL:**
```bash
# Health check
curl "http://127.0.0.1:8000/health"

# Get forecast with trend preset
curl "http://127.0.0.1:8000/forecast?ticker=AAPL&preset=trend"

# Get historical data
curl "http://127.0.0.1:8000/history?ticker=AAPL&start=2024-01-01&end=2024-01-10"
```

### Strategy Presets

Use the `preset` query parameter in `/forecast` and `/backtest` endpoints:

- **`default`** - Balanced approach (equal signal weights, 30% regime influence, 10% threshold)
- **`trend`** - Momentum-focused (60% momentum, 20% mean reversion, 15% threshold)
- **`mean_reversion`** - Mean reversion-focused (20% momentum, 60% mean reversion, 8% threshold)
- **`conservative`** - Lower risk (equal weights, 20% regime, 20% threshold)

**Example:**
```bash
curl "http://127.0.0.1:8000/forecast?ticker=AAPL&preset=trend"
```

### CLI Usage

**Fetch historical data:**
```bash
python -m app.cli fetch AAPL --start 2020-01-01 --end 2024-01-01
```

**Run backtest:**
```bash
python -m app.cli backtest AAPL --start 2020-01-01 --end 2024-12-31
```

**Walk-forward evaluation:**
```bash
python -m app.cli backtest AAPL --start 2020-01-01 --end 2024-12-31 --walkforward
```

---

## API Reference

All endpoints return JSON with consistent metadata:

- `as_of` - Request timestamp (UTC ISO format)
- `data_source` - Provider name (e.g., "stooq")
- `is_delayed` - Boolean indicating data staleness
- `staleness_seconds` - Seconds since last bar's market close, or `null`
- `last_bar_date` - Most recent bar date (YYYY-MM-DD)
- `warnings` - Array of warning messages (always a list)

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check and data source status |
| `GET` | `/history?ticker=AAPL&start=2020-01-01&end=2024-01-01` | Historical OHLCV bars |
| `GET` | `/signals?ticker=AAPL&start=2020-01-01&end=2024-01-01` | Signal history with scores and confidence |
| `GET` | `/forecast?ticker=AAPL&preset=default` | Latest forecast with direction, confidence, and position sizing |
| `GET` | `/backtest?ticker=AAPL&start=2020-01-01&end=2024-12-31&preset=default` | Run backtest and return metrics + equity curve |
| `GET` | `/tickers/search?q=AAPL` | Search tickers by symbol prefix (offline CSV lookup) |

Interactive API documentation available at http://127.0.0.1:8000/docs

---

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

- **Data Layer**: Provider abstraction (Stooq), DuckDB caching, data normalization, ticker canonicalization
- **Features**: Momentum (returns, MA slopes, breakouts), mean reversion (z-scores, Bollinger bands), volatility/regime (realized vol, trend strength)
- **Signals**: `MomentumSignal`, `MeanReversionSignal`, `RegimeFilterSignal` - each returns score [-1,1] and confidence [0,1]
- **Ensemble**: Weighted signal combination with regime-based filtering. Direction based on scores only; confidence used for position sizing
- **Portfolio**: Volatility targeting (daily units), position sizing, risk constraints (leverage, drawdown stops)
- **Backtest**: Leakage-safe engine with point-in-time data access, transaction costs, slippage, comprehensive metrics

### How It Works

1. **Data Flow**: Request → DataFetcher → Provider (Stooq) → Cache (DuckDB) → Normalization
2. **Feature Engineering**: Bars → Compute momentum/mean reversion/volatility features
3. **Signal Generation**: Features + Bars → Generate signals (score, confidence) for each date
4. **Ensemble Forecasting**: Signals → Weighted combination → Forecast (direction, confidence)
5. **Position Sizing**: Forecast + Volatility → Volatility-targeted position size
6. **Backtesting**: Historical Bars + Ensemble → Execute trades point-in-time → Compute metrics

---

## Data & Staleness

### Stooq Provider

- **Type**: End-of-day (EOD) historical data via CSV downloads
- **Coverage**: US stocks and ETFs
- **Ticker format**: Accepts `AAPL` or `AAPL.us` (normalized internally; `.us` suffix recommended for US stocks)
- **Update frequency**: Daily after market close (data may be delayed by 1+ days)
- **Rate limit**: 1 request/second (enforced automatically)

### Staleness Indicators

All API responses include staleness metadata:

- **`is_delayed`**: Boolean (typically `true` for EOD data)
- **`staleness_seconds`**: Seconds since last bar's market close (4:00 PM ET = 20:00 UTC), or `null` if data is current/future
- **`last_bar_date`**: Most recent bar date (YYYY-MM-DD)
- **`warnings`**: Array of data quality or availability messages

**How it works**: Daily bars are treated as closing at 20:00 UTC (4:00 PM ET). Staleness is computed as: current UTC time - (last_bar_date + 20:00 UTC).

**End date clamping**: If a requested `end` date exceeds available data, the system automatically clamps to the latest available bar. Check `last_bar_date` in responses to see the actual end date used.

---

## Testing

The project includes a comprehensive test suite with 139+ tests covering:

- ✅ **Logic Correctness**: Data leakage prevention, math correctness, signal calculations
- 🔒 **Security**: Input validation, injection attack prevention, error message sanitization
- 🧪 **Edge Cases**: Empty data, NaN handling, extreme values, missing columns
- 🔌 **Provider Failures**: Network errors, timeouts, rate limits, partial data
- 📊 **Financial Correctness**: P&L calculations, transaction costs, risk constraints
- 🔄 **Integration**: End-to-end workflows, API contracts, frontend-backend communication

**Run all tests:**
```bash
cd backend
python -m pytest -v
```

**Run critical tests only:**
```bash
python -m pytest tests/test_leakage.py tests/test_math_correctness.py tests/test_ensemble_fixes.py tests/test_critical_correctness.py -v
```

**Run with coverage:**
```bash
python -m pytest --cov=app --cov-report=html
```

Tests use mock data providers for reproducibility and run offline by default.

---

## Troubleshooting

**CORS errors**: Add frontend URL to `CORS_ORIGINS` in `backend/.env` (default includes `http://localhost:8080` and common ports)

**Connection refused**: Verify backend is running: `http://127.0.0.1:8000/health`

**Wrong `VITE_API_BASE_URL`**: Ensure `signal-compass/.env` has `VITE_API_BASE_URL=http://127.0.0.1:8000` matching backend port

**Port conflicts**: Change `API_PORT` in `backend/.env` and update `VITE_API_BASE_URL` in `signal-compass/.env`

**Ticker not found**: Try adding `.us` suffix (e.g., `AAPL.us`) for US stocks

**Missing dependencies**: Reinstall backend (`pip install -e ".[dev]"`) or frontend (`npm install`)

**Data not loading**: Check `warnings` field in API responses for data availability issues

---

## Contributing

Contributions welcome! Please ensure:

- ✅ Code follows existing style (type hints, docstrings)
- ✅ Tests pass (`pytest`)
- ✅ No data leakage in backtests (critical - see `test_leakage.py`)
- ✅ Security best practices (input validation, no secrets in code)
- ✅ Edge cases handled gracefully

**Development workflow:**
1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run full test suite: `pytest -v`
5. Submit pull request

---

## Security & Repo Hygiene

- ✅ **No secrets committed**: All configuration via `.env` files (git-ignored)
- ✅ **Free data sources only**: Uses Stooq (no paid APIs or API keys required)
- ✅ **`.gitignore` configured**: Excludes build artifacts, local DBs, logs, `.env` files
- ✅ **Template files**: `.env.example` files provided for setup
- ✅ **Input validation**: API endpoints validate and sanitize all inputs
- ✅ **Comprehensive testing**: Security tests included in test suite

### Pre-Push Checklist

**Windows (PowerShell):**
```powershell
git status
git ls-files | Select-String -Pattern "(\.env$|\.db$|\.sqlite$|egg-info/)"
cd backend && python -m pytest -q
```

**macOS/Linux:**
```bash
git status
git ls-files | grep -E "(\.env$|\.db$|\.sqlite$|egg-info/)"
cd backend && python -m pytest -q
```

Should return empty results for tracked artifacts check.

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

## Acknowledgments

Inspired by systematic quantitative research workflows. Built for educational and research purposes.
