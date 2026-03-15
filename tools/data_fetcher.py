#!/usr/bin/env python3
"""
Vault Research Desk — Data Fetcher
Pulls real market data using yfinance. Run before every report.

Usage:
    python3 data_fetcher.py                    # Full report data
    python3 data_fetcher.py NVDA LMT AMZN      # Add extra tickers
    python3 data_fetcher.py --portfolio-only    # Just portfolio holdings
"""

import sys
import os
import json
from datetime import datetime, timedelta

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("ERROR: Required packages not installed.")
    print("Run: pip3 install yfinance pandas")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from db import VaultDB

# --- Configuration ---

# Always fetch these (macro + sectors)
MACRO_TICKERS = [
    "^GSPC",   # S&P 500
    "^IXIC",   # Nasdaq
    "^DJI",    # Dow Jones
    "^VIX",    # VIX
    "^TNX",    # 10Y Treasury Yield
    "DX-Y.NYB",  # Dollar Index (DXY)
    "CL=F",    # WTI Crude Oil
    "GC=F",    # Gold Futures
]

SECTOR_ETFS = [
    "XLK",   # Technology
    "XLV",   # Healthcare
    "XLF",   # Financials
    "XLE",   # Energy
    "XLY",   # Consumer Discretionary
    "XLP",   # Consumer Staples
    "XLI",   # Industrials
    "XLB",   # Materials
    "XLRE",  # Real Estate
    "XLU",   # Utilities
    "XLC",   # Communication Services
]

# Benchmark
BENCHMARK = "VOO"

# BUY candidates — pass via CLI (e.g., python3 data_fetcher.py NVDA LMT AAPL)
# No hardcoded candidates. Add tickers as arguments when running.
COMMON_CANDIDATES = []

# Breadth sample: ~4 large-caps per sector for market breadth approximation
BREADTH_SAMPLE = [
    # Technology
    "AAPL", "MSFT", "NVDA", "AVGO",
    # Healthcare
    "UNH", "JNJ", "LLY", "ABBV",
    # Financials
    "JPM", "BAC", "GS", "BRK-B",
    # Energy
    "XOM", "CVX", "COP", "SLB",
    # Consumer Discretionary
    "AMZN", "TSLA", "HD", "MCD",
    # Consumer Staples
    "PG", "KO", "PEP", "COST",
    # Industrials
    "CAT", "GE", "UNP", "RTX",
    # Materials
    "LIN", "APD", "FCX", "NEM",
    # Real Estate
    "PLD", "AMT", "EQIX", "SPG",
    # Utilities
    "NEE", "SO", "DUK", "AEP",
    # Communication Services
    "GOOGL", "META", "NFLX", "DIS",
]

MACRO_NAMES = {
    "^GSPC": "S&P 500", "^IXIC": "Nasdaq", "^DJI": "Dow Jones",
    "^VIX": "VIX", "^TNX": "10Y Yield", "DX-Y.NYB": "DXY",
    "CL=F": "WTI Oil", "GC=F": "Gold",
}

SECTOR_NAMES = {
    "XLK": "Technology", "XLV": "Healthcare", "XLF": "Financials",
    "XLE": "Energy", "XLY": "Cons. Disc.", "XLP": "Cons. Staples",
    "XLI": "Industrials", "XLB": "Materials", "XLRE": "Real Estate",
    "XLU": "Utilities", "XLC": "Comm. Services",
}


