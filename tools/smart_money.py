#!/usr/bin/env python3
"""
Vault Research Desk — Smart Money Tracker

Three data sources, one unified view:
  1. ARK Invest daily trades (arkfunds.io API)
  2. Superinvestor holdings (Dataroma.com — Buffett, Ackman, etc.)
  3. SEC 13F quarterly filings (already in vault.db via learn_from_pros.py)

Usage:
    python3 tools/smart_money.py ark                    # Latest ARK trades
    python3 tools/smart_money.py ark --days 30          # ARK trades last 30 days
    python3 tools/smart_money.py ark --ticker TSLA      # ARK trades for TSLA

    python3 tools/smart_money.py gurus                  # Fetch top guru holdings
    python3 tools/smart_money.py gurus --list           # List available gurus
    python3 tools/smart_money.py gurus BRK psc          # Specific gurus

    python3 tools/smart_money.py consensus              # Tickers held by 2+ gurus
    python3 tools/smart_money.py check GOOGL            # Full smart money check for ticker
"""

import json
import os
import re
import sys
import argparse
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from db import VaultDB

# ── Config ─────────────────────────────────────────────────────────

ARKFUNDS_BASE = "https://arkfunds.io/api/v2"
DATAROMA_BASE = "https://www.dataroma.com/m"

# Top gurus to track by default
DEFAULT_GURUS = {
    "BRK": "Warren Buffett",
    "psc": "Bill Ackman",
    "PI": "Mohnish Pabrai",
    "GLRE": "David Einhorn",
    "BAUPOST": "Seth Klarman",
    "TCI": "Chris Hohn",
    "ac": "Chuck Akre",
    "LMM": "Li Lu",
}

ARK_FUNDS = ["ARKK", "ARKG", "ARKW", "ARKF", "ARKQ", "ARKX"]

# ── HTTP helpers ───────────────────────────────────────────────────

def _fetch_json(url, timeout=15):
    """Fetch JSON from API."""
    req = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "VaultResearchDesk/2.0",
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError) as e:
        print(f"  API error: {e}")
        return None


