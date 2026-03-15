#!/usr/bin/env python3
"""
Vault Research Desk — Local SQLite Database

Single module for all DB operations. Every tool reads/writes through here.
Designed for fast queries, zero parsing overhead, and full history retention.

Usage:
    from db import VaultDB
    db = VaultDB()                    # auto-creates tables on first run
    db.upsert_quote("GOOGL", {...})   # cache a price quote
    db.get_quote("GOOGL")            # retrieve cached quote
    db.close()

    # Or as context manager:
    with VaultDB() as db:
        db.get_holdings()
"""

import csv
import json
import os
import sqlite3
from datetime import datetime, date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, "..")
DB_PATH = os.path.join(PROJECT_ROOT, "vault.db")

# Common ticker ↔ company name mapping for institutional data matching
TICKER_COMPANY = {
    "GOOGL": "ALPHABET INC", "GOOG": "ALPHABET INC",
    "AAPL": "APPLE INC", "AMZN": "AMAZON COM INC",
    "MSFT": "MICROSOFT CORP", "META": "META PLATFORMS INC",
    "NVDA": "NVIDIA CORPORATION", "TSLA": "TESLA INC",
    "NFLX": "NETFLIX INC", "CRM": "SALESFORCE INC",
    "MU": "MICRON TECHNOLOGY INC", "PLTR": "PALANTIR TECHNOLOGIES INC",
    "COST": "COSTCO WHSL CORP NEW", "UBER": "UBER TECHNOLOGIES INC",
    "BN": "BROOKFIELD CORP", "BABA": "ALIBABA GROUP HLDG LTD",
    "LMT": "LOCKHEED MARTIN CORP", "RTX": "RTX CORP",
    "NOC": "NORTHROP GRUMMAN CORP", "BA": "BOEING CO",
    "CVX": "CHEVRON CORP NEW", "XOM": "EXXON MOBIL CORP",
    "OXY": "OCCIDENTAL PETE CORP", "KO": "COCA COLA CO",
    "AXP": "AMERICAN EXPRESS CO", "BAC": "BANK AMERICA CORP",
    "JPM": "JPMORGAN CHASE & CO", "GS": "GOLDMAN SACHS GROUP INC",
    "LRCX": "LAM RESEARCH CORP", "ADBE": "ADOBE INC",
    "GE": "GE VERNOVA INC", "WM": "WASTE MGMT INC DEL",
    "TSM": "TAIWAN SEMICONDUCTOR MFG LTD",
    "SPY": "SPDR S&P 500 ETF TR", "QQQ": "INVESCO QQQ TR",
    "IVV": "ISHARES TR", "IWM": "ISHARES TR",
    "XLE": "ENERGY SELECT SECTOR SPDR", "XLV": "HEALTH CARE SELECT SECTOR SPDR",
    "XLK": "TECHNOLOGY SELECT SECTOR SPDR", "XLF": "FINANCIAL SELECT SECTOR SPDR",
    "XLU": "UTILITIES SELECT SECTOR SPDR", "XLI": "INDUSTRIAL SELECT SECTOR SPDR",
    "GLD": "SPDR GOLD SHARES",
}
COMPANY_TICKER = {v: k for k, v in TICKER_COMPANY.items()}

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
-- Portfolio holdings (read from portfolio.md, cached here for fast queries)
CREATE TABLE IF NOT EXISTS holdings (
    ticker       TEXT PRIMARY KEY,
    shares       REAL NOT NULL,
    cost_basis   REAL NOT NULL,
    date_bought  TEXT,
    sector       TEXT,
    asset_type   TEXT DEFAULT 'stock',  -- stock, etf, commodity
    updated_at   TEXT NOT NULL
);

-- Every trade/call ever made
CREATE TABLE IF NOT EXISTS trades (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT NOT NULL,
    ticker       TEXT NOT NULL,
    action       TEXT NOT NULL,         -- BUY, SELL, TRIM, ADD
    entry_price  REAL,
    stop_loss    REAL,
    target       TEXT,                  -- can be range like "62-65"
    conviction   TEXT,                  -- *, **, ***
    status       TEXT DEFAULT 'OPEN',   -- OPEN, CLOSED, STOPPED
    exit_price   REAL,
    exit_date    TEXT,
    return_pct   REAL,
    report       TEXT,                  -- source report filename
    notes        TEXT,
    UNIQUE(date, ticker, action)
);

-- Watchlist: recommended but not bought
CREATE TABLE IF NOT EXISTS watchlist (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT NOT NULL,
    ticker       TEXT NOT NULL,
    price_at_rec REAL,
    conviction   TEXT,
    report       TEXT,
    status       TEXT DEFAULT 'ACTIVE', -- ACTIVE, DROPPED, CONVERTED, EXPIRED
    notes        TEXT,
    UNIQUE(date, ticker)
);

-- Daily portfolio vs VOO benchmark
CREATE TABLE IF NOT EXISTS benchmarks (
    date            TEXT PRIMARY KEY,
    portfolio_value REAL,
    portfolio_pct   REAL,
    voo_price       REAL,
    voo_pct         REAL,
    alpha           REAL
);

-- Price quote cache (avoid redundant API calls within same session)
CREATE TABLE IF NOT EXISTS price_cache (
    ticker      TEXT NOT NULL,
    date        TEXT NOT NULL,
    price       REAL,
    prev_close  REAL,
    change_pct  REAL,
    high        REAL,
    low         REAL,
    volume      INTEGER,
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (ticker, date)
);

-- Technical indicators cache
CREATE TABLE IF NOT EXISTS technicals_cache (
    ticker      TEXT NOT NULL,
    date        TEXT NOT NULL,
    rsi         REAL,
    dma_50      REAL,
    dma_200     REAL,
    high_52w    REAL,
    low_52w     REAL,
    pct_from_high REAL,
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (ticker, date)
);

-- Institutional 13F holdings
CREATE TABLE IF NOT EXISTS institutional (
    fund         TEXT NOT NULL,
    ticker       TEXT NOT NULL,
    company_name TEXT,
    shares       REAL,
    value        REAL,              -- in thousands
    pct_portfolio REAL,
    quarter      TEXT NOT NULL,     -- e.g. "Q4-2025"
    filing_date  TEXT,
    PRIMARY KEY (fund, ticker, quarter)
);

-- Fund-level metadata
CREATE TABLE IF NOT EXISTS funds (
    name            TEXT NOT NULL,
    quarter         TEXT NOT NULL,
    portfolio_value REAL,
    num_positions   INTEGER,
    top5_conc       REAL,           -- top 5 concentration %
    top10_conc      REAL,
    filing_date     TEXT,
    PRIMARY KEY (name, quarter)
);

-- Insider transactions (SEC Form 4)
CREATE TABLE IF NOT EXISTS insider_txns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    insider_name    TEXT,
    title           TEXT,           -- CEO, CFO, Director, etc.
    txn_type        TEXT,           -- BUY, SELL, OPTION_EXERCISE
    shares          REAL,
    price           REAL,
    value           REAL,
    txn_date        TEXT,
    filing_date     TEXT,
    source          TEXT,
    UNIQUE(ticker, insider_name, txn_date, txn_type, shares)
);

-- Screener results (keep history, not just latest)
CREATE TABLE IF NOT EXISTS screener_results (
    run_id      TEXT NOT NULL,      -- timestamp of scan run
    ticker      TEXT NOT NULL,
    price       REAL,
    rsi         REAL,
    dma_50      REAL,
    dma_200     REAL,
    high_52w    REAL,
    low_52w     REAL,
    volume_ratio REAL,
    earnings_date TEXT,
    signals     TEXT,               -- comma-separated
    score       INTEGER,
    sector      TEXT,
    PRIMARY KEY (run_id, ticker)
);

