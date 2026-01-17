# Systematic Trading Research Platform

A local, open-source research terminal and backtester for systematic equity strategies with signals, forecasting, and walk-forward validation.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688.svg)
![React](https://img.shields.io/badge/React-18.3+-61dafb.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)

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
- [Data & Staleness](#data--staleness)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Security & Repo Hygiene](#security--repo-hygiene)
- [License](#license)

---

## Overview

A systematic trading research terminal built for backtesting signal-based strategies on US equities. The platform combines data ingestion, feature engineering, signal generation, ensemble forecasting, and leakage-safe backtesting with walk-forward evaluation.

**Inspired by**: Systematic quantitative research workflows (educational/research use only).

**Data Source**: [Stooq](https://stooq.com/) (free, no API keys required). Provides daily end-of-day (EOD) historical data that may be delayed; no real-time quotes.

---

## Disclaimer

⚠️ **This software is for research and educational purposes only. Not financial advice.**

Past performance does not guarantee future results. All trading involves risk of loss. The authors and contributors are not responsible for any financial losses. Use at your own risk.

---

## Features

- 📊 **Data ingestion & caching**: Historical daily OHLCV data from Stooq with DuckDB caching
- 📈 **Signal generation**: Momentum, mean reversion, and regime filter signals
- 🎯 **Strategy presets**: Four presets (default, trend, mean_reversion, conservative)
- 🔮 **Ensemble forecasting**: Weighted signal combination with confidence scoring
- 🛡️ **Risk management**: Volatility targeting, position sizing, drawdown stops
- ✅ **Leakage-safe backtesting**: Time-aware engine with transaction costs
- 🔄 **Walk-forward evaluation**: Out-of-sample testing to avoid overfitting
- 🌐 **REST API**: FastAPI backend for programmatic access
- 💻 **Web UI**: React + TypeScript frontend for visualization

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

This starts both backend (port 8000) and frontend (port 8080) servers.

**Access points:**
- Frontend UI: http://localhost:8080
- Backend API: http://127.0.0.1:8000
- API Docs: http://127.0.0.1:8000/docs

### Option B: Run Separately

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

### Backend

From the `backend/` directory:

```bash
pip install -e ".[dev]"
```

This installs the package in editable mode with development dependencies (pytest, black, mypy).

### Frontend

From the `signal-compass/` directory:

```bash
npm install
```

---

## Configuration

### Backend

1. Copy `backend/env.example` to `backend/.env`
2. Default settings work for most use cases (no changes needed)

**Key settings:**
- `DATA_PROVIDER=stooq` (free, no API keys)
- `API_PORT=8000`
- `DUCKDB_PATH=./data/trading.db`
- `CORS_ORIGINS` (comma-separated frontend URLs)

### Frontend

1. Copy `signal-compass/.env.example` to `signal-compass/.env`
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

# Get historical data
Invoke-RestMethod -Uri "http://127.0.0.1:8000/history?ticker=AAPL&start=2024-01-01&end=2024-01-10" -Method Get
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

- `default` - Balanced (equal weights, 30% regime, 10% threshold)
- `trend` - Momentum-focused (60% momentum, 20% mean reversion, 15% threshold)
- `mean_reversion` - Mean reversion-focused (20% momentum, 60% mean reversion, 8% threshold)
- `conservative` - Lower risk (equal weights, 20% regime, 20% threshold)

**Example with preset:**
```bash
curl "http://127.0.0.1:8000/forecast?ticker=AAPL&preset=trend"
```

---

## API Reference

All endpoints return JSON with common metadata:

- `as_of` - Request timestamp (UTC)
- `data_source` - Provider name (e.g., "stooq")
- `is_delayed` - Boolean indicating data staleness
- `staleness_seconds` - Seconds since market close (or `null`)
- `warnings` - Array of warning messages

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check and data source status |
| `GET` | `/history?ticker=AAPL&start=2020-01-01&end=2024-01-01` | Historical OHLCV bars |
| `GET` | `/signals?ticker=AAPL&start=2020-01-01&end=2024-01-01` | Signal history |
| `GET` | `/forecast?ticker=AAPL&preset=default` | Latest forecast |
| `GET` | `/backtest?ticker=AAPL&start=2020-01-01&end=2024-12-31&preset=default` | Run backtest |

Interactive API documentation available at http://127.0.0.1:8000/docs

---

## Data & Staleness

### Stooq Provider

- **Type**: End-of-day (EOD) historical data via CSV downloads
- **Coverage**: US stocks and ETFs
- **Ticker format**: Accepts `AAPL` or `AAPL.us` (normalized internally; `.us` suffix recommended for US stocks)
- **Update frequency**: Daily after market close (data may be delayed by 1+ days)
- **Rate limit**: 1 request/second

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

Run backend tests (offline by default, no external API calls):

```bash
cd backend
python -m pytest -q
```

Tests use mock data providers for reproducibility. Test suite includes leakage detection, math correctness, and API contract validation.

---

## Troubleshooting

**CORS errors**: Add frontend URL to `CORS_ORIGINS` in `backend/.env` (default includes `http://localhost:8080` and common ports)

**Connection refused**: Verify backend is running: `http://127.0.0.1:8000/health`

**Wrong `VITE_API_BASE_URL`**: Ensure `signal-compass/.env` has `VITE_API_BASE_URL=http://127.0.0.1:8000` matching backend port

**Port conflicts**: Change `API_PORT` in `backend/.env` and update `VITE_API_BASE_URL` in `signal-compass/.env`

**Ticker not found**: Try adding `.us` suffix (e.g., `AAPL.us`) for US stocks

**Missing dependencies**: Reinstall backend (`pip install -e ".[dev]"`) or frontend (`npm install`)

---

## Security & Repo Hygiene

- ✅ **No secrets committed**: All configuration via `.env` files (git-ignored)
- ✅ **Free data sources only**: Uses Stooq (no paid APIs or API keys required)
- ✅ **`.gitignore` configured**: Excludes build artifacts, local DBs, logs, `.env` files
- ✅ **Template files**: `.env.example` files provided for setup

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

See LICENSE file in the repository root. (If no LICENSE file exists, please add one for open-source distribution.)
