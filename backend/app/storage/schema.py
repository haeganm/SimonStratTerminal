"""DuckDB schema definitions."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bars (
    ticker VARCHAR NOT NULL,
    date DATE NOT NULL,
    open DOUBLE NOT NULL,
    high DOUBLE NOT NULL,
    low DOUBLE NOT NULL,
    close DOUBLE NOT NULL,
    volume DOUBLE NOT NULL,
    source VARCHAR NOT NULL,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_bars_ticker_date ON bars(ticker, date);
"""