-- Investment theses
CREATE TABLE IF NOT EXISTS theses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    direction       TEXT NOT NULL,  -- BUY, HOLD, SELL, AVOID
    conviction      TEXT,
    thesis          TEXT,
    key_conditions  TEXT,           -- what would change the thesis
    date_opened     TEXT NOT NULL,
    date_closed     TEXT,
    status          TEXT DEFAULT 'ACTIVE',  -- ACTIVE, CLOSED, FLIPPED
    source_report   TEXT,
    UNIQUE(ticker, date_opened, direction)
);

-- Thesis history entries
CREATE TABLE IF NOT EXISTS thesis_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    thesis_id   INTEGER NOT NULL,
    date        TEXT NOT NULL,
    note        TEXT,
    FOREIGN KEY (thesis_id) REFERENCES theses(id)
);

-- AVOID calls tracking
CREATE TABLE IF NOT EXISTS avoid_calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    price_at_call REAL,
    report      TEXT,
    reason      TEXT,
    UNIQUE(date, ticker)
);

-- Report metadata
CREATE TABLE IF NOT EXISTS reports (
    filename    TEXT PRIMARY KEY,
    date        TEXT NOT NULL,
    report_type TEXT,               -- full, flash, analyze
    alerts_triggered INTEGER DEFAULT 0,
    positions_count  INTEGER,
    path        TEXT
);

-- Market snapshots (macro state at each report)
CREATE TABLE IF NOT EXISTS market_snapshots (
    date        TEXT PRIMARY KEY,
    spy         REAL,
    vix         REAL,
    oil         REAL,
    gold        REAL,
    dxy         REAL,
    ten_year    REAL,
    nasdaq      REAL,
    breadth_50  REAL,              -- % above 50 DMA
    breadth_200 REAL               -- % above 200 DMA
);

-- Consensus holdings (derived from institutional, but cached for speed)
CREATE TABLE IF NOT EXISTS consensus (
    ticker      TEXT NOT NULL,
    quarter     TEXT NOT NULL,
    fund_count  INTEGER,
    funds       TEXT,               -- comma-separated fund names
    avg_pct     REAL,              -- average % across holding funds
    PRIMARY KEY (ticker, quarter)
);

-- Sector rotation tracking
CREATE TABLE IF NOT EXISTS sector_performance (
    date        TEXT NOT NULL,
    sector      TEXT NOT NULL,
    etf_ticker  TEXT,
    price       REAL,
    change_1w   REAL,
    change_1m   REAL,
    rsi         REAL,
    rank        INTEGER,           -- 1 = best performing
    PRIMARY KEY (date, sector)
);

-- ARK Invest daily trades
CREATE TABLE IF NOT EXISTS ark_trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    fund        TEXT NOT NULL,             -- ARKK, ARKG, ARKW, etc.
    ticker      TEXT NOT NULL,
    company     TEXT,
    direction   TEXT NOT NULL,             -- Buy / Sell
    shares      INTEGER,
    etf_percent REAL,                      -- weight impact
    cached_at   TEXT NOT NULL,
    UNIQUE(date, fund, ticker, direction)
);

-- Superinvestor holdings (Dataroma)
CREATE TABLE IF NOT EXISTS guru_holdings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guru_code   TEXT NOT NULL,             -- BRK, psc, GLRE, etc.
    guru_name   TEXT,
    ticker      TEXT NOT NULL,
    company     TEXT,
    pct_portfolio REAL,
    activity    TEXT,                       -- Buy, Add X%, Reduce X%, Sell
    shares      INTEGER,
    value       REAL,                      -- in dollars
    reported_price REAL,
    quarter     TEXT NOT NULL,             -- e.g. Q4-2025
    cached_at   TEXT NOT NULL,
    UNIQUE(guru_code, ticker, quarter)
);

-- News articles (Finnhub)
CREATE TABLE IF NOT EXISTS news (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT NOT NULL,          -- ticker symbol or 'MARKET' for general news
    headline    TEXT NOT NULL,
    summary     TEXT,
    source      TEXT,                   -- e.g. "Reuters", "CNBC"
    url         TEXT,
    published   TEXT NOT NULL,          -- ISO datetime
    category    TEXT,                   -- 'company' or 'general'
    sentiment   REAL,                   -- future: -1.0 to 1.0
    cached_at   TEXT NOT NULL,
    UNIQUE(ticker, headline, published)
);