def read_portfolio():
    """Read tickers from portfolio.md"""
    import os
    portfolio_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "portfolio.md")
    tickers = []
    holdings = {}

    try:
        with open(portfolio_path, 'r') as f:
            lines = f.readlines()

        in_table = False
        for line in lines:
            line = line.strip()
            if '|' in line and 'Ticker' in line:
                in_table = True
                continue
            if in_table and '|' in line and '---' not in line:
                parts = [p.strip() for p in line.split('|') if p.strip()]
                if len(parts) >= 3 and parts[0] and parts[0] != '':
                    ticker = parts[0]
                    if ticker and ticker.isalpha():
                        tickers.append(ticker)
                        try:
                            holdings[ticker] = {
                                'shares': float(parts[1]) if len(parts) > 1 else 0,
                                'cost': float(parts[2].replace('$', '')) if len(parts) > 2 else 0,
                                'date': parts[3] if len(parts) > 3 else '',
                            }
                        except (ValueError, IndexError):
                            holdings[ticker] = {}

        # Read settings and profile (key: value lines)
        settings = {}
        setting_keys = [
            'Risk tolerance', 'Monthly investment', 'Cash available',
            'Name', 'Location', 'Broker', 'Experience', 'Preference', 'Start date',
        ]
        for line in lines:
            line = line.strip()
            for key in setting_keys:
                if line.startswith(f'{key}:'):
                    val = line.split(':', 1)[1].strip()
                    settings[key.lower().replace(' ', '_')] = val
                    # Parse numeric values
                    if key in ('Monthly investment', 'Cash available'):
                        try:
                            settings[key.lower().replace(' ', '_')] = float(
                                val.replace('$', '').replace(',', '').replace('€', '')
                            )
                        except ValueError:
                            pass

    except FileNotFoundError:
        pass

    return tickers, holdings, settings


def fetch_quote(ticker):
    """Fetch current price and key data for a ticker."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist.empty:
            return None

        current = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) > 1 else current

        price = round(current['Close'], 2)
        prev_close = round(prev['Close'], 2)
        change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0

        result = {
            'price': price,
            'prev_close': prev_close,
            'change_pct': change_pct,
            'high': round(current['High'], 2),
            'low': round(current['Low'], 2),
            'volume': int(current['Volume']),
        }

        try:
            with VaultDB() as db:
                db.cache_quote(ticker, result)
        except Exception as e:
            print(f"  Warning: could not cache quote for {ticker}: {e}", file=sys.stderr)

        return result
    except Exception as e:
        return {'error': str(e)}


def fetch_technicals(ticker):
    """Fetch technical indicators: 50 DMA, 200 DMA, RSI."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")
        if hist.empty or len(hist) < 50:
            return {}

        close = hist['Close']
        result = {}

        # Moving averages
        if len(close) >= 50:
            result['dma_50'] = round(close.rolling(50).mean().iloc[-1], 2)
        if len(close) >= 200:
            result['dma_200'] = round(close.rolling(200).mean().iloc[-1], 2)

        # RSI (14-period)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        result['rsi'] = round(rsi.iloc[-1], 1)

        # 52-week high/low
        result['high_52w'] = round(close.max(), 2)
        result['low_52w'] = round(close.min(), 2)

        # % from 52-week high
        current = close.iloc[-1]
        result['pct_from_high'] = round((current - result['high_52w']) / result['high_52w'] * 100, 1)

        try:
            with VaultDB() as db:
                db.cache_technicals(ticker, result)
        except Exception as e:
            print(f"  Warning: could not cache technicals for {ticker}: {e}", file=sys.stderr)

        return result
    except Exception as e:
        print(f"  Warning: could not fetch technicals for {ticker}: {e}", file=sys.stderr)
        return {}


def fetch_earnings_date(ticker):
    """Check upcoming earnings date."""
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is not None and not cal.empty:
            if 'Earnings Date' in cal.index:
                dates = cal.loc['Earnings Date']
                if hasattr(dates, '__iter__'):
                    return str(dates.iloc[0].date()) if hasattr(dates.iloc[0], 'date') else str(dates.iloc[0])
                return str(dates)
        # Try earnings_dates attribute
        ed = t.earnings_dates
        if ed is not None and not ed.empty:
            future = ed.index[ed.index >= pd.Timestamp.now(tz='America/New_York')]
            if len(future) > 0:
                return str(future[0].date())
    except Exception:
        pass
    return None


def fetch_market_breadth():
    """Approximate market breadth using sector ETFs + large-cap sample."""
    tickers = SECTOR_ETFS + BREADTH_SAMPLE
    above_50 = 0
    above_200 = 0
    total = 0

    for ticker in tickers:
        tech = fetch_technicals(ticker)
        if not tech or 'dma_50' not in tech:
            continue
        q = fetch_quote(ticker)
        if not q or 'error' in q:
            continue

        price = q['price']
        total += 1
        if price > tech['dma_50']:
            above_50 += 1
        if 'dma_200' in tech and price > tech['dma_200']:
            above_200 += 1

    if total == 0:
        return None

    pct_50 = round(above_50 / total * 100, 1)
    pct_200 = round(above_200 / total * 100, 1)

    if pct_200 > 70:
        interpretation = "Healthy"
    elif pct_200 > 40:
        interpretation = "Weakening"
    else:
        interpretation = "Bear-like"

    return {
        'above_50dma_pct': pct_50,
        'above_200dma_pct': pct_200,
        'sample_size': total,
        'interpretation': interpretation,
    }