def _fetch_html(url, timeout=15):
    """Fetch HTML page."""
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except (URLError, HTTPError) as e:
        print(f"  Fetch error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════
# ARK Invest
# ═══════════════════════════════════════════════════════════════════

def fetch_ark_trades(fund="ARKK", days=7):
    """Fetch recent ARK trades from arkfunds.io API."""
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    date_to = datetime.now().strftime("%Y-%m-%d")

    url = (f"{ARKFUNDS_BASE}/etf/trades"
           f"?symbol={fund}&date_from={date_from}&date_to={date_to}")

    data = _fetch_json(url)
    if not data or "trades" not in data:
        return []
    return data["trades"]


def fetch_all_ark_trades(days=7):
    """Fetch trades across all ARK funds."""
    all_trades = []
    for fund in ARK_FUNDS:
        trades = fetch_ark_trades(fund, days)
        all_trades.extend(trades)
        if trades:
            print(f"  {fund}: {len(trades)} trades")
    return all_trades


def cmd_ark(args):
    """Handle 'ark' command."""
    days = args.days or 7

    with VaultDB() as db:
        # Check cache freshness
        cached = db.get_ark_trades(days=days, ticker=args.ticker,
                                    direction=args.direction)
        if cached and not args.no_cache:
            # Check if cache is recent enough (< 4 hours)
            latest = cached[0] if cached else None
            if latest:
                try:
                    cached_at = datetime.fromisoformat(latest["cached_at"])
                except (ValueError, TypeError):
                    cached_at = None  # Treat as expired cache
                if cached_at is None:
                    age_hrs = float("inf")
                else:
                    age_hrs = (datetime.now() - cached_at).total_seconds() / 3600
                if age_hrs < 4:
                    _print_ark_trades(cached, from_cache=True)
                    return

        # Fetch fresh
        print(f"\nFetching ARK trades (last {days} days)...")
        all_trades = fetch_all_ark_trades(days)

        if all_trades:
            db.cache_ark_trades(all_trades)
            print(f"\n  Total: {len(all_trades)} trades cached")

        # Query back with filters
        results = db.get_ark_trades(days=days, ticker=args.ticker,
                                     direction=args.direction)
        _print_ark_trades(results, from_cache=False)


def _print_ark_trades(trades, from_cache=False):
    """Print formatted ARK trades."""
    tag = " (cached)" if from_cache else ""
    print(f"\n{'═' * 60}")
    print(f"  ARK INVEST TRADES{tag}")
    print(f"{'═' * 60}")

    if not trades:
        print("  No trades found.")
        return

    # Group by date
    by_date = {}
    for t in trades:
        d = t["date"]
        if d not in by_date:
            by_date[d] = []
        by_date[d].append(t)

    for date in sorted(by_date.keys(), reverse=True):
        print(f"\n  {date}")
        print(f"  {'─' * 50}")
        for t in by_date[date]:
            direction = "BUY " if t["direction"] == "Buy" else "SELL"
            shares = f"{t['shares']:>10,}" if t['shares'] else ""
            weight = f"{t['etf_percent']:.4f}%" if t['etf_percent'] else ""
            print(f"    {direction}  {t['ticker']:6s}  {t['fund']:5s}  "
                  f"{shares}  {weight}  {t['company'] or ''}")

    # Summary
    buys = [t for t in trades if t["direction"] == "Buy"]
    sells = [t for t in trades if t["direction"] == "Sell"]
    buy_tickers = set(t["ticker"] for t in buys)
    sell_tickers = set(t["ticker"] for t in sells)
    print(f"\n  Summary: {len(buys)} buys, {len(sells)} sells")
    if buy_tickers:
        print(f"  Buying: {', '.join(sorted(buy_tickers))}")
    if sell_tickers:
        print(f"  Selling: {', '.join(sorted(sell_tickers))}")


# ═══════════════════════════════════════════════════════════════════
# Dataroma Superinvestors
# ═══════════════════════════════════════════════════════════════════

def _parse_value(text):
    """Parse dollar value like '$2,217,678,000' to float."""
    text = text.replace("$", "").replace(",", "").strip()
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _parse_shares(text):
    """Parse share count like '9,607,824' to int."""
    text = text.replace(",", "").strip()
    try:
        return int(text)
    except (ValueError, TypeError):
        return None


def fetch_guru_holdings(guru_code):
    """Fetch holdings for a superinvestor from Dataroma."""
    url = f"{DATAROMA_BASE}/holdings.php?m={guru_code}"
    html = _fetch_html(url)
    if not html:
        return [], "", ""

    # Extract guru name from page title
    name_match = re.search(r'<title>(.*?)\s*-', html)
    guru_name = name_match.group(1).strip() if name_match else guru_code

    # Extract quarter from page
    quarter_match = re.search(r'Portfolio date:\s*(\d{1,2}\s+\w+\s+\d{4})', html)
    if quarter_match:
        try:
            dt = datetime.strptime(quarter_match.group(1), "%d %b %Y")
            q = f"Q{(dt.month - 1) // 3 + 1}-{dt.year}"
        except ValueError:
            q = "Q4-2025"
    else:
        q = "Q4-2025"

    # Parse holdings from table rows
    holdings = []
    # Pattern: ticker - company, pct, activity, shares, price, value
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)

    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(cells) < 7:
            continue

        # Clean HTML from cells
        clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]

        # Cell[1] should be "TICKER - Company Name"
        ticker_match = re.match(r'^([A-Z]{1,5})\s*-\s*(.+)', clean[1])
        if not ticker_match:
            continue

        ticker = ticker_match.group(1)
        company = ticker_match.group(2).strip()

        # Cell[2] = % of portfolio
        try:
            pct = float(clean[2])
        except (ValueError, TypeError):
            pct = None

        # Cell[3] = activity (Buy, Add X%, Reduce X%, Sell)
        activity = clean[3].strip()

        # Cell[4] = shares
        shares = _parse_shares(clean[4])

        # Cell[5] = reported price
        reported_price = _parse_value(clean[5])

        # Cell[6] = value
        value = _parse_value(clean[6])

        holdings.append({
            "ticker": ticker,
            "company": company,
            "pct_portfolio": pct,
            "activity": activity,
            "shares": shares,
            "value": value,
            "reported_price": reported_price,
        })

    return holdings, guru_name, q


