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

-- Smart money learnings (from learn_from_pros real analysis)
CREATE TABLE IF NOT EXISTS learnings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date    TEXT NOT NULL,
    category    TEXT NOT NULL,              -- 'portfolio_signal', 'new_candidate', 'change_detected',
                                           -- 'risk_flag', 'missed_opportunity'
    ticker      TEXT,                       -- NULL for portfolio-wide learnings
    signal_type TEXT,                       -- '13f', 'ark', 'insider', 'guru', 'analyst', 'cross_source'
    direction   TEXT,                       -- 'BULLISH', 'BEARISH', 'NEUTRAL', 'MIXED'
    strength    TEXT,                       -- 'STRONG', 'MODERATE', 'WEAK'
    detail      TEXT NOT NULL,              -- Human-readable finding
    data        TEXT,                       -- JSON blob with structured data
    relevance   TEXT,                       -- 'HOLDING', 'WATCHLIST', 'NEW_CANDIDATE', 'PORTFOLIO_WIDE'
    consumed    INTEGER DEFAULT 0,          -- 1 after report generator reads it
    created_at  TEXT NOT NULL
);

-- Performance indices (query acceleration)
CREATE INDEX IF NOT EXISTS idx_insider_ticker_date ON insider_txns(ticker, txn_date);
CREATE INDEX IF NOT EXISTS idx_insider_ticker_type ON insider_txns(ticker, txn_type);
CREATE INDEX IF NOT EXISTS idx_ark_ticker ON ark_trades(ticker);
CREATE INDEX IF NOT EXISTS idx_ark_date ON ark_trades(date);
CREATE INDEX IF NOT EXISTS idx_guru_ticker ON guru_holdings(ticker);
CREATE INDEX IF NOT EXISTS idx_guru_code ON guru_holdings(guru_code);
CREATE INDEX IF NOT EXISTS idx_news_ticker ON news(ticker);
CREATE INDEX IF NOT EXISTS idx_news_published ON news(published);
CREATE INDEX IF NOT EXISTS idx_learnings_ticker ON learnings(ticker);
CREATE INDEX IF NOT EXISTS idx_learnings_category ON learnings(category);
CREATE INDEX IF NOT EXISTS idx_improvements_status ON improvements(status);
CREATE INDEX IF NOT EXISTS idx_theses_ticker ON theses(ticker);
CREATE INDEX IF NOT EXISTS idx_theses_status ON theses(status);
CREATE INDEX IF NOT EXISTS idx_watchlist_ticker ON watchlist(ticker);
CREATE INDEX IF NOT EXISTS idx_watchlist_status ON watchlist(status);
CREATE INDEX IF NOT EXISTS idx_trades_ticker ON trades(ticker);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_institutional_ticker ON institutional(ticker);
CREATE INDEX IF NOT EXISTS idx_consensus_ticker ON consensus(ticker);