def main():
    args = sys.argv[1:]
    portfolio_only = '--portfolio-only' in args
    extra_tickers = [a.upper() for a in args if not a.startswith('--')]

    # Read portfolio
    port_tickers, holdings, settings = read_portfolio()

    print("=" * 60)
    print("  VAULT RESEARCH DESK — DATA FETCH")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # --- Portfolio Status ---
    print(f"\n{'─' * 40}")
    print("PORTFOLIO STATUS")
    print(f"{'─' * 40}")
    if port_tickers:
        print(f"Holdings: {', '.join(port_tickers)}")
        for t, h in holdings.items():
            print(f"  {t}: {h.get('shares', '?')} shares @ ${h.get('cost', '?')} (bought {h.get('date', '?')})")
    else:
        print("Portfolio: EMPTY — no holdings on file")
    if settings:
        for k, v in settings.items():
            print(f"  {k}: {v}")

    # --- Macro Data ---
    macro_prices = {}  # Collect for DB snapshot
    if not portfolio_only:
        print(f"\n{'─' * 40}")
        print("MACRO DATA")
        print(f"{'─' * 40}")
        print(f"{'Name':<15} {'Price':>12} {'Change':>8}")
        print(f"{'─' * 35}")
        for ticker in MACRO_TICKERS:
            q = fetch_quote(ticker)
            name = MACRO_NAMES.get(ticker, ticker)
            if q and 'error' not in q:
                sign = '+' if q['change_pct'] >= 0 else ''
                print(f"{name:<15} {q['price']:>12,.2f} {sign}{q['change_pct']:>7.2f}%")
                macro_prices[ticker] = q['price']
            else:
                err = q.get('error', 'no data') if q else 'no data'
                print(f"{name:<15} {'ERROR':>12} {err}")

    # --- Sector ETFs ---
    sector_ranked = []
    if not portfolio_only:
        print(f"\n{'─' * 40}")
        print("SECTOR PERFORMANCE")
        print(f"{'─' * 40}")
        sector_data = []
        print(f"{'Sector':<16} {'ETF':<6} {'Price':>8} {'Chg%':>7} {'RSI':>5} {'vs 50d':>7} {'vs 200d':>7}")
        print(f"{'─' * 58}")
        for ticker in SECTOR_ETFS:
            q = fetch_quote(ticker)
            tech = fetch_technicals(ticker)
            name = SECTOR_NAMES.get(ticker, ticker)
            if q and 'error' not in q:
                price = q['price']
                chg = q['change_pct']
                rsi = tech.get('rsi', '-')
                vs50 = f"{((price - tech['dma_50']) / tech['dma_50'] * 100):+.1f}%" if 'dma_50' in tech else '-'
                vs200 = f"{((price - tech['dma_200']) / tech['dma_200'] * 100):+.1f}%" if 'dma_200' in tech else '-'
                sign = '+' if chg >= 0 else ''
                print(f"{name:<16} {ticker:<6} {price:>8.2f} {sign}{chg:>6.2f}% {rsi:>5} {vs50:>7} {vs200:>7}")
                sector_data.append((name, ticker, price, chg, rsi))
            else:
                print(f"{name:<16} {ticker:<6} {'ERROR':>8}")

        # Sort by change% for ranking
        if sector_data:
            print(f"\nSector Ranking (by daily change):")
            ranked = sorted(sector_data, key=lambda x: x[3] if isinstance(x[3], (int, float)) else 0, reverse=True)
            for i, (name, ticker, price, chg, rsi) in enumerate(ranked, 1):
                sign = '+' if chg >= 0 else ''
                print(f"  {i:>2}. {name:<16} ({ticker}) {sign}{chg:.2f}%")
                sector_ranked.append((name, ticker, price, chg, rsi, i))

    # --- Market Breadth ---
    breadth = None
    if not portfolio_only:
        print(f"\n{'─' * 40}")
        print("MARKET BREADTH (approximate)")
        print(f"{'─' * 40}")
        breadth = fetch_market_breadth()
        if breadth:
            print(f"  Sample size: {breadth['sample_size']} stocks")
            print(f"  % above 50 DMA:  {breadth['above_50dma_pct']}%")
            print(f"  % above 200 DMA: {breadth['above_200dma_pct']}%")
            print(f"  Breadth read: {breadth['interpretation']}")
        else:
            print("  ERROR: Could not calculate breadth")

    # --- Benchmark ---
    if not portfolio_only:
        print(f"\n{'─' * 40}")
        print("BENCHMARK (VOO)")
        print(f"{'─' * 40}")
        q = fetch_quote(BENCHMARK)
        if q and 'error' not in q:
            print(f"VOO: ${q['price']:.2f} ({'+' if q['change_pct'] >= 0 else ''}{q['change_pct']:.2f}%)")
        tech = fetch_technicals(BENCHMARK)
        if tech:
            print(f"  RSI: {tech.get('rsi', '-')} | 50 DMA: ${tech.get('dma_50', '-')} | 200 DMA: ${tech.get('dma_200', '-')}")
            print(f"  52-wk range: ${tech.get('low_52w', '-')} - ${tech.get('high_52w', '-')} ({tech.get('pct_from_high', '-')}% from high)")

    # --- Portfolio Holdings (detailed) ---
    if port_tickers:
        print(f"\n{'─' * 40}")
        print("PORTFOLIO HOLDINGS — DETAILED")
        print(f"{'─' * 40}")
        total_value = 0
        total_cost = 0
        for ticker in port_tickers:
            q = fetch_quote(ticker)
            tech = fetch_technicals(ticker)
            h = holdings.get(ticker, {})
            print(f"\n  {ticker}:")
            if q and 'error' not in q:
                price = q['price']
                shares = h.get('shares', 0)
                cost = h.get('cost', 0)
                value = shares * price
                cost_total = shares * cost
                pnl = value - cost_total
                pnl_pct = (pnl / cost_total * 100) if cost_total > 0 else 0
                total_value += value
                total_cost += cost_total

                print(f"    Price: ${price:.2f} ({'+' if q['change_pct'] >= 0 else ''}{q['change_pct']:.2f}%)")
                print(f"    Shares: {shares} @ ${cost:.2f} = ${cost_total:.2f}")
                print(f"    Value: ${value:.2f} | P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)")
            if tech:
                print(f"    50 DMA: ${tech.get('dma_50', '-')} | 200 DMA: ${tech.get('dma_200', '-')} | RSI: {tech.get('rsi', '-')}")
                print(f"    52-wk: ${tech.get('low_52w', '-')} - ${tech.get('high_52w', '-')} ({tech.get('pct_from_high', '-')}% from high)")

            # Earnings check
            earnings = fetch_earnings_date(ticker)
            if earnings:
                print(f"    Next earnings: {earnings}")

        if total_cost > 0:
            total_pnl = total_value - total_cost
            total_pnl_pct = (total_pnl / total_cost) * 100
            print(f"\n  TOTAL: ${total_value:.2f} (cost: ${total_cost:.2f}, P&L: ${total_pnl:+.2f} / {total_pnl_pct:+.1f}%)")

    # --- Extra Tickers (BUY candidates) ---
    all_extra = list(set(COMMON_CANDIDATES + extra_tickers) - set(port_tickers) - set(SECTOR_ETFS))
    if all_extra and not portfolio_only:
        print(f"\n{'─' * 40}")
        print("BUY CANDIDATES")
        print(f"{'─' * 40}")
        for ticker in sorted(all_extra):
            q = fetch_quote(ticker)
            tech = fetch_technicals(ticker)
            if q and 'error' not in q:
                price = q['price']
                print(f"\n  {ticker}: ${price:.2f} ({'+' if q['change_pct'] >= 0 else ''}{q['change_pct']:.2f}%)")
                if tech:
                    print(f"    50 DMA: ${tech.get('dma_50', '-')} | 200 DMA: ${tech.get('dma_200', '-')} | RSI: {tech.get('rsi', '-')}")
                    print(f"    52-wk: ${tech.get('low_52w', '-')} - ${tech.get('high_52w', '-')} ({tech.get('pct_from_high', '-')}% from high)")
                earnings = fetch_earnings_date(ticker)
                if earnings:
                    print(f"    Next earnings: {earnings}")
            else:
                print(f"\n  {ticker}: ERROR")

    # --- Auto-run alerts ---
    if not portfolio_only:
        print(f"\n{'─' * 40}")
        print("ALERT CHECK (auto)")
        print(f"{'─' * 40}")
        try:
            import subprocess
            alerts_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alerts.py")
            result = subprocess.run(
                [sys.executable, alerts_script],
                capture_output=True, text=True, timeout=60,
            )
            # Print only the results, skip blank lines at start
            for line in result.stdout.strip().split("\n"):
                print(f"  {line}")
        except Exception as e:
            print(f"  Could not run alerts: {e}")

    # --- Log benchmark to DB ---
    if not portfolio_only and port_tickers:
        try:
            _log_benchmark(total_value, total_cost)
        except Exception as e:
            print(f"  Warning: could not log benchmark: {e}", file=sys.stderr)

    # --- News fetch (Finnhub) ---
    # Check api_keys.conf as fallback for FINNHUB key
    _finnhub_key = os.environ.get("FINNHUB_API_KEY", "")
    if not _finnhub_key:
        _conf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_keys.conf")
        if os.path.exists(_conf):
            with open(_conf) as _f:
                for _line in _f:
                    _line = _line.strip()
                    if _line.startswith("FINNHUB_API_KEY="):
                        _finnhub_key = _line.split("=", 1)[1].strip()
                        os.environ["FINNHUB_API_KEY"] = _finnhub_key
                        break
    if not portfolio_only and _finnhub_key:
        print(f"\n{'─' * 40}")
        print("NEWS FETCH (Finnhub)")
        print(f"{'─' * 40}")
        try:
            from news import get_news
            # Market news
            market_articles = get_news("MARKET", force=False)
            print(f"  MARKET: {len(market_articles)} articles")
            # Portfolio + candidate news
            news_tickers = list(set(port_tickers + extra_tickers))
            for t in news_tickers:
                articles = get_news(t, days_back=7, force=False)
                print(f"  {t}: {len(articles)} articles")
        except Exception as e:
            print(f"  News fetch error: {e}")

    # --- Finnhub: Analyst Recommendations + Earnings ---
    if _finnhub_key:
        print(f"\n{'─' * 40}")
        print("ANALYST RECOMMENDATIONS (Finnhub)")
        print(f"{'─' * 40}")
        all_rec_tickers = list(set(port_tickers + extra_tickers))
        for t in all_rec_tickers:
            try:
                from urllib.request import Request, urlopen
                import json as _json
                url = f"https://finnhub.io/api/v1/stock/recommendation?symbol={t}&token={_finnhub_key}"
                req = Request(url, headers={"Accept": "application/json"})
                with urlopen(req, timeout=10) as resp:
                    recs = _json.loads(resp.read())
                if recs and len(recs) > 0:
                    latest = recs[0]
                    total = latest.get('strongBuy',0) + latest.get('buy',0) + latest.get('hold',0) + latest.get('sell',0) + latest.get('strongSell',0)
                    if total > 0:
                        bull = latest.get('strongBuy',0) + latest.get('buy',0)
                        bear = latest.get('sell',0) + latest.get('strongSell',0)
                        print(f"  {t}: {latest.get('strongBuy',0)} Strong Buy, {latest.get('buy',0)} Buy, "
                              f"{latest.get('hold',0)} Hold, {latest.get('sell',0)} Sell "
                              f"({latest.get('period','')[:7]}) — {'BULLISH' if bull > bear else 'MIXED' if bull == bear else 'BEARISH'}")
            except Exception as e:
                print(f"  {t}: error — {e}")

        # Earnings calendar (next 30 days)
        print(f"\n{'─' * 40}")
        print("EARNINGS CALENDAR (next 30 days)")
        print(f"{'─' * 40}")
        try:
            from urllib.request import Request, urlopen
            import json as _json
            today_str = datetime.now().strftime("%Y-%m-%d")
            future_str = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            url = f"https://finnhub.io/api/v1/calendar/earnings?from={today_str}&to={future_str}&token={_finnhub_key}"
            req = Request(url, headers={"Accept": "application/json"})
            with urlopen(req, timeout=15) as resp:
                cal = _json.loads(resp.read())
            if cal and "earningsCalendar" in cal:
                relevant = [e for e in cal["earningsCalendar"]
                           if e.get("symbol") in set(port_tickers + extra_tickers)]
                if relevant:
                    for e in sorted(relevant, key=lambda x: x.get("date", "")):
                        est = f"EPS est: ${e['epsEstimate']:.2f}" if e.get('epsEstimate') else "no estimate"
                        print(f"  {e['date']}  {e['symbol']:6s}  {est}  ⚠️ EARNINGS")
                else:
                    print("  No portfolio/candidate earnings in next 30 days.")
        except Exception as e:
            print(f"  Earnings calendar error: {e}")

    # --- Sync to DB ---
    try:
        with VaultDB() as db:
            # Sync holdings from portfolio.md
            db.sync_holdings_from_portfolio()

            # Save market snapshot
            if macro_prices:
                today = datetime.now().strftime("%Y-%m-%d")
                breadth_50 = breadth.get('above_50dma_pct') if not portfolio_only and breadth else None
                breadth_200 = breadth.get('above_200dma_pct') if not portfolio_only and breadth else None
                db.save_market_snapshot(
                    date=today,
                    spy=macro_prices.get("^GSPC"),
                    vix=macro_prices.get("^VIX"),
                    oil=macro_prices.get("CL=F"),
                    gold=macro_prices.get("GC=F"),
                    dxy=macro_prices.get("DX-Y.NYB"),
                    ten_year=macro_prices.get("^TNX"),
                    nasdaq=macro_prices.get("^IXIC"),
                    breadth_50=breadth_50,
                    breadth_200=breadth_200,
                )

            # Save sector performance rankings
            if not portfolio_only and sector_ranked:
                today = datetime.now().strftime("%Y-%m-%d")
                for name, ticker, price, chg, rsi, rank in sector_ranked:
                    db.save_sector_performance(
                        date=today,
                        sector=name,
                        etf_ticker=ticker,
                        price=price,
                        change_1w=chg,  # daily change stored as 1w placeholder
                        rsi=rsi if isinstance(rsi, (int, float)) else None,
                        rank=rank,
                    )
    except Exception as e:
        print(f"  Warning: could not sync to DB: {e}", file=sys.stderr)

    print(f"\n{'=' * 60}")
    print(f"  Data fetch complete. {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'=' * 60}")