def cmd_gurus(args):
    """Handle 'gurus' command."""
    if args.list_gurus:
        print("\n  Available gurus (default set):")
        for code, name in DEFAULT_GURUS.items():
            print(f"    {code:10s}  {name}")
        print(f"\n  Full list at: {DATAROMA_BASE}/home.php")
        return

    guru_codes = args.codes if args.codes else list(DEFAULT_GURUS.keys())

    with VaultDB() as db:
        for code in guru_codes:
            # Check cache
            cached = db.get_guru_holdings(guru_code=code)
            if cached and not args.no_cache:
                try:
                    cached_at = datetime.fromisoformat(cached[0]["cached_at"])
                except (ValueError, TypeError):
                    cached_at = None  # Treat as expired cache
                if cached_at is None:
                    age_days = float("inf")
                else:
                    age_days = (datetime.now() - cached_at).total_seconds() / 86400
                if age_days < 7:  # Cache for 7 days (quarterly data)
                    name = cached[0]["guru_name"]
                    print(f"\n  {name} ({code}) — {len(cached)} holdings (cached)")
                    _print_guru_top(cached[:10])
                    continue

            print(f"\n  Fetching {DEFAULT_GURUS.get(code, code)}...")
            holdings, guru_name, quarter = fetch_guru_holdings(code)

            if holdings:
                db.cache_guru_holdings(code, guru_name, holdings, quarter)
                print(f"  {guru_name} — {len(holdings)} holdings ({quarter})")
                _print_guru_top(holdings[:10])
            else:
                print(f"  No holdings found for {code}")


def _print_guru_top(holdings):
    """Print top holdings for a guru."""
    for h in holdings:
        ticker = h["ticker"] if isinstance(h, dict) else h["ticker"]
        company = (h.get("company", "") if isinstance(h, dict)
                   else h["company"] or "")
        pct = (h.get("pct_portfolio", 0) if isinstance(h, dict)
               else h["pct_portfolio"] or 0)
        activity = (h.get("activity", "") if isinstance(h, dict)
                    else h["activity"] or "")

        act_str = f"  [{activity}]" if activity else ""
        print(f"    {ticker:6s}  {pct:6.2f}%  {company[:30]}{act_str}")


# ═══════════════════════════════════════════════════════════════════
# Consensus / Full check
# ═══════════════════════════════════════════════════════════════════

def cmd_consensus(args):
    """Show tickers held by multiple gurus."""
    min_gurus = args.min or 2

    with VaultDB() as db:
        results = db.get_guru_consensus(min_gurus=min_gurus)

    if not results:
        print("\n  No consensus picks found. Run 'smart_money.py gurus' first.")
        return

    print(f"\n{'═' * 60}")
    print(f"  GURU CONSENSUS (held by {min_gurus}+ superinvestors)")
    print(f"{'═' * 60}")

    for r in results:
        print(f"\n  {r['ticker']:6s}  {r['guru_count']} gurus  avg {r['avg_pct']:.1f}%")
        print(f"    {r['gurus']}")