-- Portfolio settings (DB-first, exported to portfolio.md)
CREATE TABLE IF NOT EXISTS settings (
    key          TEXT PRIMARY KEY,
    value        TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- Scorecard snapshots (track system performance over time)
CREATE TABLE IF NOT EXISTS scorecards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    total_trades    INTEGER,
    open_trades     INTEGER,
    closed_trades   INTEGER,
    win_rate        REAL,                   -- 0-100%
    avg_return      REAL,                   -- portfolio avg return %
    best_ticker     TEXT,
    best_return     REAL,
    worst_ticker    TEXT,
    worst_return    REAL,
    avg_holding_days REAL,
    voo_avg         REAL,                   -- VOO same-period avg return %
    alpha           REAL,                   -- portfolio avg - VOO avg
    verdict         TEXT,                   -- 'Outperforming', 'Underperforming', 'Too early'
    created_at      TEXT NOT NULL
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

    # Sector map for auto-detection
    SECTOR_MAP = {
        "XLK": "Technology", "XLC": "Communication", "XLV": "Healthcare",
        "XLE": "Energy", "XLF": "Financials", "XLY": "Cons Discretionary",
        "XLP": "Cons Staples", "XLI": "Industrials", "XLB": "Materials",
        "XLRE": "Real Estate", "XLU": "Utilities", "GLD": "Commodities",
        "SLV": "Commodities", "VOO": "Broad Market", "SPY": "Broad Market",
        "QQQ": "Technology", "IWM": "Broad Market",
        "GOOGL": "Technology", "GOOG": "Technology", "AAPL": "Technology",
        "MSFT": "Technology", "AMZN": "Cons Discretionary", "META": "Technology",
        "NVDA": "Technology", "TSLA": "Cons Discretionary", "NFLX": "Communication",
        "XOM": "Energy", "CVX": "Energy", "LMT": "Industrials",
        "JPM": "Financials", "BAC": "Financials", "CFG": "Financials",
        "JNJ": "Healthcare", "UNH": "Healthcare", "PFE": "Healthcare",
    }

    ETFS = {"XLE", "XLV", "XLK", "XLF", "XLY", "XLP", "XLI", "XLB",
            "XLRE", "XLU", "XLC", "GLD", "SLV", "VOO", "SPY", "QQQ", "IWM"}

    def get_sector(self, ticker):
        """Get sector for a ticker."""
        return self.SECTOR_MAP.get(ticker)

    # ------------------------------------------------------------------
    # Settings (DB-first)
    # ------------------------------------------------------------------
    def get_setting(self, key, default=None):
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row['value'] if row else default

    def set_setting(self, key, value):
        self.conn.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """, (key, str(value), datetime.now().isoformat()))
        self.conn.commit()

    def get_all_settings(self):
        rows = self.conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
        return {r['key']: r['value'] for r in rows}

    def get_cash(self):
        return float(self.get_setting('cash_available', '0'))

    def set_cash(self, amount):
        self.set_setting('cash_available', str(amount))

    # ------------------------------------------------------------------
    # Portfolio sync (DB is master → portfolio.md is export)
    # ------------------------------------------------------------------
    def sync_holdings_from_portfolio(self):
        """One-time import: read portfolio.md into DB. After this, DB is master."""
        import sys
        sys.path.insert(0, SCRIPT_DIR)
        from data_fetcher import read_portfolio
        tickers, holdings, settings = read_portfolio()

        for ticker in tickers:
            h = holdings.get(ticker, {})
            sector = self.SECTOR_MAP.get(ticker)
            self.upsert_holding(
                ticker=ticker,
                shares=h.get("shares", 0),
                cost_basis=h.get("cost", 0),
                date_bought=h.get("date"),
                sector=sector,
                asset_type="etf" if ticker in self.ETFS else "stock"
            )

        # Sync settings
        setting_map = {
            'risk_tolerance': settings.get('risk_tolerance', 'moderate'),
            'monthly_investment': settings.get('monthly_investment', '4500'),
            'cash_available': settings.get('cash_available', '0'),
            'name': settings.get('name', ''),
            'location': settings.get('location', ''),
            'broker': settings.get('broker', ''),
            'experience': settings.get('experience', ''),
            'preference': settings.get('preference', ''),
            'start_date': settings.get('start_date', ''),
        }
        for k, v in setting_map.items():
            if v:
                self.set_setting(k, v)

        return len(tickers)

    def export_portfolio_md(self):
        """Export DB holdings + settings to portfolio.md (DB → file)."""
        holdings = self.get_holdings()
        settings = self.get_all_settings()

        lines = []
        lines.append("## Holdings\n")
        lines.append("| Ticker | Shares | Avg Cost | Date Bought |\n")
        lines.append("|--------|--------|----------|-------------|\n")
        for h in holdings:
            date_str = h['date_bought'] or ''
            lines.append(f"| {h['ticker']}  | {h['shares']:.4f} | ${h['cost_basis']:.0f}     | {date_str}  |\n")
        lines.append("\n")

        lines.append("## Settings\n")
        lines.append(f"Risk tolerance: {settings.get('risk_tolerance', 'moderate')}\n")
        lines.append(f"Monthly investment: ${float(settings.get('monthly_investment', 4500)):,.0f}\n")
        lines.append(f"Cash available: ${float(settings.get('cash_available', 0)):,.0f}\n")
        lines.append("\n")

        lines.append("## Profile\n")
        for key in ['name', 'location', 'broker', 'experience', 'preference', 'start_date']:
            val = settings.get(key, '')
            if val:
                label = key.replace('_', ' ').title()
                if key == 'start_date':
                    label = 'Start date'
                lines.append(f"{label}: {val}\n")
        lines.append("\n")

        lines.append("## Notes\n")
        lines.append("- This file is auto-generated from vault.db\n")
        lines.append("- To update: tell Claude or use `vault portfolio` commands\n")
        lines.append("- DB is the source of truth, this file is an export\n")

        filepath = os.path.join(PROJECT_ROOT, "portfolio.md")
        with open(filepath, 'w') as f:
            f.writelines(lines)

        return len(holdings)

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
    # Learnings (from learn_from_pros real analysis)
    # ------------------------------------------------------------------
    def add_learning(self, run_date, category, detail, ticker=None, signal_type=None,
                     direction=None, strength=None, data=None, relevance=None):
        """Insert a single learning from the learning engine."""
        self.conn.execute("""
            INSERT INTO learnings
            (run_date, category, ticker, signal_type, direction, strength,
             detail, data, relevance, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (run_date, category, ticker, signal_type, direction, strength,
              detail, json.dumps(data) if data else None, relevance,
              datetime.now().isoformat()))
        self.conn.commit()

    def clear_learnings(self, run_date=None):
        """Clear learnings for a specific run date, or all unconsumed."""
        if run_date:
            self.conn.execute("DELETE FROM learnings WHERE run_date=?", (run_date,))
        else:
            self.conn.execute("DELETE FROM learnings WHERE consumed=0")
        self.conn.commit()

    def get_unconsumed_learnings(self, limit=50):
        """Get learnings not yet consumed by report generator."""
        return self.conn.execute("""
            SELECT * FROM learnings WHERE consumed=0
            ORDER BY
                CASE strength WHEN 'STRONG' THEN 1 WHEN 'MODERATE' THEN 2 ELSE 3 END,
                CASE category
                    WHEN 'risk_flag' THEN 1
                    WHEN 'portfolio_signal' THEN 2
                    WHEN 'change_detected' THEN 3
                    WHEN 'new_candidate' THEN 4
                    ELSE 5 END,
                created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()

    def get_learnings_for_ticker(self, ticker):
        """Get all unconsumed learnings for a specific ticker."""
        return self.conn.execute("""
            SELECT * FROM learnings
            WHERE ticker=? AND consumed=0
            ORDER BY
                CASE strength WHEN 'STRONG' THEN 1 WHEN 'MODERATE' THEN 2 ELSE 3 END,
                created_at DESC
        """, (ticker,)).fetchall()

    def mark_learnings_consumed(self, learning_ids=None):
        """Mark learnings as consumed after report generation."""
        if learning_ids:
            placeholders = ",".join("?" * len(learning_ids))
            self.conn.execute(
                f"UPDATE learnings SET consumed=1 WHERE id IN ({placeholders})",
                tuple(learning_ids))
        else:
            self.conn.execute("UPDATE learnings SET consumed=1 WHERE consumed=0")
        self.conn.commit()

    def get_learnings_summary(self):
        """Formatted summary for report consumption.
        Returns a string with portfolio-specific smart money insights."""
        rows = self.get_unconsumed_learnings(limit=50)
        if not rows:
            return "No new smart money learnings available. Run: python3 tools/learn_from_pros.py"

        lines = []
        run_dates = set(r['run_date'] for r in rows)
        latest = max(run_dates) if run_dates else "unknown"
        lines.append(f"=== SMART MONEY LEARNINGS ({latest}) ===\n")

        # Group by category
        cats = {}
        for r in rows:
            cats.setdefault(r['category'], []).append(r)

        # Risk flags first
        if 'risk_flag' in cats:
            lines.append("**RISK FLAGS:**")
            for r in cats['risk_flag']:
                tag = f"[{r['strength']}]" if r['strength'] else ""
                lines.append(f"- {r['ticker'] or 'PORTFOLIO'} {tag}: {r['detail']}")
            lines.append("")

        # Portfolio signals
        if 'portfolio_signal' in cats:
            lines.append("**PORTFOLIO SIGNALS (your holdings):**")
            for r in cats['portfolio_signal']:
                tag = f"[{r['strength']} {r['direction']}]" if r['strength'] else ""
                lines.append(f"- {r['ticker']} {tag}: {r['detail']}")
            lines.append("")

        # Changes detected
        if 'change_detected' in cats:
            lines.append("**CHANGES SINCE LAST RUN:**")
            for r in cats['change_detected']:
                lines.append(f"- {r['ticker'] or 'MARKET'}: {r['detail']}")
            lines.append("")

        # New candidates
        if 'new_candidate' in cats:
            lines.append("**NEW CANDIDATES (strong signals, not in portfolio):**")
            for r in cats['new_candidate']:
                tag = f"[{r['strength']}]" if r['strength'] else ""
                lines.append(f"- {r['ticker']} {tag}: {r['detail']}")
            lines.append("")

        # Missed opportunities
        if 'missed_opportunity' in cats:
            lines.append("**MISSED OPPORTUNITIES (hindsight):**")
            for r in cats['missed_opportunity']:
                lines.append(f"- {r['ticker']}: {r['detail']}")
            lines.append("")

        return "\n".join(lines)

    def get_learning_history(self, days=90):
        """Get learnings over time for trend analysis."""
        cutoff = (datetime.now() - __import__('datetime').timedelta(days=days)).strftime('%Y-%m-%d')
        return self.conn.execute("""
            SELECT * FROM learnings WHERE run_date >= ?
            ORDER BY run_date DESC, created_at DESC
        """, (cutoff,)).fetchall()

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
    # ------------------------------------------------------------------
    # Scorecards (performance tracking over time)
    # ------------------------------------------------------------------
    def save_scorecard(self, total_trades, open_trades, closed_trades,
                       win_rate, avg_return, best_ticker, best_return,
                       worst_ticker, worst_return, avg_holding_days,
                       voo_avg, alpha, verdict):
        """Save a scorecard snapshot for performance trending."""
        today = datetime.now().strftime("%Y-%m-%d")
        # Upsert: only one snapshot per day
        self.conn.execute("DELETE FROM scorecards WHERE date=?", (today,))
        self.conn.execute("""
            INSERT INTO scorecards
            (date, total_trades, open_trades, closed_trades, win_rate,
             avg_return, best_ticker, best_return, worst_ticker, worst_return,
             avg_holding_days, voo_avg, alpha, verdict, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (today, total_trades, open_trades, closed_trades, win_rate,
              avg_return, best_ticker, best_return, worst_ticker, worst_return,
              avg_holding_days, voo_avg, alpha, verdict,
              datetime.now().isoformat()))
        self.conn.commit()

    def get_scorecard_history(self, limit=12):
        """Get scorecard history for performance trending."""
        return self.conn.execute("""
            SELECT * FROM scorecards ORDER BY date DESC LIMIT ?
        """, (limit,)).fetchall()

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

    def _generate_action_items(self):
        """Synthesize all signals into specific action items."""
        actions = []

        # 1. Concentration warnings
        risk = self.risk_dashboard()
        if risk:
            over = risk.get('over_concentrated', [])
            worst = max(over, key=lambda c: c['pct']) if over else None
            if worst and worst['pct'] > 30:
                actions.append(f"TRIM {worst['ticker']} — {worst['pct']:.0f}% allocation (limit: 15%)")
            elif worst and worst['pct'] > 15:
                actions.append(f"Consider trimming {worst['ticker']} ({worst['pct']:.0f}% vs 15% limit)")

            # Circuit breaker
            if risk.get('circuit_breaker'):
                actions.insert(0, "CIRCUIT BREAKER — portfolio down >15%, raise cash to 30%+")

        # 2. Data freshness
        latest = self.conn.execute(
            "SELECT max(fetched_at) as latest FROM price_cache"
        ).fetchone()
        if latest and latest['latest']:
            fetched = datetime.fromisoformat(latest['latest'])
            age_hours = (datetime.now() - fetched).total_seconds() / 3600
            if age_hours > 48:
                actions.append(f"Run `vault fetch` — data is {age_hours:.0f}h stale")

        # 3. Report freshness
        last_report = self.conn.execute(
            "SELECT date FROM reports ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if last_report:
            days_since = (datetime.now().date() - datetime.strptime(
                last_report['date'], '%Y-%m-%d').date()).days
            if days_since >= 7:
                actions.append(f"Run `report` — last report was {days_since} days ago")

        # 4. Strong smart money signals on holdings
        holdings = self.get_holdings()
        port_tickers = {h['ticker'] for h in holdings}
        strong_learnings = self.conn.execute("""
            SELECT ticker, detail FROM learnings
            WHERE consumed=0 AND strength='STRONG' AND ticker IS NOT NULL
            ORDER BY created_at DESC
        """).fetchall()
        for l in strong_learnings[:3]:
            if l['ticker'] in port_tickers:
                actions.append(f"Review {l['ticker']} — {l['detail'][:50]}")
                break  # Only one holding signal

        # 5. Profit-taking thresholds on holdings (batch price fetch)
        dashboard = self.portfolio_dashboard()
        for h in dashboard:
            ticker = h['ticker']
            current = h['current_price'] or 0
            entry_per_share = h['cost_basis'] or 0
            if current > 0 and entry_per_share > 0:
                gain_pct = (current - entry_per_share) / entry_per_share * 100
                if gain_pct >= 100:
                    actions.append(f"PROFIT-TAKE {ticker} — up {gain_pct:+.0f}%, sell half (house money rule)")
                elif gain_pct >= 50:
                    actions.append(f"PROFIT-TAKE {ticker} — up {gain_pct:+.0f}%, trim 25% more (50% rule)")
                elif gain_pct >= 30:
                    actions.append(f"PROFIT-TAKE {ticker} — up {gain_pct:+.0f}%, trim 25% (30% rule)")

        # 6. Insider cluster buys (strong signal)
        clusters = self.get_cluster_buys(days=60, min_insiders=2)
        for c in clusters[:2]:
            t = c['ticker']
            if t in port_tickers:
                actions.append(f"Insider cluster BUY in {t} — {c['num_insiders']} insiders bought recently")
            else:
                actions.append(f"Watch {t} — insider cluster buying ({c['num_insiders']} insiders)")

        # 7. Stale theses
        stale_count = self.conn.execute("""
            SELECT count(*) as c FROM theses
            WHERE status='ACTIVE'
              AND julianday('now') - julianday(date_opened) > 90
        """).fetchone()
        if stale_count and stale_count['c'] > 0:
            actions.append(f"Review {stale_count['c']} stale theses (>90 days old)")

        # 8. Under-diversified
        if risk and risk.get('position_count', 0) < 6:
            actions.append(f"Only {risk['position_count']} positions — target is 6-8 for diversification")

        # 9. VIX warning
        snap = self.conn.execute(
            "SELECT vix FROM market_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if snap and snap['vix'] and snap['vix'] > 30:
            actions.append(f"VIX at {snap['vix']:.0f} — elevated fear, be cautious with new buys")

        # 10. Watchlist picks with strong smart money support
        for l in strong_learnings[:5]:
            if l['ticker'] and l['ticker'] not in port_tickers:
                watchlist = self.conn.execute(
                    "SELECT ticker FROM watchlist WHERE ticker=? AND status='ACTIVE'",
                    (l['ticker'],)
                ).fetchone()
                if watchlist:
                    actions.append(f"Watchlist {l['ticker']} has smart money support — {l['detail'][:40]}")
                    break

        return actions

    def get_thesis_relevant_news(self, days=3):
        """Find recent news that may impact active theses."""
        theses = self.get_active_theses()
        thesis_tickers = {t['ticker'] for t in theses}
        if not thesis_tickers:
            return []

        results = []
        news = self.conn.execute("""
            SELECT ticker, headline, sentiment, published
            FROM news
            WHERE published >= date('now', ?)
            ORDER BY published DESC
        """, (f'-{days} days',)).fetchall()

        for n in news:
            if n['ticker'] in thesis_tickers:
                thesis = next((t for t in theses if t['ticker'] == n['ticker']), None)
                if thesis:
                    sentiment = n['sentiment'] or 0
                    direction = thesis['direction'] if thesis['direction'] else 'BUY'
                    # Check if news contradicts thesis
                    contradicts = (direction in ('BUY', 'HOLD') and sentiment < -0.3) or \
                                  (direction in ('SELL', 'AVOID') and sentiment > 0.3)
                    results.append({
                        'ticker': n['ticker'],
                        'headline': n['headline'],
                        'sentiment': sentiment,
                        'thesis_direction': direction,
                        'contradicts': contradicts,
                        'published': n['published'],
                    })

        return results

    def generate_search_log(self, tickers):
        """Generate a Search Log table from cached price data for report inclusion.

        Returns a markdown-formatted Search Log string per 00_system.md requirements.
        Tickers should include all tickers that will appear in the report.
        """
        # Batch fetch all prices in one query
        placeholders = ",".join("?" * len(tickers))
        rows = self.conn.execute(f"""
            SELECT ticker, price, fetched_at FROM price_cache
            WHERE ticker IN ({placeholders})
            AND fetched_at = (
                SELECT max(fetched_at) FROM price_cache p2
                WHERE p2.ticker = price_cache.ticker
            )
        """, list(tickers)).fetchall()
        price_map = {r['ticker']: r for r in rows}

        lines = []
        lines.append("### Search Log")
        lines.append("")
        lines.append("| # | Ticker | Verified Price | Source | Date |")
        lines.append("|---|--------|---------------|--------|------|")

        for i, ticker in enumerate(sorted(tickers), 1):
            row = price_map.get(ticker)
            if row and row['price']:
                fetched = row['fetched_at'][:10]
                lines.append(f"| {i} | {ticker} | ${row['price']:.2f} | data_fetcher.py | {fetched} |")
            else:
                lines.append(f"| {i} | {ticker} | NOT VERIFIED | — | — |")

        lines.append("")
        return "\n".join(lines)

    def morning_briefing(self):
        """One-command morning overview: portfolio + risk + theses + watchlist + learnings."""
        now = datetime.now()
        lines = []

        lines.append("")
        lines.append(f"{'=' * 58}")
        lines.append(f"  MORNING BRIEFING — {now.strftime('%A, %B %d %Y  %H:%M')}")
        lines.append(f"{'=' * 58}")

        # ── Action Items (synthesized from all signals) ──
        actions = self._generate_action_items()
        if actions:
            lines.append("")
            lines.append(f"  ACTION ITEMS")
            lines.append(f"  {'─' * 52}")
            for i, action in enumerate(actions[:5], 1):
                lines.append(f"  {i}. {action}")

        # ── Market Snapshot ──
        snap = self.conn.execute(
            "SELECT * FROM market_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if snap:
            lines.append("")
            lines.append(f"  MARKET ({snap['date']})")
            lines.append(f"  {'─' * 52}")
            parts = []
            if snap['spy']:
                parts.append(f"S&P {snap['spy']:,.0f}")
            if snap['vix']:
                vix_warn = " !" if snap['vix'] > 25 else ""
                parts.append(f"VIX {snap['vix']:.1f}{vix_warn}")
            if snap['oil']:
                parts.append(f"Oil ${snap['oil']:.0f}")
            if snap['gold']:
                parts.append(f"Gold ${snap['gold']:,.0f}")
            if snap['dxy']:
                parts.append(f"DXY {snap['dxy']:.1f}")
            if snap['ten_year']:
                parts.append(f"10Y {snap['ten_year']:.2f}%")
            lines.append(f"  {' | '.join(parts)}")
            if snap['breadth_200']:
                b200 = snap['breadth_200']
                health = "Healthy" if b200 > 70 else "Weakening" if b200 > 40 else "Bear-like"
                lines.append(f"  Breadth: {b200:.0f}% above 200 DMA — {health}")

        # ── Portfolio ──
        holdings = self.portfolio_dashboard()
        risk = self.risk_dashboard()

        lines.append("")
        lines.append(f"  PORTFOLIO ({risk.get('position_count', 0)} positions)")
        lines.append(f"  {'─' * 52}")
        lines.append(f"  {'Ticker':<7} {'Shares':>8} {'Cost':>8} {'Price':>8} {'P&L':>8} {'Alloc':>6}")
        lines.append(f"  {'─' * 52}")

        concentrations = {c['ticker']: c['pct'] for c in risk.get('concentrations', [])}
        for h in holdings:
            pnl_str = f"{h['pnl_pct'] or 0:+.1f}%"
            alloc = concentrations.get(h['ticker'], 0)
            warn = " !" if alloc > 15 else ""
            lines.append(
                f"  {h['ticker']:<7} {h['shares']:>8.4f} "
                f"${h['cost_basis']:>6.0f} ${h['current_price'] or 0:>6.2f} "
                f"{pnl_str:>7} {alloc:>5.1f}%{warn}"
            )

        if risk:
            lines.append(f"  {'─' * 52}")
            lines.append(f"  Total: ${risk['total_value']:,.2f}  "
                         f"Cost: ${risk['total_cost']:,.2f}  "
                         f"P&L: {risk['drawdown_pct']:+.2f}%")
            if risk['circuit_breaker']:
                lines.append(f"  *** CIRCUIT BREAKER: Drawdown exceeds -15% ***")
            over = risk.get('over_concentrated', [])
            if over:
                names = ", ".join(f"{c['ticker']} ({c['pct']:.0f}%)" for c in over)
                lines.append(f"  Over-concentrated: {names}")

        # ── Benchmark ──
        bench = self.conn.execute(
            "SELECT * FROM benchmarks ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if bench:
            lines.append(f"  vs VOO: alpha {bench['alpha']:+.2f}%  "
                         f"(portfolio {bench['portfolio_pct']:+.2f}% | VOO {bench['voo_pct']:+.2f}%)")

        # ── Active Theses ──
        theses = self.get_active_theses()
        lines.append("")
        lines.append(f"  ACTIVE THESES ({len(theses)})")
        lines.append(f"  {'─' * 52}")
        if theses:
            for t in theses[:8]:
                age = (now.date() - datetime.strptime(t['date_opened'], '%Y-%m-%d').date()).days
                stale = " STALE" if age > 90 else ""
                direction = t['direction'] if 'direction' in t.keys() else '?'
                lines.append(f"  {t['ticker']:<7} {direction:<6} {age:>3}d  {t['thesis'][:35]}{stale}")
        else:
            lines.append("  No active theses. Run: thesis_tracker.py extract <report>")

        # ── Watchlist ──
        watchlist = self.watchlist_performance()
        lines.append("")
        lines.append(f"  WATCHLIST ({len(watchlist)} active picks)")
        lines.append(f"  {'─' * 52}")
        if watchlist:
            winners = 0
            losers = 0
            for w in watchlist[:6]:
                ret = w['return_pct']
                if ret is not None:
                    tag = f"{ret:+.1f}%"
                    if ret > 0:
                        winners += 1
                    else:
                        losers += 1
                else:
                    tag = "  n/a"
                conv = w['conviction'] if w['conviction'] else '?'
                lines.append(f"  {w['ticker']:<7} {conv:<8} rec'd ${w['price_at_rec'] or 0:>6.0f}  now {tag}")
            if len(watchlist) > 6:
                lines.append(f"  ... and {len(watchlist) - 6} more")
            lines.append(f"  Score: {winners}W / {losers}L")
        else:
            lines.append("  No active watchlist picks.")

        # ── Thesis-Relevant News ──
        thesis_news = self.get_thesis_relevant_news(days=3)
        contradictions = [n for n in thesis_news if n['contradicts']]
        if contradictions:
            lines.append("")
            lines.append(f"  NEWS ALERTS ({len(contradictions)} contradicting your theses)")
            lines.append(f"  {'─' * 52}")
            for n in contradictions[:3]:
                lines.append(f"  {n['ticker']:<7} vs {n['thesis_direction']}: {n['headline'][:42]}")

        # ── Smart Money Learnings ──
        learnings = self.get_unconsumed_learnings(limit=10)
        lines.append("")
        lines.append(f"  SMART MONEY LEARNINGS ({len(learnings)} new)")
        lines.append(f"  {'─' * 52}")
        if learnings:
            for l in learnings[:5]:
                strength = l['strength'] or ''
                ticker = l['ticker'] or 'PORTFOLIO'
                tag = f"[{strength}]" if strength else ""
                detail = l['detail'][:50]
                lines.append(f"  {ticker:<7} {tag:<10} {detail}")
            if len(learnings) > 5:
                lines.append(f"  ... and {len(learnings) - 5} more")
        else:
            lines.append("  No new learnings. Run: learn_from_pros.py")

        # ── Smart Money Divergence ──
        divergences = self.detect_smart_money_divergence()
        if divergences:
            lines.append("")
            lines.append(f"  CONTESTED THESES ({len(divergences)} tickers)")
            lines.append(f"  {'─' * 52}")
            for d in divergences[:4]:
                bull = ','.join(d['bullish_sources'])
                bear = ','.join(d['bearish_sources'])
                lines.append(f"  {d['ticker']:<7} Bull({bull}) vs Bear({bear})")

        # ── Regime ──
        regime = self.detect_regime()
        if regime['regime'] != 'UNKNOWN':
            lines.append("")
            lines.append(f"  REGIME: {regime['regime']} ({regime['confidence']}%) — {regime['posture']}")

        # ── Improvements (from self-analyze) ──
        improvements = self.get_active_improvements()
        high_priority = [i for i in improvements if i['priority'] == 'HIGH']
        if high_priority:
            lines.append("")
            lines.append(f"  ISSUES ({len(high_priority)} high priority)")
            lines.append(f"  {'─' * 52}")
            for imp in high_priority[:3]:
                lines.append(f"  [{imp['priority']}] {imp['finding'][:50]}")

        # ── Performance Trend ──
        scorecards = self.get_scorecard_history(limit=5)
        if scorecards:
            lines.append("")
            lines.append(f"  PERFORMANCE TREND (last {len(scorecards)} snapshots)")
            lines.append(f"  {'─' * 52}")
            lines.append(f"  {'Date':<12} {'Trades':>7} {'Win%':>6} {'Avg Ret':>8} {'Alpha':>7} {'Verdict'}")
            for sc in scorecards:
                wr = f"{sc['win_rate']:.0f}%" if sc['win_rate'] is not None else " n/a"
                ar = f"{sc['avg_return']:+.1f}%" if sc['avg_return'] is not None else "  n/a"
                al = f"{sc['alpha']:+.1f}%" if sc['alpha'] is not None else "  n/a"
                lines.append(f"  {sc['date']:<12} {sc['total_trades']:>7} {wr:>6} {ar:>8} {al:>7} {sc['verdict']}")

        # ── Footer ──
        lines.append("")
        lines.append(f"  {'─' * 52}")
        lines.append(f"  Commands: report | flash | score | alerts | learn-from-pros")
        lines.append(f"{'=' * 58}")
        lines.append("")

        return "\n".join(lines)

    def changes_since_last_report(self):
        """Show what changed since the last report was generated."""
        lines = []
        now = datetime.now()

        # Find last report date
        last_report = self.conn.execute("""
            SELECT date, filename FROM reports ORDER BY date DESC LIMIT 1
        """).fetchone()

        if not last_report:
            return "No reports found. Run `report` to generate your first one."

        report_date = last_report['date']
        days_since = (now.date() - datetime.strptime(report_date, '%Y-%m-%d').date()).days

        lines.append("")
        lines.append(f"{'=' * 58}")
        lines.append(f"  CHANGES SINCE LAST REPORT")
        lines.append(f"{'=' * 58}")
        lines.append(f"  Last report: {last_report['filename']} ({days_since} days ago)")
        lines.append("")

        # ── Price changes for holdings ──
        holdings = self.portfolio_dashboard()
        if holdings:
            lines.append(f"  HOLDING PRICE CHANGES")
            lines.append(f"  {'─' * 52}")

            for h in holdings:
                ticker = h['ticker']
                current = h['current_price'] or 0

                # Get price at or before report date from cache
                old_price_row = self.conn.execute("""
                    SELECT price FROM price_cache
                    WHERE ticker=? AND date<=?
                    ORDER BY date DESC
                    LIMIT 1
                """, (ticker, report_date)).fetchone()

                if old_price_row and old_price_row['price']:
                    old_price = old_price_row['price']
                    change_pct = (current - old_price) / old_price * 100
                    direction = "+" if change_pct >= 0 else ""
                    lines.append(f"  {ticker:<7} ${old_price:>7.2f} -> ${current:>7.2f}  ({direction}{change_pct:.1f}%)")
                else:
                    lines.append(f"  {ticker:<7} no data at report date -> ${current:>7.2f}")
            lines.append("")

        # ── Market changes ──
        old_snap = self.conn.execute(
            "SELECT * FROM market_snapshots WHERE date=?", (report_date,)
        ).fetchone()
        new_snap = self.conn.execute(
            "SELECT * FROM market_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()

        if old_snap and new_snap and old_snap['date'] != new_snap['date']:
            lines.append(f"  MARKET CHANGES")
            lines.append(f"  {'─' * 52}")
            macro_items = [
                ("S&P 500", old_snap['spy'], new_snap['spy']),
                ("VIX", old_snap['vix'], new_snap['vix']),
                ("Oil", old_snap['oil'], new_snap['oil']),
                ("Gold", old_snap['gold'], new_snap['gold']),
                ("DXY", old_snap['dxy'], new_snap['dxy']),
                ("10Y", old_snap['ten_year'], new_snap['ten_year']),
            ]
            for name, old_val, new_val in macro_items:
                if old_val and new_val:
                    chg = (new_val - old_val) / old_val * 100
                    direction = "+" if chg >= 0 else ""
                    lines.append(f"  {name:<10} {old_val:>8.2f} -> {new_val:>8.2f}  ({direction}{chg:.1f}%)")
            lines.append("")

        # ── New smart money learnings since report ──
        new_learnings = self.conn.execute("""
            SELECT * FROM learnings
            WHERE created_at > ? AND consumed=0
            ORDER BY
                CASE strength WHEN 'STRONG' THEN 1 WHEN 'MODERATE' THEN 2 ELSE 3 END
            LIMIT 10
        """, (report_date,)).fetchall()

        if new_learnings:
            lines.append(f"  NEW SMART MONEY SIGNALS ({len(new_learnings)})")
            lines.append(f"  {'─' * 52}")
            for l in new_learnings[:7]:
                strength = l['strength'] or ''
                ticker = l['ticker'] or 'PORTFOLIO'
                tag = f"[{strength}]" if strength else ""
                lines.append(f"  {ticker:<7} {tag:<10} {l['detail'][:45]}")
            if len(new_learnings) > 7:
                lines.append(f"  ... and {len(new_learnings) - 7} more")
            lines.append("")

        # ── New insider activity since report ──
        new_insider = self.conn.execute("""
            SELECT ticker, insider_name, txn_type, shares, value, txn_date
            FROM insider_txns
            WHERE txn_date > ? AND txn_type IN ('BUY', 'SELL')
            ORDER BY txn_date DESC
            LIMIT 10
        """, (report_date,)).fetchall()

        if new_insider:
            buys = [i for i in new_insider if i['txn_type'] == 'BUY']
            sells = [i for i in new_insider if i['txn_type'] == 'SELL']
            lines.append(f"  NEW INSIDER ACTIVITY ({len(buys)} buys, {len(sells)} sells)")
            lines.append(f"  {'─' * 52}")
            for i in new_insider[:5]:
                val = f"${i['value']:,.0f}" if i['value'] and i['value'] > 0 else ""
                lines.append(f"  {i['txn_date']}  {i['ticker']:<7} {i['txn_type']:<5} {val}")
            lines.append("")

        # ── Thesis age check ──
        stale = self.conn.execute("""
            SELECT ticker, thesis, date_opened,
                   julianday('now') - julianday(date_opened) as age_days
            FROM theses
            WHERE status='ACTIVE'
              AND julianday('now') - julianday(date_opened) > 90
            ORDER BY age_days DESC
        """).fetchall()

        if stale:
            lines.append(f"  STALE THESES (>90 days old)")
            lines.append(f"  {'─' * 52}")
            for s in stale:
                lines.append(f"  {s['ticker']:<7} {int(s['age_days'])}d old  {s['thesis'][:40]}")
            lines.append("")

        if days_since == 0:
            lines.append("  Report generated today — run `report` again if market has moved.")
        elif days_since >= 7:
            lines.append(f"  {days_since} days since last report — consider running `report`.")

        lines.append(f"{'=' * 58}")
        lines.append("")
        return "\n".join(lines)


    # ------------------------------------------------------------------
    # Portfolio drift analysis
    # ------------------------------------------------------------------
    def portfolio_drift(self):
        """Calculate allocation drift from target weights."""
        dashboard = self.portfolio_dashboard()
        if not dashboard:
            return None

        total_value = sum((r['market_value'] or 0) for r in dashboard)
        if total_value == 0:
            return None

        count = len(dashboard)
        # Default target: equal-weight with 15% cash reserve
        invested_target = 85.0
        per_position_target = invested_target / count if count else 0

        positions = []
        for h in dashboard:
            mv = h['market_value'] or 0
            actual_pct = mv / total_value * 100 if total_value else 0
            drift = actual_pct - per_position_target
            positions.append({
                'ticker': h['ticker'],
                'shares': h['shares'],
                'cost_basis': h['cost_basis'],
                'current_price': h['current_price'] or 0,
                'market_value': mv,
                'actual_pct': actual_pct,
                'target_pct': per_position_target,
                'drift_pct': drift,
                'action': 'TRIM' if drift > 5 else 'ADD' if drift < -5 else 'OK',
            })

        positions.sort(key=lambda x: x['drift_pct'], reverse=True)
        return {
            'positions': positions,
            'total_value': total_value,
            'target_per_position': per_position_target,
        }

    # ------------------------------------------------------------------
    # Position sizing calculator
    # ------------------------------------------------------------------
    def calculate_position_size(self, ticker, conviction, entry_price=None):
        """Calculate optimal position size for a new buy."""
        risk = self.risk_dashboard()
        if not risk:
            return None

        total_value = risk['total_value']
        total_cost = risk['total_cost']

        # Conviction limits
        max_pct = {'***': 18, '**': 12, '*': 7}.get(conviction, 12)

        # Current exposure to this ticker
        existing = self.get_holding(ticker)
        existing_value = 0
        if existing:
            cached = self.get_cached_quote(ticker, max_age_minutes=1440)
            if cached and cached.get('price'):
                existing_value = existing['shares'] * cached['price']

        existing_pct = existing_value / total_value * 100 if total_value else 0
        available_pct = max(0, max_pct - existing_pct)
        max_investment = total_value * available_pct / 100

        # Scaling rules based on portfolio size
        if total_value < 10000:
            tranches = [('Tranche 1 (50%)', 0.50), ('Tranche 2 (50%)', 0.50)]
        elif total_value < 50000:
            tranches = [('Tranche 1 (40%)', 0.40), ('Tranche 2 (30%)', 0.30), ('Tranche 3 (30%)', 0.30)]
        else:
            tranches = [('Tranche 1 (30%)', 0.30), ('Tranche 2 (25%)', 0.25),
                        ('Tranche 3 (25%)', 0.25), ('Tranche 4 (20%)', 0.20)]

        # Stop-loss distances by conviction
        stop_pct = {'***': 0.11, '**': 0.09, '*': 0.075}.get(conviction, 0.09)

        result = {
            'ticker': ticker,
            'conviction': conviction,
            'entry_price': entry_price,
            'max_position_pct': max_pct,
            'existing_pct': existing_pct,
            'available_pct': available_pct,
            'max_investment': max_investment,
            'stop_distance_pct': stop_pct * 100,
            'tranches': [],
            'portfolio_value': total_value,
        }

        if entry_price:
            result['stop_price'] = round(entry_price * (1 - stop_pct), 2)
            for label, pct in tranches:
                amount = max_investment * pct
                shares = amount / entry_price if entry_price > 0 else 0
                result['tranches'].append({
                    'label': label,
                    'amount': round(amount, 2),
                    'shares': round(shares, 4),
                })

        return result

    # ------------------------------------------------------------------
    # Watchlist conversion
    # ------------------------------------------------------------------
    def convert_watchlist_to_trade(self, ticker, price, shares):
        """Convert a watchlist pick to an active trade."""
        today = date.today().isoformat()

        # Find active watchlist entry
        wl = self.conn.execute("""
            SELECT * FROM watchlist WHERE ticker=? AND status='ACTIVE'
            ORDER BY date DESC LIMIT 1
        """, (ticker,)).fetchone()

        if wl:
            self.conn.execute(
                "UPDATE watchlist SET status='CONVERTED' WHERE id=?",
                (wl['id'],)
            )

        # Add trade
        self.add_trade(
            date=today,
            ticker=ticker,
            action='BUY',
            entry_price=price,
            conviction=wl['conviction'] if wl else '**',
            status='OPEN',
            notes=f"Converted from watchlist (rec'd ${wl['price_at_rec']:.2f})" if wl and wl['price_at_rec'] else "Manual entry",
        )
        self.conn.commit()

        return {
            'ticker': ticker,
            'price': price,
            'shares': shares,
            'from_watchlist': bool(wl),
            'rec_price': wl['price_at_rec'] if wl and wl['price_at_rec'] else None,
        }

    # ------------------------------------------------------------------
    # Trade journal
    # ------------------------------------------------------------------
    def add_journal_entry(self, ticker, trade_id=None, reflection=None,
                          what_happened=None, lesson=None):
        """Add a journal entry for a trade."""
        today = date.today().isoformat()

        # Store as thesis_history if we have a thesis, else as improvement
        self.conn.execute("""
            INSERT INTO improvements (date, type, category, priority, finding,
                action, target_file, status, source, meta, created_at)
            VALUES (?, 'journal', 'reflection', 'LOW', ?, ?, NULL, 'active', ?, ?, ?)
        """, (today, reflection or f"Journal entry for {ticker}",
              lesson or "", ticker,
              json.dumps({'ticker': ticker, 'trade_id': trade_id,
                         'what_happened': what_happened}),
              datetime.now().isoformat()))
        self.conn.commit()

    def get_journal_entries(self, ticker=None, limit=20):
        """Get journal entries, optionally filtered by ticker."""
        if ticker:
            return self.conn.execute("""
                SELECT * FROM improvements
                WHERE type='journal' AND source=?
                ORDER BY date DESC LIMIT ?
            """, (ticker, limit)).fetchall()
        return self.conn.execute("""
            SELECT * FROM improvements WHERE type='journal'
            ORDER BY date DESC LIMIT ?
        """, (limit,)).fetchall()

    # ------------------------------------------------------------------
    # Smart money divergence detection
    # ------------------------------------------------------------------
    def detect_smart_money_divergence(self):
        """Find tickers where smart money sources disagree."""
        divergences = []

        # Get all tickers with multiple signals
        tickers_with_signals = self.conn.execute("""
            SELECT DISTINCT ticker FROM learnings
            WHERE consumed=0 AND ticker IS NOT NULL
        """).fetchall()

        for row in tickers_with_signals:
            ticker = row['ticker']
            signals = self.conn.execute("""
                SELECT signal_type, direction, strength, detail
                FROM learnings
                WHERE ticker=? AND consumed=0
                ORDER BY created_at DESC
            """, (ticker,)).fetchall()

            if len(signals) < 2:
                continue

            bullish = [s for s in signals if s['direction'] == 'BULLISH']
            bearish = [s for s in signals if s['direction'] == 'BEARISH']

            if bullish and bearish:
                bull_sources = set(s['signal_type'] for s in bullish)
                bear_sources = set(s['signal_type'] for s in bearish)
                divergences.append({
                    'ticker': ticker,
                    'bullish_sources': list(bull_sources),
                    'bearish_sources': list(bear_sources),
                    'bull_detail': bullish[0]['detail'][:60],
                    'bear_detail': bearish[0]['detail'][:60],
                })

        return divergences

    # ------------------------------------------------------------------
    # Portfolio simulation
    # ------------------------------------------------------------------
    def simulate_additions(self, new_positions):
        """Simulate adding new positions and show resulting portfolio.

        new_positions: list of {'ticker': str, 'amount': float}
        """
        dashboard = self.portfolio_dashboard()
        total_value = sum((r['market_value'] or 0) for r in dashboard)

        # Current positions
        positions = []
        for h in dashboard:
            positions.append({
                'ticker': h['ticker'],
                'current_value': h['market_value'] or 0,
                'current_pct': (h['market_value'] or 0) / total_value * 100 if total_value else 0,
                'is_new': False,
            })

        # Add new positions
        added_total = sum(p['amount'] for p in new_positions)
        new_total = total_value + added_total

        for np in new_positions:
            existing = next((p for p in positions if p['ticker'] == np['ticker']), None)
            if existing:
                existing['current_value'] += np['amount']
                existing['is_new'] = False  # addition to existing
            else:
                positions.append({
                    'ticker': np['ticker'],
                    'current_value': np['amount'],
                    'current_pct': 0,
                    'is_new': True,
                })

        # Recalculate percentages
        for p in positions:
            p['new_pct'] = p['current_value'] / new_total * 100 if new_total else 0
            p['change_pct'] = p['new_pct'] - p['current_pct']

        positions.sort(key=lambda x: x['new_pct'], reverse=True)

        # Check violations
        violations = []
        for p in positions:
            if p['new_pct'] > 18:
                violations.append(f"{p['ticker']} would be {p['new_pct']:.1f}% (max 18%)")
            elif p['new_pct'] > 15 and p.get('is_new'):
                violations.append(f"New position {p['ticker']} at {p['new_pct']:.1f}% (max 15% for new)")

        return {
            'current_total': total_value,
            'added': added_total,
            'new_total': new_total,
            'positions': positions,
            'violations': violations,
            'position_count': len(positions),
        }

    # ------------------------------------------------------------------
    # Report comparison
    # ------------------------------------------------------------------
    def compare_reports(self, date1, date2):
        """Compare two reports by date string."""
        theses1 = self.conn.execute("""
            SELECT ticker, direction, conviction, thesis
            FROM theses WHERE source_report LIKE ?
        """, (f"%{date1}%",)).fetchall()

        theses2 = self.conn.execute("""
            SELECT ticker, direction, conviction, thesis
            FROM theses WHERE source_report LIKE ?
        """, (f"%{date2}%",)).fetchall()

        tickers1 = {r['ticker']: dict(r) for r in theses1}
        tickers2 = {r['ticker']: dict(r) for r in theses2}

        all_tickers = set(tickers1.keys()) | set(tickers2.keys())

        changes = []
        for t in sorted(all_tickers):
            old = tickers1.get(t)
            new = tickers2.get(t)
            if old and not new:
                changes.append({'ticker': t, 'type': 'DROPPED', 'old': old, 'new': None})
            elif new and not old:
                changes.append({'ticker': t, 'type': 'NEW', 'old': None, 'new': new})
            elif old and new:
                if old['direction'] != new['direction']:
                    changes.append({'ticker': t, 'type': 'FLIPPED', 'old': old, 'new': new})
                elif old['conviction'] != new['conviction']:
                    changes.append({'ticker': t, 'type': 'CONVICTION_CHANGE', 'old': old, 'new': new})
                else:
                    changes.append({'ticker': t, 'type': 'UNCHANGED', 'old': old, 'new': new})

        # Benchmark comparison
        bench1 = self.conn.execute(
            "SELECT * FROM benchmarks WHERE date<=? ORDER BY date DESC LIMIT 1",
            (date1,)).fetchone()
        bench2 = self.conn.execute(
            "SELECT * FROM benchmarks WHERE date<=? ORDER BY date DESC LIMIT 1",
            (date2,)).fetchone()

        return {
            'date1': date1,
            'date2': date2,
            'changes': changes,
            'bench1': dict(bench1) if bench1 else None,
            'bench2': dict(bench2) if bench2 else None,
        }

    # ------------------------------------------------------------------
    # Regime detection
    # ------------------------------------------------------------------
    def detect_regime(self):
        """Classify current market regime from latest snapshot data."""
        snap = self.conn.execute(
            "SELECT * FROM market_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if not snap:
            return {'regime': 'UNKNOWN', 'signals': [], 'confidence': 0}

        signals = []
        risk_on = 0
        risk_off = 0

        vix = snap['vix'] or 0
        if vix < 15:
            signals.append(('VIX', f'{vix:.0f}', 'Low volatility', 'RISK-ON'))
            risk_on += 2
        elif vix > 25:
            signals.append(('VIX', f'{vix:.0f}', 'Elevated fear', 'RISK-OFF'))
            risk_off += 2
        else:
            signals.append(('VIX', f'{vix:.0f}', 'Normal range', 'NEUTRAL'))

        breadth = snap['breadth_200'] or 0
        if breadth > 70:
            signals.append(('Breadth', f'{breadth:.0f}%', 'Healthy participation', 'RISK-ON'))
            risk_on += 2
        elif breadth < 40:
            signals.append(('Breadth', f'{breadth:.0f}%', 'Narrow/Bear-like', 'RISK-OFF'))
            risk_off += 2
        else:
            signals.append(('Breadth', f'{breadth:.0f}%', 'Weakening', 'CAUTION'))
            risk_off += 1

        ten_y = snap['ten_year'] or 0
        if ten_y > 5.0:
            signals.append(('10Y Yield', f'{ten_y:.2f}%', 'Restrictive', 'RISK-OFF'))
            risk_off += 1
        elif ten_y < 3.5:
            signals.append(('10Y Yield', f'{ten_y:.2f}%', 'Accommodative', 'RISK-ON'))
            risk_on += 1

        oil = snap['oil'] or 0
        if oil > 90:
            signals.append(('Oil', f'${oil:.0f}', 'Inflationary pressure', 'RISK-OFF'))
            risk_off += 1
        elif oil < 60:
            signals.append(('Oil', f'${oil:.0f}', 'Deflationary', 'RISK-ON'))
            risk_on += 1

        dxy = snap['dxy'] or 0
        if dxy > 105:
            signals.append(('DXY', f'{dxy:.1f}', 'Strong dollar (EM drag)', 'RISK-OFF'))
            risk_off += 1
        elif dxy < 95:
            signals.append(('DXY', f'{dxy:.1f}', 'Weak dollar (risk assets up)', 'RISK-ON'))
            risk_on += 1

        total = risk_on + risk_off
        if total == 0:
            regime = 'NEUTRAL'
            confidence = 50
        elif risk_on > risk_off * 1.5:
            regime = 'RISK-ON'
            confidence = min(95, int(risk_on / total * 100))
        elif risk_off > risk_on * 1.5:
            regime = 'RISK-OFF'
            confidence = min(95, int(risk_off / total * 100))
        else:
            regime = 'TRANSITION'
            confidence = 50

        posture = {
            'RISK-ON': 'Offensive — favor growth, reduce cash',
            'RISK-OFF': 'Defensive — raise cash, favor value/staples',
            'TRANSITION': 'Balanced — maintain positions, tighten stops',
            'NEUTRAL': 'Standard allocation per risk tolerance',
        }

        return {
            'regime': regime,
            'confidence': confidence,
            'signals': signals,
            'posture': posture.get(regime, ''),
            'date': snap['date'],
            'risk_on_score': risk_on,
            'risk_off_score': risk_off,
        }

    # ------------------------------------------------------------------
    # Backtesting
    # ------------------------------------------------------------------
    def backtest_recommendations(self, conviction_filter=None):
        """Backtest all closed trades by conviction level."""
        where = "WHERE status IN ('CLOSED', 'HIT_TARGET', 'STOPPED_OUT')"
        params = []
        if conviction_filter:
            where += " AND conviction=?"
            params.append(conviction_filter)

        trades = self.conn.execute(f"""
            SELECT * FROM trades {where} ORDER BY date
        """, params).fetchall()

        if not trades:
            return None

        results = {
            'total': len(trades),
            'by_conviction': {},
            'by_year': {},
            'cumulative_return': 0,
            'max_drawdown': 0,
            'trades': [],
        }

        cumulative = 0
        peak = 0
        max_dd = 0

        for t in trades:
            ret = t['return_pct'] or 0
            cumulative += ret
            peak = max(peak, cumulative)
            dd = cumulative - peak
            max_dd = min(max_dd, dd)

            conv = t['conviction'] or '**'
            if conv not in results['by_conviction']:
                results['by_conviction'][conv] = {'count': 0, 'wins': 0, 'total_return': 0, 'returns': []}
            bucket = results['by_conviction'][conv]
            bucket['count'] += 1
            if ret > 0:
                bucket['wins'] += 1
            bucket['total_return'] += ret
            bucket['returns'].append(ret)

            year = t['date'][:4]
            if year not in results['by_year']:
                results['by_year'][year] = {'count': 0, 'total_return': 0}
            results['by_year'][year]['count'] += 1
            results['by_year'][year]['total_return'] += ret

        results['cumulative_return'] = cumulative
        results['max_drawdown'] = max_dd

        for conv, b in results['by_conviction'].items():
            b['win_rate'] = b['wins'] / b['count'] * 100 if b['count'] else 0
            b['avg_return'] = b['total_return'] / b['count'] if b['count'] else 0

        return results

    # ------------------------------------------------------------------
    # Peer comparison
    # ------------------------------------------------------------------
    def peer_comparison(self):
        """Compare portfolio against top institutional investors."""
        dashboard = self.portfolio_dashboard()
        my_tickers = {h['ticker'] for h in dashboard}

        peers = {}
        gurus = self.conn.execute("""
            SELECT DISTINCT guru_code, guru_name FROM guru_holdings
        """).fetchall()

        for g in gurus:
            holdings = self.conn.execute("""
                SELECT ticker, pct_portfolio FROM guru_holdings
                WHERE guru_code=?
                ORDER BY pct_portfolio DESC
            """, (g['guru_code'],)).fetchall()

            guru_tickers = {h['ticker'] for h in holdings}
            overlap = my_tickers & guru_tickers
            peers[g['guru_name'] or g['guru_code']] = {
                'total_positions': len(holdings),
                'overlap': list(overlap),
                'overlap_count': len(overlap),
                'top5': [(h['ticker'], h['pct_portfolio']) for h in holdings[:5]],
            }

        # ARK overlap
        ark = self.conn.execute("""
            SELECT DISTINCT ticker FROM ark_trades
            WHERE direction='Buy'
            AND date >= date('now', '-30 days')
        """).fetchall()
        ark_tickers = {r['ticker'] for r in ark}
        ark_overlap = my_tickers & ark_tickers
        if ark_tickers:
            peers['ARK Invest (recent buys)'] = {
                'total_positions': len(ark_tickers),
                'overlap': list(ark_overlap),
                'overlap_count': len(ark_overlap),
                'top5': [],
            }

        return peers

    # ------------------------------------------------------------------
    # Report template pre-fill
    # ------------------------------------------------------------------
    def generate_report_skeleton(self):
        """Generate a pre-filled report skeleton with data from DB."""
        now = datetime.now()
        lines = []

        lines.append(f"# Vault Research Desk — Weekly Report")
        lines.append(f"## {now.strftime('%B %d, %Y')}")
        lines.append("")

        # Search Log
        holdings = self.get_holdings()
        watchlist = self.get_active_watchlist()
        all_tickers = set(h['ticker'] for h in holdings)
        all_tickers.update(w['ticker'] for w in watchlist)
        lines.append(self.generate_search_log(all_tickers))

        # Portfolio section
        dashboard = self.portfolio_dashboard()
        if dashboard:
            lines.append("### Your Portfolio")
            lines.append("")
            lines.append("| Stock | Shares | Cost | Current | P&L | Action |")
            lines.append("|-------|--------|------|---------|-----|--------|")
            for h in dashboard:
                pnl = f"{h['pnl_pct'] or 0:+.1f}%" if h['pnl_pct'] else "n/a"
                price = f"${h['current_price']:.2f}" if h['current_price'] else "—"
                lines.append(f"| {h['ticker']} | {h['shares']:.4f} | ${h['cost_basis']:.2f} | {price} | {pnl} | **HOLD** |")
            lines.append("")

        # Benchmark
        bench = self.conn.execute(
            "SELECT * FROM benchmarks ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if bench and bench['portfolio_pct'] is not None:
            lines.append(f"Portfolio since inception: {bench['portfolio_pct']:+.2f}%")
            lines.append(f"VOO over same period: {bench['voo_pct'] or 0:+.2f}%")
            lines.append("")

        # Regime
        regime = self.detect_regime()
        if regime['regime'] != 'UNKNOWN':
            lines.append(f"### Market Regime: {regime['regime']} ({regime['confidence']}% confidence)")
            lines.append(f"Posture: {regime['posture']}")
            lines.append("")

        # Placeholders
        for section in ["### What's Happening", "### This Week",
                        "### What to Buy", "### What to Avoid",
                        "### Biggest Risks", "### Chief's Corner",
                        "### Gut Check", "### Validation Summary (Devil's Gate)",
                        "### Alert Conditions", "### Bottom Line"]:
            lines.append(section)
            lines.append("")
            lines.append("*[TODO: Fill in]*")
            lines.append("")

        lines.append("---")
        lines.append("*Disclaimer: Educational purposes only. Not financial advice.*")

        return "\n".join(lines)


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
    elif len(sys.argv) > 1 and sys.argv[1] == "morning":
        with VaultDB() as db:
            print(db.morning_briefing())
    elif len(sys.argv) > 1 and sys.argv[1] == "changes":
        with VaultDB() as db:
            print(db.changes_since_last_report())
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
        print("  python3 tools/db.py morning       — Morning briefing (full overview)")
        print("  python3 tools/db.py dashboard     — Portfolio overview")
        print("  python3 tools/db.py consensus     — Institutional consensus")
        print("  python3 tools/db.py smart-money TICKER — Smart money check")
        print("  python3 tools/db.py export        — Dump tables to exports/ as CSV")
        print("  python3 tools/db.py migrate       — Import existing CSV/JSON data")
        print()
        print(f"DB path: {DB_PATH}")
        if os.path.exists(DB_PATH):
            print(f"DB size: {os.path.getsize(DB_PATH) / 1024:.1f} KB")