CREATE TABLE IF NOT EXISTS improvements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    type        TEXT NOT NULL,              -- 'self_analysis' or 'learn_from_pros'
    category    TEXT,                       -- e.g. 'concentration', 'bias', 'portfolio_risk'
    priority    TEXT,                       -- 'HIGH', 'MEDIUM', 'LOW'
    finding     TEXT NOT NULL,
    action      TEXT,                       -- recommended action
    target_file TEXT,                       -- system file this applies to
    status      TEXT DEFAULT 'active',      -- 'active', 'applied', 'resolved', 'obsolete'
    source      TEXT,                       -- report filename or run identifier
    meta        TEXT,                       -- JSON blob for extra structured data
    created_at  TEXT NOT NULL
);
"""

# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------

class VaultDB:
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row  # dict-like access
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ------------------------------------------------------------------
    # Holdings
    # ------------------------------------------------------------------
    def upsert_holding(self, ticker, shares, cost_basis, date_bought=None,
                       sector=None, asset_type='stock'):
        self.conn.execute("""
            INSERT INTO holdings (ticker, shares, cost_basis, date_bought, sector, asset_type, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                shares=excluded.shares, cost_basis=excluded.cost_basis,
                date_bought=excluded.date_bought, sector=excluded.sector,
                asset_type=excluded.asset_type, updated_at=excluded.updated_at
        """, (ticker, shares, cost_basis, date_bought, sector, asset_type,
              datetime.now().isoformat()))
        self.conn.commit()

    def get_holdings(self):
        return self.conn.execute("SELECT * FROM holdings ORDER BY ticker").fetchall()

    def get_holding(self, ticker):
        return self.conn.execute("SELECT * FROM holdings WHERE ticker=?", (ticker,)).fetchone()

    def remove_holding(self, ticker):
        self.conn.execute("DELETE FROM holdings WHERE ticker=?", (ticker,))
        self.conn.commit()

    def sync_holdings_from_portfolio(self):
        """Read portfolio.md and sync holdings into DB."""
        import sys
        sys.path.insert(0, SCRIPT_DIR)
        from data_fetcher import read_portfolio
        tickers, holdings, settings = read_portfolio()

        etfs = {"XLE", "XLV", "XLK", "XLF", "XLY", "XLP", "XLI", "XLB",
                "XLRE", "XLU", "XLC", "GLD", "SLV", "VOO", "SPY", "QQQ", "IWM"}

        for ticker in tickers:
            h = holdings.get(ticker, {})
            self.upsert_holding(
                ticker=ticker,
                shares=h.get("shares", 0),
                cost_basis=h.get("cost", 0),
                date_bought=h.get("date"),
                asset_type="etf" if ticker in etfs else "stock"
            )

        # Remove holdings no longer in portfolio.md
        db_tickers = {r["ticker"] for r in self.get_holdings()}
        for old in db_tickers - set(tickers):
            self.remove_holding(old)

        return len(tickers)

    # ------------------------------------------------------------------
    # Trades (performance log)
    # ------------------------------------------------------------------
    def add_trade(self, date, ticker, action, entry_price=None, stop_loss=None,
                  target=None, conviction=None, status='OPEN', report=None, notes=None):
        try:
            self.conn.execute("""
                INSERT INTO trades (date, ticker, action, entry_price, stop_loss, target,
                    conviction, status, report, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (date, ticker, action, entry_price, stop_loss, target,
                  conviction, status, report, notes))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # duplicate

    def get_open_trades(self):
        return self.conn.execute(
            "SELECT * FROM trades WHERE status='OPEN' ORDER BY date"
        ).fetchall()

    def get_all_trades(self):
        return self.conn.execute("SELECT * FROM trades ORDER BY date").fetchall()

    def close_trade(self, ticker, exit_price, exit_date=None, return_pct=None):
        exit_date = exit_date or date.today().isoformat()
        self.conn.execute("""
            UPDATE trades SET status='CLOSED', exit_price=?, exit_date=?, return_pct=?
            WHERE ticker=? AND status='OPEN'
        """, (exit_price, exit_date, return_pct, ticker))
        self.conn.commit()

    def get_trade_stats(self):
        """Return win rate, avg return, total trades."""
        rows = self.conn.execute("""
            SELECT count(*) as total,
                   sum(case when return_pct > 0 then 1 else 0 end) as wins,
                   avg(return_pct) as avg_return
            FROM trades WHERE status='CLOSED' AND return_pct IS NOT NULL
        """).fetchone()
        return dict(rows) if rows else {}

    # ------------------------------------------------------------------
    # Watchlist
    # ------------------------------------------------------------------
    def add_watchlist(self, date, ticker, price_at_rec=None, conviction=None,
                      report=None, notes=None):
        try:
            self.conn.execute("""
                INSERT INTO watchlist (date, ticker, price_at_rec, conviction, report, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (date, ticker, price_at_rec, conviction, report, notes))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_active_watchlist(self):
        return self.conn.execute(
            "SELECT * FROM watchlist WHERE status='ACTIVE' ORDER BY date DESC"
        ).fetchall()

    def update_watchlist_status(self, ticker, status, date=None):
        if date:
            self.conn.execute(
                "UPDATE watchlist SET status=? WHERE ticker=? AND date=?",
                (status, ticker, date))
        else:
            self.conn.execute(
                "UPDATE watchlist SET status=? WHERE ticker=? AND status='ACTIVE'",
                (status, ticker))
        self.conn.commit()

    # ------------------------------------------------------------------
    # Benchmarks
    # ------------------------------------------------------------------
    def add_benchmark(self, date, portfolio_value, portfolio_pct,
                      voo_price, voo_pct, alpha):
        self.conn.execute("""
            INSERT OR REPLACE INTO benchmarks
            VALUES (?, ?, ?, ?, ?, ?)
        """, (date, portfolio_value, portfolio_pct, voo_price, voo_pct, alpha))
        self.conn.commit()

    def get_benchmarks(self, limit=30):
        return self.conn.execute(
            "SELECT * FROM benchmarks ORDER BY date DESC LIMIT ?", (limit,)
        ).fetchall()

    def get_latest_alpha(self):
        row = self.conn.execute(
            "SELECT alpha FROM benchmarks ORDER BY date DESC LIMIT 1"
        ).fetchone()
        return row["alpha"] if row else None

    # ------------------------------------------------------------------
    # Price cache
    # ------------------------------------------------------------------
    def cache_quote(self, ticker, quote_data):
        """Cache a quote from data_fetcher.fetch_quote()."""
        today = date.today().isoformat()
        self.conn.execute("""
            INSERT OR REPLACE INTO price_cache
            (ticker, date, price, prev_close, change_pct, high, low, volume, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (ticker, today,
              quote_data.get('price'), quote_data.get('prev_close'),
              quote_data.get('change_pct'), quote_data.get('high'),
              quote_data.get('low'), quote_data.get('volume'),
              datetime.now().isoformat()))
        self.conn.commit()

    def get_cached_quote(self, ticker, max_age_minutes=15):
        """Get cached quote if fresh enough."""
        row = self.conn.execute("""
            SELECT * FROM price_cache
            WHERE ticker=? AND date=?
            ORDER BY fetched_at DESC LIMIT 1
        """, (ticker, date.today().isoformat())).fetchone()

        if row:
            fetched = datetime.fromisoformat(row["fetched_at"])
            age = (datetime.now() - fetched).total_seconds() / 60
            if age <= max_age_minutes:
                return dict(row)
        return None

    def cache_technicals(self, ticker, tech_data):
        today = date.today().isoformat()
        self.conn.execute("""
            INSERT OR REPLACE INTO technicals_cache
            (ticker, date, rsi, dma_50, dma_200, high_52w, low_52w, pct_from_high, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (ticker, today,
              tech_data.get('rsi'), tech_data.get('dma_50'),
              tech_data.get('dma_200'), tech_data.get('high_52w'),
              tech_data.get('low_52w'), tech_data.get('pct_from_high'),
              datetime.now().isoformat()))
        self.conn.commit()

    def get_cached_technicals(self, ticker, max_age_minutes=60):
        row = self.conn.execute("""
            SELECT * FROM technicals_cache
            WHERE ticker=? AND date=?
            ORDER BY fetched_at DESC LIMIT 1
        """, (ticker, date.today().isoformat())).fetchone()

        if row:
            fetched = datetime.fromisoformat(row["fetched_at"])
            age = (datetime.now() - fetched).total_seconds() / 60
            if age <= max_age_minutes:
                return dict(row)
        return None

    # ------------------------------------------------------------------
    # Institutional (13F)
    # ------------------------------------------------------------------
    def add_institutional(self, fund, ticker, company_name=None, shares=None,
                          value=None, pct_portfolio=None, quarter=None, filing_date=None):
        self.conn.execute("""
            INSERT OR REPLACE INTO institutional
            (fund, ticker, company_name, shares, value, pct_portfolio, quarter, filing_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (fund, ticker, company_name, shares, value, pct_portfolio, quarter, filing_date))
        self.conn.commit()

    def add_fund(self, name, quarter, portfolio_value=None, num_positions=None,
                 top5_conc=None, top10_conc=None, filing_date=None):
        self.conn.execute("""
            INSERT OR REPLACE INTO funds
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, quarter, portfolio_value, num_positions,
              top5_conc, top10_conc, filing_date))
        self.conn.commit()

    def get_consensus(self, min_funds=2, quarter=None):
        """Find tickers held by multiple funds."""
        q = quarter or self._latest_quarter()
        if not q:
            return []
        return self.conn.execute("""
            SELECT ticker, company_name,
                   count(DISTINCT fund) as fund_count,
                   group_concat(DISTINCT fund) as funds,
                   avg(pct_portfolio) as avg_pct
            FROM institutional
            WHERE quarter=?
            GROUP BY ticker
            HAVING fund_count >= ?
            ORDER BY fund_count DESC, avg_pct DESC
        """, (q, min_funds)).fetchall()

    def get_fund_holdings(self, fund, quarter=None, limit=20):
        q = quarter or self._latest_quarter()
        if not q:
            return []
        return self.conn.execute("""
            SELECT * FROM institutional
            WHERE fund=? AND quarter=?
            ORDER BY pct_portfolio DESC
            LIMIT ?
        """, (fund, q, limit)).fetchall()

    def ticker_held_by(self, ticker, quarter=None):
        """Which funds hold this ticker? Matches both ticker and company name."""
        q = quarter or self._latest_quarter()
        if not q:
            return []
        # Try both the ticker itself and the company name
        names = [ticker]
        if ticker in TICKER_COMPANY:
            names.append(TICKER_COMPANY[ticker])
        if ticker in COMPANY_TICKER:
            names.append(COMPANY_TICKER[ticker])
        placeholders = ",".join("?" * len(names))
        return self.conn.execute(f"""
            SELECT fund, pct_portfolio, shares, value, company_name
            FROM institutional
            WHERE ticker IN ({placeholders}) AND quarter=?
            ORDER BY pct_portfolio DESC
        """, (*names, q)).fetchall()

    def _latest_quarter(self):
        row = self.conn.execute(
            "SELECT quarter FROM funds ORDER BY quarter DESC LIMIT 1"
        ).fetchone()
        return row["quarter"] if row else None

    # ------------------------------------------------------------------
    # Insider transactions
    # ------------------------------------------------------------------
    def add_insider_txn(self, ticker, insider_name=None, title=None,
                        txn_type=None, shares=None, price=None, value=None,
                        txn_date=None, filing_date=None, source=None):
        try:
            self.conn.execute("""
                INSERT INTO insider_txns
                (ticker, insider_name, title, txn_type, shares, price, value,
                 txn_date, filing_date, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (ticker, insider_name, title, txn_type, shares, price, value,
                  txn_date, filing_date, source))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_insider_buys(self, ticker=None, days=90):
        if ticker:
            return self.conn.execute("""
                SELECT * FROM insider_txns
                WHERE ticker=? AND txn_type='BUY'
                  AND txn_date >= date('now', ?)
                ORDER BY txn_date DESC
            """, (ticker, f'-{days} days')).fetchall()
        return self.conn.execute("""
            SELECT * FROM insider_txns
            WHERE txn_type='BUY' AND txn_date >= date('now', ?)
            ORDER BY value DESC
        """, (f'-{days} days',)).fetchall()

    def get_cluster_buys(self, days=90, min_insiders=2):
        """Find tickers with multiple insiders buying recently."""
        return self.conn.execute("""
            SELECT ticker,
                   count(DISTINCT insider_name) as num_insiders,
                   sum(value) as total_value,
                   min(txn_date) as first_buy,
                   max(txn_date) as last_buy
            FROM insider_txns
            WHERE txn_type='BUY' AND txn_date >= date('now', ?)
            GROUP BY ticker
            HAVING num_insiders >= ?
            ORDER BY total_value DESC
        """, (f'-{days} days', min_insiders)).fetchall()

    # ------------------------------------------------------------------
    # Screener
    # ------------------------------------------------------------------
    def save_screener_run(self, results, run_id=None):
        """Save a batch of screener results."""
        run_id = run_id or datetime.now().strftime('%Y-%m-%d %H:%M')
        for r in results:
            self.conn.execute("""
                INSERT OR REPLACE INTO screener_results
                (run_id, ticker, price, rsi, dma_50, dma_200, high_52w, low_52w,
                 volume_ratio, earnings_date, signals, score, sector)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (run_id, r.get('ticker'), r.get('price'), r.get('rsi'),
                  r.get('dma_50'), r.get('dma_200'), r.get('high_52w'),
                  r.get('low_52w'), r.get('volume_ratio'), r.get('earnings_date'),
                  r.get('signals'), r.get('score'), r.get('sector')))
        self.conn.commit()
        return run_id

    def get_latest_screener(self, min_score=4, limit=20):
        """Get top picks from most recent screener run."""
        run = self.conn.execute(
            "SELECT run_id FROM screener_results ORDER BY run_id DESC LIMIT 1"
        ).fetchone()
        if not run:
            return []
        return self.conn.execute("""
            SELECT * FROM screener_results
            WHERE run_id=? AND score >= ?
            ORDER BY score DESC
            LIMIT ?
        """, (run["run_id"], min_score, limit)).fetchall()

    def get_screener_history(self, ticker, limit=10):
        """Track a ticker's screener score over time."""
        return self.conn.execute("""
            SELECT run_id, score, rsi, signals
            FROM screener_results WHERE ticker=?
            ORDER BY run_id DESC LIMIT ?
        """, (ticker, limit)).fetchall()

    # ------------------------------------------------------------------
    # Theses
    # ------------------------------------------------------------------
    def add_thesis(self, ticker, direction, conviction=None, thesis=None,
                   key_conditions=None, date_opened=None, source_report=None):
        try:
            self.conn.execute("""
                INSERT INTO theses
                (ticker, direction, conviction, thesis, key_conditions,
                 date_opened, source_report)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (ticker, direction, conviction, thesis, key_conditions,
                  date_opened or date.today().isoformat(), source_report))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_active_theses(self):
        return self.conn.execute(
            "SELECT * FROM theses WHERE status='ACTIVE' ORDER BY date_opened DESC"
        ).fetchall()

    def get_thesis(self, ticker):
        return self.conn.execute(
            "SELECT * FROM theses WHERE ticker=? AND status='ACTIVE' ORDER BY date_opened DESC LIMIT 1",
            (ticker,)
        ).fetchone()

    def close_thesis(self, ticker, reason=None):
        self.conn.execute(
            "UPDATE theses SET status='CLOSED', date_closed=? WHERE ticker=? AND status='ACTIVE'",
            (date.today().isoformat(), ticker))
        if reason:
            # Get thesis id for history
            row = self.conn.execute(
                "SELECT id FROM theses WHERE ticker=? ORDER BY date_closed DESC LIMIT 1",
                (ticker,)).fetchone()
            if row:
                self.conn.execute(
                    "INSERT INTO thesis_history (thesis_id, date, note) VALUES (?, ?, ?)",
                    (row["id"], date.today().isoformat(), reason))
        self.conn.commit()

    # ------------------------------------------------------------------
    # Theses (extended for DB-primary mode)
    # ------------------------------------------------------------------
    def get_all_theses(self):
        """Return all theses (active + closed) with history."""
        rows = self.conn.execute(
            "SELECT * FROM theses ORDER BY date_opened DESC"
        ).fetchall()
        result = []
        for r in rows:
            t = dict(r)
            t['history'] = [
                dict(h) for h in self.conn.execute(
                    "SELECT date, note FROM thesis_history WHERE thesis_id=? ORDER BY date",
                    (r['id'],)
                ).fetchall()
            ]
            result.append(t)
        return result

    def get_thesis_full(self, ticker):
        """Get active thesis with history, matching thesis_log.json shape."""
        row = self.get_thesis(ticker)
        if not row:
            return None
        t = dict(row)
        t['history'] = [
            dict(h) for h in self.conn.execute(
                "SELECT date, note FROM thesis_history WHERE thesis_id=? ORDER BY date",
                (row['id'],)
            ).fetchall()
        ]
        return t

    def update_thesis(self, ticker, direction=None, conviction=None,
                      thesis=None, key_conditions=None):
        """Update fields on an active thesis."""
        row = self.get_thesis(ticker)
        if not row:
            return False
        updates = []
        params = []
        if direction is not None:
            updates.append("direction=?")
            params.append(direction)
        if conviction is not None:
            updates.append("conviction=?")
            params.append(conviction)
        if thesis is not None:
            updates.append("thesis=?")
            params.append(thesis)
        if key_conditions is not None:
            updates.append("key_conditions=?")
            params.append(key_conditions)
        if not updates:
            return False
        params.append(row['id'])
        self.conn.execute(
            f"UPDATE theses SET {', '.join(updates)} WHERE id=?", params)
        self.conn.commit()
        return True

    def close_thesis_with_status(self, ticker, status='CLOSED', note=None):
        """Close thesis with specific status (CLOSED, CONFIRMED, INVALIDATED, EXPIRED)."""
        row = self.get_thesis(ticker)
        if not row:
            return False
        self.conn.execute(
            "UPDATE theses SET status=?, date_closed=? WHERE id=?",
            (status, date.today().isoformat(), row['id']))
        if note:
            self.conn.execute(
                "INSERT INTO thesis_history (thesis_id, date, note) VALUES (?, ?, ?)",
                (row['id'], date.today().isoformat(), note))
        self.conn.commit()
        return True

    def add_thesis_history(self, ticker, note):
        """Add a history note to the active thesis for a ticker."""
        row = self.get_thesis(ticker)
        if not row:
            return False
        self.conn.execute(
            "INSERT INTO thesis_history (thesis_id, date, note) VALUES (?, ?, ?)",
            (row['id'], date.today().isoformat(), note))
        self.conn.commit()
        return True

    def get_all_watchlist(self):
        """Return all watchlist entries (active + dropped + converted)."""
        return self.conn.execute(
            "SELECT * FROM watchlist ORDER BY date DESC"
        ).fetchall()

    def watchlist_exists(self, date, ticker):
        """Check if a watchlist entry already exists."""
        row = self.conn.execute(
            "SELECT 1 FROM watchlist WHERE date=? AND ticker=?",
            (date, ticker)
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # ARK Invest trades
    # ------------------------------------------------------------------
    def cache_ark_trades(self, trades):
        """Bulk-insert ARK daily trades."""
        now = datetime.now().isoformat()
        for t in trades:
            try:
                self.conn.execute("""
                    INSERT OR IGNORE INTO ark_trades
                    (date, fund, ticker, company, direction, shares, etf_percent, cached_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (t.get('date', ''), t.get('fund', ''), t.get('ticker', ''),
                      t.get('company', ''), t.get('direction', ''),
                      t.get('shares'), t.get('etf_percent'), now))
            except Exception:
                pass
        self.conn.commit()

    def get_ark_trades(self, days=30, ticker=None, direction=None):
        """Get recent ARK trades, optionally filtered."""
        cutoff = (datetime.now() - __import__('datetime').timedelta(days=days)).strftime('%Y-%m-%d')
        query = "SELECT * FROM ark_trades WHERE date >= ?"
        params = [cutoff]
        if ticker:
            query += " AND ticker = ?"
            params.append(ticker)
        if direction:
            query += " AND direction = ?"
            params.append(direction)
        query += " ORDER BY date DESC, fund"
        return self.conn.execute(query, params).fetchall()

    def get_ark_conviction(self, ticker):
        """Count how many times ARK bought/sold a ticker recently."""
        buys = self.conn.execute(
            "SELECT COUNT(*) as c, SUM(shares) as s FROM ark_trades WHERE ticker=? AND direction='Buy'",
            (ticker,)).fetchone()
        sells = self.conn.execute(
            "SELECT COUNT(*) as c, SUM(shares) as s FROM ark_trades WHERE ticker=? AND direction='Sell'",
            (ticker,)).fetchone()
        return {
            'ticker': ticker,
            'buy_count': buys['c'] or 0, 'buy_shares': buys['s'] or 0,
            'sell_count': sells['c'] or 0, 'sell_shares': sells['s'] or 0,
            'net_direction': 'ACCUMULATING' if (buys['c'] or 0) > (sells['c'] or 0) else
                            'DISTRIBUTING' if (sells['c'] or 0) > (buys['c'] or 0) else 'NEUTRAL',
        }

    # ------------------------------------------------------------------
    # Guru holdings (Dataroma)
    # ------------------------------------------------------------------
    def cache_guru_holdings(self, guru_code, guru_name, holdings, quarter):
        """Bulk-insert superinvestor holdings."""
        now = datetime.now().isoformat()
        for h in holdings:
            try:
                self.conn.execute("""
                    INSERT OR REPLACE INTO guru_holdings
                    (guru_code, guru_name, ticker, company, pct_portfolio,
                     activity, shares, value, reported_price, quarter, cached_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (guru_code, guru_name, h.get('ticker', ''), h.get('company', ''),
                      h.get('pct_portfolio'), h.get('activity', ''),
                      h.get('shares'), h.get('value'), h.get('reported_price'),
                      quarter, now))
            except Exception:
                pass
        self.conn.commit()

    def get_guru_holdings(self, guru_code=None, ticker=None):
        """Query guru holdings."""
        if ticker:
            return self.conn.execute(
                "SELECT * FROM guru_holdings WHERE ticker=? ORDER BY pct_portfolio DESC",
                (ticker,)).fetchall()
        if guru_code:
            return self.conn.execute(
                "SELECT * FROM guru_holdings WHERE guru_code=? ORDER BY pct_portfolio DESC",
                (guru_code,)).fetchall()
        return self.conn.execute(
            "SELECT * FROM guru_holdings ORDER BY guru_code, pct_portfolio DESC"
        ).fetchall()

    def get_guru_consensus(self, min_gurus=2):
        """Tickers held by N+ superinvestors."""
        return self.conn.execute("""
            SELECT ticker, company,
                   COUNT(DISTINCT guru_code) as guru_count,
                   GROUP_CONCAT(DISTINCT guru_name) as gurus,
                   ROUND(AVG(pct_portfolio), 2) as avg_pct
            FROM guru_holdings
            WHERE quarter = (SELECT MAX(quarter) FROM guru_holdings)
            GROUP BY ticker
            HAVING guru_count >= ?
            ORDER BY guru_count DESC, avg_pct DESC
        """, (min_gurus,)).fetchall()

    # ------------------------------------------------------------------
    # News (Finnhub)
    def cache_news(self, ticker, articles):
        """Bulk-insert news articles. Skips duplicates via UNIQUE constraint."""
        now = datetime.now().isoformat()
        for a in articles:
            try:
                self.conn.execute("""
                    INSERT OR IGNORE INTO news
                    (ticker, headline, summary, source, url, published, category, sentiment, cached_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (ticker, a.get('headline', ''), a.get('summary', ''),
                      a.get('source', ''), a.get('url', ''),
                      a.get('published', ''), a.get('category', 'company'),
                      a.get('sentiment'), now))
            except Exception:
                pass
        self.conn.commit()

    def get_cached_news(self, ticker, max_age_minutes=60, limit=20):
        """Return cached news if fresh enough, else None."""
        row = self.conn.execute(
            "SELECT cached_at FROM news WHERE ticker=? ORDER BY cached_at DESC LIMIT 1",
            (ticker,)
        ).fetchone()
        if not row:
            return None
        cached_at = datetime.fromisoformat(row['cached_at'])
        age_min = (datetime.now() - cached_at).total_seconds() / 60
        if age_min > max_age_minutes:
            return None
        return self.conn.execute(
            "SELECT * FROM news WHERE ticker=? ORDER BY published DESC LIMIT ?",
            (ticker, limit)
        ).fetchall()

    def get_recent_news(self, ticker=None, days=7, limit=50):
        """All news from last N days, optionally filtered by ticker."""
        cutoff = (datetime.now() - __import__('datetime').timedelta(days=days)).isoformat()
        if ticker:
            return self.conn.execute(
                "SELECT * FROM news WHERE ticker=? AND published>=? ORDER BY published DESC LIMIT ?",
                (ticker, cutoff, limit)
            ).fetchall()
        return self.conn.execute(
            "SELECT * FROM news WHERE published>=? ORDER BY published DESC LIMIT ?",
            (cutoff, limit)
        ).fetchall()

    # ------------------------------------------------------------------
    # Fund analysis reconstruction (for learn_from_pros DB-primary)
    # ------------------------------------------------------------------
    def reconstruct_fund_analysis(self, fund_name, quarter=None):
        """Rebuild the analysis dict from funds + institutional tables."""
        q = quarter or self._latest_quarter()
        if not q:
            return {}
        fund = self.conn.execute(
            "SELECT * FROM funds WHERE name=? AND quarter=?",
            (fund_name, q)
        ).fetchone()
        if not fund:
            return {}
        holdings = self.conn.execute(
            "SELECT * FROM institutional WHERE fund=? AND quarter=? ORDER BY pct_portfolio DESC",
            (fund_name, q)
        ).fetchall()
        top10 = [(h['company_name'] or h['ticker'], h['pct_portfolio']) for h in holdings[:10]]
        return {
            'name': fund_name,
            'filing_date': fund['filing_date'] or '',
            'total_value_millions': fund['portfolio_value'] or 0,
            'num_positions': fund['num_positions'] or len(holdings),
            'top5_pct': fund['top5_conc'] or 0,
            'top10_pct': fund['top10_conc'] or 0,
            'largest_position_pct': top10[0][1] if top10 else 0,
            'largest_position': top10[0][0] if top10 else '',
            'avg_position_pct': round(100 / max(len(holdings), 1), 2),
            'top10': top10,
        }

    def get_all_fund_analyses(self, quarter=None):
        """Reconstruct all fund analyses from DB."""
        q = quarter or self._latest_quarter()
        if not q:
            return []
        funds = self.conn.execute(
            "SELECT name FROM funds WHERE quarter=? ORDER BY name", (q,)
        ).fetchall()
        return [self.reconstruct_fund_analysis(f['name'], q) for f in funds]

    # ------------------------------------------------------------------
    # Export (human-readable CSV dump on demand)
    # ------------------------------------------------------------------
    def export_tables(self, export_dir=None):
        """Dump key tables to CSV files for human readability."""
        export_dir = export_dir or os.path.join(PROJECT_ROOT, "exports")
        os.makedirs(export_dir, exist_ok=True)

        tables = {
            'trades': "SELECT date, ticker, action, entry_price as entry, stop_loss as stop, target, conviction, status, exit_price, exit_date, return_pct, report, notes FROM trades ORDER BY date",
            'watchlist': "SELECT date, ticker, price_at_rec, conviction, report, status, notes FROM watchlist ORDER BY date DESC",
            'benchmarks': "SELECT * FROM benchmarks ORDER BY date DESC",
            'theses': "SELECT ticker, direction, conviction, thesis, key_conditions, date_opened, date_closed, status, source_report FROM theses ORDER BY date_opened DESC",
            'institutional_consensus': "SELECT ticker, fund_count, funds, avg_pct FROM consensus WHERE quarter=(SELECT max(quarter) FROM consensus) ORDER BY fund_count DESC",
            'holdings': "SELECT ticker, shares, cost_basis, date_bought, sector, asset_type FROM holdings ORDER BY ticker",
        }

        exported = []
        for name, query in tables.items():
            rows = self.conn.execute(query).fetchall()
            if not rows:
                continue
            path = os.path.join(export_dir, f"{name}.csv")
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(rows[0].keys())
                for r in rows:
                    writer.writerow(tuple(r))
            exported.append((name, len(rows), path))

        return exported

    # ------------------------------------------------------------------
    # Avoid calls
    # ------------------------------------------------------------------
    def add_avoid(self, date, ticker, price_at_call=None, report=None, reason=None):
        try:
            self.conn.execute("""
                INSERT INTO avoid_calls (date, ticker, price_at_call, report, reason)
                VALUES (?, ?, ?, ?, ?)
            """, (date, ticker, price_at_call, report, reason))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_avoid_accuracy(self):
        """Check if AVOID calls were correct (price dropped after)."""
        return self.conn.execute("""
            SELECT a.date, a.ticker, a.price_at_call, a.reason,
                   p.price as current_price,
                   CASE WHEN p.price IS NOT NULL
                        THEN round((p.price - a.price_at_call) / a.price_at_call * 100, 2)
                        ELSE NULL END as change_pct
            FROM avoid_calls a
            LEFT JOIN price_cache p ON a.ticker = p.ticker
                AND p.date = (SELECT max(date) FROM price_cache WHERE ticker=a.ticker)
            ORDER BY a.date DESC
        """).fetchall()

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------
    def add_report(self, filename, date, report_type='full',
                   alerts_triggered=0, positions_count=None, path=None):
        self.conn.execute("""
            INSERT OR REPLACE INTO reports
            VALUES (?, ?, ?, ?, ?, ?)
        """, (filename, date, report_type, alerts_triggered, positions_count, path))
        self.conn.commit()

    def get_reports(self, limit=20):
        return self.conn.execute(
            "SELECT * FROM reports ORDER BY date DESC LIMIT ?", (limit,)
        ).fetchall()

    # ------------------------------------------------------------------
    # Market snapshots
    # ------------------------------------------------------------------
    def save_market_snapshot(self, date, spy=None, vix=None, oil=None,
                             gold=None, dxy=None, ten_year=None, nasdaq=None,
                             breadth_50=None, breadth_200=None):
        self.conn.execute("""
            INSERT OR REPLACE INTO market_snapshots
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (date, spy, vix, oil, gold, dxy, ten_year, nasdaq,
              breadth_50, breadth_200))
        self.conn.commit()

    def get_market_history(self, limit=30):
        return self.conn.execute(
            "SELECT * FROM market_snapshots ORDER BY date DESC LIMIT ?", (limit,)
        ).fetchall()

    def get_latest_snapshot(self):
        return self.conn.execute(
            "SELECT * FROM market_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()

    # ------------------------------------------------------------------
    # Consensus (derived)
    # ------------------------------------------------------------------
    def rebuild_consensus(self, quarter=None):
        """Rebuild consensus table from institutional holdings."""
        q = quarter or self._latest_quarter()
        if not q:
            return

        self.conn.execute("DELETE FROM consensus WHERE quarter=?", (q,))
        self.conn.execute("""
            INSERT INTO consensus (ticker, quarter, fund_count, funds, avg_pct)
            SELECT ticker, quarter,
                   count(DISTINCT fund),
                   group_concat(DISTINCT fund),
                   round(avg(pct_portfolio), 2)
            FROM institutional
            WHERE quarter=?
            GROUP BY ticker
            HAVING count(DISTINCT fund) >= 2
        """, (q,))
        self.conn.commit()

    def is_consensus_pick(self, ticker, min_funds=3):
        """Quick check: is this ticker held by N+ funds?"""
        names = [ticker]
        if ticker in TICKER_COMPANY:
            names.append(TICKER_COMPANY[ticker])
        if ticker in COMPANY_TICKER:
            names.append(COMPANY_TICKER[ticker])
        placeholders = ",".join("?" * len(names))
        row = self.conn.execute(f"""
            SELECT fund_count, funds FROM consensus
            WHERE ticker IN ({placeholders})
              AND quarter=(SELECT max(quarter) FROM consensus)
            ORDER BY fund_count DESC LIMIT 1
        """, tuple(names)).fetchone()
        if row and row["fund_count"] >= min_funds:
            return True, row["fund_count"], row["funds"]
        return False, 0, ""

    # ------------------------------------------------------------------
    # Sector performance
    # ------------------------------------------------------------------
    def save_sector_performance(self, date, sector, etf_ticker=None,
                                 price=None, change_1w=None, change_1m=None,
                                 rsi=None, rank=None):
        self.conn.execute("""
            INSERT OR REPLACE INTO sector_performance
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (date, sector, etf_ticker, price, change_1w, change_1m, rsi, rank))
        self.conn.commit()

    def get_sector_rankings(self, date=None):
        d = date or self.conn.execute(
            "SELECT max(date) as d FROM sector_performance"
        ).fetchone()["d"]
        if not d:
            return []
        return self.conn.execute(
            "SELECT * FROM sector_performance WHERE date=? ORDER BY rank",
            (d,)
        ).fetchall()

    # ------------------------------------------------------------------
    # Improvements
    # ------------------------------------------------------------------
    def add_improvement(self, date, imp_type, category, finding, action=None,
                        priority=None, target_file=None, status='active',
                        source=None, meta=None):
        self.conn.execute("""
            INSERT INTO improvements (date, type, category, priority, finding,
                                      action, target_file, status, source, meta, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (date, imp_type, category, priority, finding, action, target_file,
              status, source, json.dumps(meta) if meta else None,
              datetime.now().isoformat()))
        self.conn.commit()

    def get_active_improvements(self):
        """Get all active improvements — replaces active_improvements.md."""
        return self.conn.execute("""
            SELECT * FROM improvements
            WHERE status = 'active'
            ORDER BY
                CASE priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
                date DESC
        """).fetchall()

    def get_improvements(self, imp_type=None, limit=50):
        """Get improvements history, optionally filtered by type."""
        if imp_type:
            return self.conn.execute(
                "SELECT * FROM improvements WHERE type=? ORDER BY date DESC LIMIT ?",
                (imp_type, limit)
            ).fetchall()
        return self.conn.execute(
            "SELECT * FROM improvements ORDER BY date DESC LIMIT ?",
            (limit,)
        ).fetchall()

    def clear_improvements(self, imp_type=None):
        """Delete previous active improvements of a type before re-generating.
        Keeps 'applied' rows for history. Deletes 'active' and 'obsolete' to prevent bloat."""
        if imp_type:
            self.conn.execute(
                "DELETE FROM improvements WHERE type=? AND status IN ('active', 'obsolete')",
                (imp_type,))
        else:
            self.conn.execute(
                "DELETE FROM improvements WHERE status IN ('active', 'obsolete')")
        self.conn.commit()

    def get_active_improvements_summary(self):
        """Get a formatted summary of active improvements for Phase 2 Strategy.
        Returns a string that replaces what active_improvements.md used to provide."""
        rows = self.get_active_improvements()
        if not rows:
            return "No active improvements."

        lines = []
        # Group by category
        by_cat = {}
        for r in rows:
            cat = r['category'] or 'general'
            by_cat.setdefault(cat, []).append(r)

        for cat, items in by_cat.items():
            lines.append(f"### {cat.replace('_', ' ').title()}")
            for item in items:
                prefix = f"[{item['priority']}] " if item['priority'] else ""
                lines.append(f"- {prefix}{item['finding']}")
                if item['action']:
                    lines.append(f"  Fix: {item['action']}")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Cross-cutting queries (the good stuff)
    # ------------------------------------------------------------------
    def portfolio_dashboard(self):
        """One-shot portfolio overview: holdings + current prices + P&L."""
        return self.conn.execute("""
            SELECT h.ticker, h.shares, h.cost_basis, h.asset_type, h.date_bought,
                   p.price as current_price,
                   round((p.price - h.cost_basis) / h.cost_basis * 100, 2) as pnl_pct,
                   round(h.shares * p.price, 2) as market_value,
                   round(h.shares * (p.price - h.cost_basis), 2) as pnl_dollar,
                   t.rsi, t.dma_50, t.dma_200
            FROM holdings h
            LEFT JOIN price_cache p ON h.ticker = p.ticker
                AND p.date = (SELECT max(date) FROM price_cache WHERE ticker=h.ticker)
            LEFT JOIN technicals_cache t ON h.ticker = t.ticker
                AND t.date = (SELECT max(date) FROM technicals_cache WHERE ticker=h.ticker)
            ORDER BY market_value DESC
        """).fetchall()

    def smart_money_check(self, ticker):
        """Full smart money signal for a ticker: institutional + insider + consensus."""
        result = {}

        # Institutional holders
        holders = self.ticker_held_by(ticker)
        result['institutional'] = [dict(r) for r in holders]
        result['fund_count'] = len(holders)

        # Consensus
        is_cons, count, funds = self.is_consensus_pick(ticker)
        result['is_consensus'] = is_cons
        result['consensus_funds'] = funds

        # Recent insider buys
        insider = self.get_insider_buys(ticker, days=90)
        result['insider_buys'] = [dict(r) for r in insider]
        result['insider_buy_count'] = len(insider)

        # Signal strength
        signals = []
        if count >= 3:
            signals.append(f"Held by {count} top funds")
        if len(insider) >= 2:
            signals.append(f"{len(insider)} insider buys in 90 days")
        elif len(insider) == 1:
            signals.append("1 insider buy in 90 days")

        result['signal_strength'] = 'STRONG' if len(signals) >= 2 else \
                                    'MODERATE' if len(signals) == 1 else 'WEAK'
        result['signals'] = signals
        return result

    def watchlist_performance(self):
        """How are watchlist picks performing since recommendation?"""
        return self.conn.execute("""
            SELECT w.date, w.ticker, w.price_at_rec, w.conviction, w.status, w.notes,
                   p.price as current_price,
                   CASE WHEN w.price_at_rec > 0 AND p.price IS NOT NULL
                        THEN round((p.price - w.price_at_rec) / w.price_at_rec * 100, 2)
                        ELSE NULL END as return_pct
            FROM watchlist w
            LEFT JOIN price_cache p ON w.ticker = p.ticker
                AND p.date = (SELECT max(date) FROM price_cache WHERE ticker=w.ticker)
            WHERE w.status = 'ACTIVE'
            ORDER BY w.date DESC
        """).fetchall()

    def risk_dashboard(self):
        """Portfolio risk metrics in one query."""
        holdings = self.portfolio_dashboard()
        if not holdings:
            return {}

        total_value = sum(r["market_value"] or 0 for r in holdings)
        total_cost = sum(r["shares"] * r["cost_basis"] for r in holdings)

        concentrations = []
        for h in holdings:
            mv = h["market_value"] or 0
            pct = (mv / total_value * 100) if total_value > 0 else 0
            concentrations.append({
                'ticker': h["ticker"],
                'pct': round(pct, 1),
                'over_limit': pct > 15
            })

        drawdown = round((total_value - total_cost) / total_cost * 100, 2) if total_cost > 0 else 0

        return {
            'total_value': round(total_value, 2),
            'total_cost': round(total_cost, 2),
            'drawdown_pct': drawdown,
            'circuit_breaker': drawdown <= -15,
            'position_count': len(holdings),
            'concentrations': sorted(concentrations, key=lambda x: x['pct'], reverse=True),
            'over_concentrated': [c for c in concentrations if c['over_limit']],
        }


# ---------------------------------------------------------------------------
# Migration: import existing CSVs and data into DB
# ---------------------------------------------------------------------------

def migrate_all():
    """One-time migration of all existing data into the database."""
    print("Migrating existing data to vault.db...")

    with VaultDB() as db:
        count = _migrate_performance_log(db)
        print(f"  Trades: {count} rows")

        count = _migrate_watchlist(db)
        print(f"  Watchlist: {count} rows")

        count = _migrate_benchmarks(db)
        print(f"  Benchmarks: {count} rows")

        count = _migrate_screener(db)
        print(f"  Screener: {count} rows")

        count = _migrate_theses(db)
        print(f"  Theses: {count} rows")

        count = _migrate_institutional(db)
        print(f"  Institutional: {count} rows")

        count = db.sync_holdings_from_portfolio()
        print(f"  Holdings: {count} synced from portfolio.md")

        count = _migrate_reports(db)
        print(f"  Reports: {count} indexed")

    print(f"\nDatabase ready: {DB_PATH}")
    print(f"Size: {os.path.getsize(DB_PATH) / 1024:.1f} KB")


def _migrate_performance_log(db):
    path = os.path.join(SCRIPT_DIR, "performance_log.csv")
    if not os.path.exists(path):
        return 0
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            entry = None
            try:
                entry = float(row.get("entry", "")) if row.get("entry") else None
            except ValueError:
                pass
            db.add_trade(
                date=row.get("date", ""),
                ticker=row.get("ticker", ""),
                action=row.get("action", "BUY"),
                entry_price=entry,
                target=row.get("target"),
                conviction=row.get("conviction"),
                status=row.get("status", "OPEN"),
                report=row.get("report"),
                notes=row.get("notes"),
            )
            count += 1
    return count


def _migrate_watchlist(db):
    path = os.path.join(SCRIPT_DIR, "watchlist_log.csv")
    if not os.path.exists(path):
        return 0
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            price = None
            try:
                price = float(row.get("price_at_rec", "")) if row.get("price_at_rec") else None
            except ValueError:
                pass
            db.add_watchlist(
                date=row.get("date", ""),
                ticker=row.get("ticker", ""),
                price_at_rec=price,
                conviction=row.get("conviction"),
                report=row.get("report"),
                notes=row.get("notes"),
            )
            # Update status if not ACTIVE
            status = row.get("status", "ACTIVE")
            if status != "ACTIVE":
                db.update_watchlist_status(row["ticker"], status, row.get("date"))
            count += 1
    return count


def _migrate_benchmarks(db):
    path = os.path.join(SCRIPT_DIR, "benchmark_log.csv")
    if not os.path.exists(path):
        return 0
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                db.add_benchmark(
                    date=row["date"],
                    portfolio_value=float(row.get("portfolio_value", 0)),
                    portfolio_pct=float(row.get("portfolio_pct", 0)),
                    voo_price=float(row.get("voo_price", 0)),
                    voo_pct=float(row.get("voo_pct", 0)),
                    alpha=float(row.get("alpha", "0").replace("+", "")),
                )
                count += 1
            except (ValueError, KeyError):
                pass
    return count


def _migrate_screener(db):
    path = os.path.join(SCRIPT_DIR, "screener_output.csv")
    if not os.path.exists(path):
        return 0
    results = []
    run_id = None
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            run_id = run_id or row.get("date", "unknown")
            try:
                results.append({
                    'ticker': row.get("ticker", ""),
                    'price': float(row["price"]) if row.get("price") else None,
                    'rsi': float(row["rsi"]) if row.get("rsi") else None,
                    'dma_50': float(row["dma_50"]) if row.get("dma_50") else None,
                    'dma_200': float(row["dma_200"]) if row.get("dma_200") else None,
                    'high_52w': float(row["high_52w"]) if row.get("high_52w") else None,
                    'low_52w': float(row["low_52w"]) if row.get("low_52w") else None,
                    'volume_ratio': float(row["volume_ratio"]) if row.get("volume_ratio") else None,
                    'earnings_date': row.get("earnings_date"),
                    'signals': row.get("signals", ""),
                    'score': int(row["score"]) if row.get("score") else None,
                })
            except (ValueError, KeyError):
                pass
    if results:
        db.save_screener_run(results, run_id=run_id)
    return len(results)


def _migrate_theses(db):
    path = os.path.join(SCRIPT_DIR, "thesis_log.json")
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8") as f:
        theses = json.load(f)
    count = 0
    for t in theses:
        added = db.add_thesis(
            ticker=t.get("ticker", ""),
            direction=t.get("direction", "BUY"),
            conviction=t.get("conviction"),
            thesis=t.get("thesis"),
            key_conditions=t.get("key_conditions"),
            date_opened=t.get("date_opened"),
            source_report=None,
        )
        if added:
            count += 1
    return count


def _migrate_institutional(db):
    """Import institutional data from learn_from_pros report."""
    research_dir = os.path.join(PROJECT_ROOT, "research")
    improvements_dir = os.path.join(PROJECT_ROOT, "improvements")
    count = 0

    # Parse the learn_from_pros report
    for d in [research_dir, improvements_dir]:
        if not os.path.isdir(d):
            continue
        import glob as g
        for fpath in g.glob(os.path.join(d, "*institutional*")) + \
                      g.glob(os.path.join(d, "learn_from_pros*")):
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
            count += _parse_institutional_md(db, text)
    return count


def _parse_institutional_md(db, text):
    """Extract fund holdings from markdown institutional report."""
    import re
    count = 0
    current_fund = None
    quarter = "Q4-2025"

    lines = text.split("\n")
    for i, line in enumerate(lines):
        # Detect fund headers
        if line.startswith("### ") and not line.startswith("### Consensus") and \
           not line.startswith("### Cluster") and not line.startswith("### Key"):
            fund_name = line.replace("### ", "").strip()
            current_fund = fund_name
            continue

        if not current_fund:
            continue

        # Parse portfolio value
        pv_match = re.search(r'\*\*Portfolio[:\s]*\*\*\s*\$?([\d,.]+)([BM])', line)
        if pv_match:
            val = float(pv_match.group(1).replace(",", ""))
            if pv_match.group(2) == "B":
                val *= 1000  # store in millions
            # Extract other fund-level data
            positions = None
            top5 = None
            top10 = None
            filing = None
            for j in range(max(0, i-3), min(len(lines), i+10)):
                pm = re.search(r'(\d+)\s*positions', lines[j])
                if pm:
                    positions = int(pm.group(1))
                t5m = re.search(r'Top\s*5.*?(\d+\.?\d*)%', lines[j])
                if t5m:
                    top5 = float(t5m.group(1))
                t10m = re.search(r'Top\s*10.*?(\d+\.?\d*)%', lines[j])
                if t10m:
                    top10 = float(t10m.group(1))
                fm = re.search(r'[Ff]iling.*?(\d{4}-\d{2}-\d{2})', lines[j])
                if fm:
                    filing = fm.group(1)
            db.add_fund(current_fund, quarter, val, positions, top5, top10, filing)

        # Parse top holdings lines like "- TICKER NAME: X.X%"
        holding_match = re.search(r'[-*]\s+(.+?):\s*(\d+\.?\d*)%', line)
        if holding_match and current_fund:
            name = holding_match.group(1).strip()
            pct = float(holding_match.group(2))
            # Try to extract ticker from name
            ticker = name.upper().replace(" ", "_")  # fallback
            db.add_institutional(
                fund=current_fund,
                ticker=name,
                company_name=name,
                pct_portfolio=pct,
                quarter=quarter,
            )
            count += 1

        # Parse table rows like "| GOOGL | Pershing, Appaloosa... | 5 |"
        table_match = re.match(r'\|\s*([A-Z]{1,5})\s*\|', line)
        if table_match:
            ticker = table_match.group(1)
            # Extract fund names
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if len(cells) >= 3:
                fund_names = cells[1] if len(cells) > 1 else ""
                fund_count_str = cells[2] if len(cells) > 2 else ""

    return count


def _migrate_reports(db):
    """Index all report files."""
    import glob as g
    reports_dir = os.path.join(PROJECT_ROOT, "reports")
    count = 0
    for fpath in g.glob(os.path.join(reports_dir, "report_*.md")):
        fname = os.path.basename(fpath)
        # Extract date from filename
        import re
        dm = re.search(r'report_(\d{4}-\d{2}-\d{2})', fname)
        if dm:
            db.add_report(
                filename=fname,
                date=dm.group(1),
                report_type='full',
                path=fpath,
            )
            count += 1
    return count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        migrate_all()
    elif len(sys.argv) > 1 and sys.argv[1] == "export":
        with VaultDB() as db:
            exported = db.export_tables()
            print("\nExported tables to exports/:")
            for name, count, path in exported:
                print(f"  {name}: {count} rows -> {os.path.basename(path)}")
            print()
    elif len(sys.argv) > 1 and sys.argv[1] == "dashboard":
        with VaultDB() as db:
            print("\n=== Portfolio Dashboard ===\n")
            for row in db.portfolio_dashboard():
                print(f"  {row['ticker']:6s}  {row['shares']:8.4f} × ${row['cost_basis']:.2f}"
                      f"  → ${row['current_price'] or 0:.2f}  ({row['pnl_pct'] or 0:+.1f}%)"
                      f"  RSI: {row['rsi'] or '-':>5}")
            print()
            risk = db.risk_dashboard()
            if risk:
                print(f"  Total value: ${risk['total_value']:,.2f}")
                print(f"  Total cost:  ${risk['total_cost']:,.2f}")
                print(f"  Drawdown:    {risk['drawdown_pct']:+.2f}%")
                if risk['circuit_breaker']:
                    print(f"  ⚠ CIRCUIT BREAKER TRIGGERED")
                print(f"  Positions:   {risk['position_count']}")
                if risk['over_concentrated']:
                    print(f"  Over-concentrated: {', '.join(c['ticker'] for c in risk['over_concentrated'])}")
    elif len(sys.argv) > 1 and sys.argv[1] == "consensus":
        with VaultDB() as db:
            print("\n=== Consensus Holdings ===\n")
            for row in db.get_consensus(min_funds=2):
                print(f"  {row['ticker']:30s}  {row['fund_count']} funds  ({row['funds']})")
    elif len(sys.argv) > 1 and sys.argv[1] == "smart-money":
        ticker = sys.argv[2] if len(sys.argv) > 2 else None
        if not ticker:
            print("Usage: python3 db.py smart-money TICKER")
        else:
            with VaultDB() as db:
                result = db.smart_money_check(ticker)
                print(f"\n=== Smart Money: {ticker} ===")
                print(f"  Signal: {result['signal_strength']}")
                for s in result['signals']:
                    print(f"    → {s}")
                if result['institutional']:
                    print(f"  Held by {result['fund_count']} funds:")
                    for h in result['institutional']:
                        print(f"    {h['fund']}: {h['pct_portfolio']:.1f}%")
    else:
        print("Vault Research Desk — Database")
        print()
        print("Commands:")
        print("  python3 tools/db.py migrate      — Import existing CSV/JSON data")
        print("  python3 tools/db.py export        — Dump tables to exports/ as CSV")
        print("  python3 tools/db.py dashboard     — Portfolio overview")
        print("  python3 tools/db.py consensus     — Institutional consensus")
        print("  python3 tools/db.py smart-money TICKER — Smart money check")
        print()
        print(f"DB path: {DB_PATH}")
        if os.path.exists(DB_PATH):
            print(f"DB size: {os.path.getsize(DB_PATH) / 1024:.1f} KB")