def cmd_check(args):
    """Full smart money check for a single ticker."""
    ticker = args.ticker.upper()

    print(f"\n{'═' * 60}")
    print(f"  SMART MONEY CHECK: {ticker}")
    print(f"{'═' * 60}")

    with VaultDB() as db:
        # 1. ARK activity
        ark = db.get_ark_conviction(ticker)
        print(f"\n  ARK Invest:")
        if ark['buy_count'] or ark['sell_count']:
            print(f"    {ark['net_direction']} — "
                  f"{ark['buy_count']} buys ({ark['buy_shares']:,} shares), "
                  f"{ark['sell_count']} sells ({ark['sell_shares']:,} shares)")
        else:
            print(f"    No ARK trades on record")

        # 2. Guru holdings
        guru_rows = db.get_guru_holdings(ticker=ticker)
        print(f"\n  Superinvestors:")
        if guru_rows:
            for g in guru_rows:
                act = f" [{g['activity']}]" if g['activity'] else ""
                print(f"    {g['guru_name']:20s}  {g['pct_portfolio'] or 0:.1f}%{act}")
        else:
            print(f"    Not held by any tracked guru")

        # 3. 13F institutional (existing)
        holders = db.ticker_held_by(ticker)
        print(f"\n  13F Institutional:")
        if holders:
            for h in holders:
                print(f"    {h['fund']:25s}  {h['pct_portfolio']:.1f}%")
        else:
            print(f"    Not in tracked 13F filings")

        # 4. Insider buys (existing)
        insider = db.get_insider_buys(ticker, days=90)
        print(f"\n  Insider Buying (90 days):")
        if insider:
            for i in insider:
                print(f"    {i['filed_date']}  {i['insider_name']}  "
                      f"${i['total_value']:,.0f}")
        else:
            print(f"    No insider purchases")

        # 5. Overall signal
        signals = []
        if ark['buy_count'] > ark['sell_count']:
            signals.append("ARK accumulating")
        if len(guru_rows) >= 2:
            signals.append(f"{len(guru_rows)} superinvestors hold")
        if len(holders) >= 2:
            signals.append(f"{len(holders)} top funds hold (13F)")
        if len(insider) >= 1:
            signals.append(f"{len(insider)} insider buys")

        strength = ("STRONG" if len(signals) >= 3 else
                    "MODERATE" if len(signals) >= 2 else
                    "WEAK" if len(signals) >= 1 else "NONE")

        print(f"\n  {'─' * 40}")
        print(f"  SIGNAL: {strength}")
        for s in signals:
            print(f"    + {s}")


# ── CLI ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Smart Money Tracker — ARK, Gurus, 13F, Insiders")
    parser.add_argument("--no-cache", action="store_true",
                        help="Force fresh fetch")
    sub = parser.add_subparsers(dest="command")

    # ark
    ark_p = sub.add_parser("ark", help="ARK Invest daily trades")
    ark_p.add_argument("--days", type=int, default=7)
    ark_p.add_argument("--ticker", type=str)
    ark_p.add_argument("--direction", choices=["Buy", "Sell"])
    ark_p.add_argument("--no-cache", action="store_true")

    # gurus
    guru_p = sub.add_parser("gurus", help="Superinvestor holdings")
    guru_p.add_argument("codes", nargs="*", help="Guru codes (e.g. BRK psc)")
    guru_p.add_argument("--list", dest="list_gurus", action="store_true",
                        help="List available gurus")
    guru_p.add_argument("--no-cache", action="store_true")

    # consensus
    cons_p = sub.add_parser("consensus", help="Guru consensus picks")
    cons_p.add_argument("--min", type=int, default=2,
                        help="Min gurus holding (default 2)")

    # check
    check_p = sub.add_parser("check", help="Full smart money check")
    check_p.add_argument("ticker", help="Ticker to check")

    args = parser.parse_args()

    if args.command == "ark":
        cmd_ark(args)
    elif args.command == "gurus":
        cmd_gurus(args)
    elif args.command == "consensus":
        cmd_consensus(args)
    elif args.command == "check":
        cmd_check(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