def _log_benchmark(portfolio_value, portfolio_cost):
    """Log today's portfolio vs VOO snapshot to DB."""
    today = datetime.now().strftime("%Y-%m-%d")

    # Read portfolio start date and VOO inception price
    _, _, settings = read_portfolio()
    start_date = settings.get("start_date", "2026-03-10")

    # Get VOO current
    voo_q = fetch_quote("VOO")
    if not voo_q or "error" in voo_q:
        return

    voo_price = voo_q["price"]

    # Get VOO price at inception
    try:
        t = yf.Ticker("VOO")
        dt = datetime.strptime(start_date, "%Y-%m-%d")
        start = (dt - timedelta(days=3)).strftime("%Y-%m-%d")
        end = (dt + timedelta(days=3)).strftime("%Y-%m-%d")
        hist = t.history(start=start, end=end)
        if hist.empty:
            return
        hist.index = hist.index.tz_localize(None)
        target = pd.Timestamp(dt)
        valid = hist.index[hist.index <= target]
        voo_inception = float(hist.loc[valid[-1]]["Close"]) if len(valid) > 0 else float(hist.iloc[0]["Close"])
    except Exception:
        return

    portfolio_pct = round((portfolio_value - portfolio_cost) / portfolio_cost * 100, 2) if portfolio_cost > 0 else 0
    voo_pct = round((voo_price - voo_inception) / voo_inception * 100, 2)
    alpha = round(portfolio_pct - voo_pct, 2)

    # Write to DB only
    try:
        with VaultDB() as db:
            db.add_benchmark(today, portfolio_value, portfolio_pct,
                             voo_price, voo_pct, alpha)
    except Exception as e:
        print(f"  Warning: could not save benchmark: {e}", file=sys.stderr)


if __name__ == '__main__':
    main()
