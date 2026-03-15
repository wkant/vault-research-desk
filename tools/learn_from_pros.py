#!/usr/bin/env python3
"""
learn_from_pros.py — Real smart money learning engine

Fetches data from 5 professional sources, cross-references against
YOUR portfolio, detects changes, and saves actionable learnings to vault.db.

Sources:
  1. SEC 13F filings (16 hedge funds — quarterly)
  2. ARK Invest daily trades (arkfunds.io — daily)
  3. Superinvestor holdings (Dataroma — quarterly)
  4. Analyst recommendations (Finnhub — monthly)
  5. Insider transactions (Finnhub — daily)

What it actually does:
  - Cross-references all signals against your holdings and watchlist
  - Detects ARK accumulation/distribution patterns
  - Detects guru buys/sells/additions
  - Detects cluster insider buying (strongest public signal)
  - Finds new candidates with multi-source support
  - Saves everything to vault.db learnings table for report consumption

Usage:
    python3 tools/learn_from_pros.py              # fetch + analyze + save learnings
    python3 tools/learn_from_pros.py --analyze    # analyze cached data only (no fetch)
    python3 tools/learn_from_pros.py --summary    # show latest learnings
    python3 tools/learn_from_pros.py --cleanup    # clear learnings from DB
"""

import json
import os
import sys
import re
import time
import gzip
import argparse
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from xml.etree import ElementTree as ET
from collections import defaultdict, Counter
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from db import VaultDB

ROOT = Path(__file__).resolve().parent.parent

# ── Top funds to study (SEC EDGAR CIK numbers) ──────────────────────
FUNDS = {
    # Original 8
    "Berkshire Hathaway": "1067983",
    "Bridgewater Associates": "1350694",
    "Renaissance Technologies": "1037389",
    "Pershing Square": "1336528",
    "Soros Fund Management": "1029160",
    "Appaloosa Management": "1656456",
    "Citadel Advisors": "1423053",
    "Two Sigma": "1179392",
    # Added 8
    "Duquesne Family Office": "1536411",      # Druckenmiller
    "Tiger Global": "1167483",
    "Baupost Group": "1061768",               # Klarman
    "Third Point": "1040273",                 # Loeb
    "Coatue Management": "1135730",
    "Viking Global": "1103804",
    "Lone Pine Capital": "1061165",
    "Greenlight Capital": "1079114",           # Einhorn
}

HEADERS = {
    "User-Agent": "VaultResearchDesk research@vaultresearch.local",
    "Accept": "application/json",
}


# ── SEC EDGAR Fetching ──────────────────────────────────────────────

def _read_response(resp) -> bytes:
    """Read response, handling gzip encoding."""
    raw = resp.read()
    try:
        return gzip.decompress(raw)
    except (gzip.BadGzipFile, OSError):
        return raw


def fetch_filing_list(cik: str) -> dict:
    """Fetch filing index from SEC EDGAR."""
    cik_padded = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=20) as resp:
            return json.loads(_read_response(resp))
    except (URLError, HTTPError) as e:
        print(f"  Warning: Failed to fetch {url}: {e}")
        return {}


def find_latest_13f(data: dict) -> tuple:
    """Find the latest 13F-HR filing from submission data."""
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])

    for i, form in enumerate(forms):
        if "13F" in form and ("HR" in form or "NT" not in form):
            return accessions[i], dates[i]
    return None, None


def fetch_13f_holdings(cik: str, accession: str) -> list:
    """Fetch and parse 13F holdings from XML InfoTable."""
    acc_clean = accession.replace("-", "")
    index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/"
    req = Request(index_url, headers=HEADERS)

    try:
        with urlopen(req, timeout=20) as resp:
            index_html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    Warning: Failed to fetch filing index: {e}")
        return []

    # Find XML files — SEC uses absolute paths in href attributes
    xml_matches = re.findall(r'href="(/Archives/[^"]*\.xml)"', index_html, re.IGNORECASE)

    if not xml_matches:
        # Try relative paths too
        xml_matches = re.findall(r'href="([^"]*\.xml)"', index_html)

    if not xml_matches:
        print("    Warning: No XML files found in filing")
        return []

    # Filter: InfoTable XML is NOT primary_doc.xml — it's the holdings data
    # Try files with "infotable" in name first, then non-primary XMLs
    infotable = [f for f in xml_matches if "infotable" in f.lower()]
    non_primary = [f for f in xml_matches if "primary_doc" not in f.lower()]

    target_files = infotable or non_primary or xml_matches

    for xml_path in target_files:
        # Build full URL
        if xml_path.startswith("/"):
            xml_url = f"https://www.sec.gov{xml_path}"
        else:
            xml_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{xml_path}"

        req = Request(xml_url, headers=HEADERS)
        try:
            with urlopen(req, timeout=20) as resp:
                xml_data = resp.read()
        except Exception as e:
            print(f"    Warning: Failed to fetch {xml_path}: {e}")
            continue

        holdings = parse_13f_xml(xml_data)
        if holdings:
            return holdings

    print("    Warning: No holdings parsed from any XML file")
    return []


def parse_13f_xml(xml_data: bytes) -> list:
    """Parse 13F InfoTable XML into holdings list."""
    holdings = []
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError:
        return []

    # Handle XML namespace
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    for info in root.iter(f"{ns}infoTable"):
        holding = {}
        for child in info:
            tag = child.tag.replace(ns, "")
            if tag == "nameOfIssuer":
                holding["name"] = (child.text or "").strip()
            elif tag == "titleOfClass":
                holding["class"] = (child.text or "").strip()
            elif tag == "cusip":
                holding["cusip"] = (child.text or "").strip()
            elif tag == "value":
                try:
                    holding["value"] = int(child.text or 0)
                except ValueError:
                    holding["value"] = 0
            elif tag == "shrsOrPrnAmt":
                for sub in child:
                    subtag = sub.tag.replace(ns, "")
                    if subtag == "sshPrnamt":
                        try:
                            holding["shares"] = int(sub.text or 0)
                        except ValueError:
                            holding["shares"] = 0
                    elif subtag == "sshPrnamtType":
                        holding["share_type"] = sub.text or ""
            elif tag == "putCall":
                holding["put_call"] = child.text or ""

        if holding.get("value"):
            holdings.append(holding)

    return holdings


# ── Analysis ────────────────────────────────────────────────────────

def analyze_fund(name: str, holdings: list, filing_date: str = "") -> dict:
    """Analyze a single fund's holdings for patterns."""
    if not holdings:
        return {}

    total_value = sum(h["value"] for h in holdings)
    sorted_h = sorted(holdings, key=lambda x: x["value"], reverse=True)

    top5_value = sum(h["value"] for h in sorted_h[:5])
    top10_value = sum(h["value"] for h in sorted_h[:10])

    return {
        "name": name,
        "filing_date": filing_date,
        "total_value_millions": round(total_value / 1000, 1),
        "num_positions": len(holdings),
        "top5_pct": round(top5_value / total_value * 100, 1) if total_value else 0,
        "top10_pct": round(top10_value / total_value * 100, 1) if total_value else 0,
        "largest_position_pct": round(sorted_h[0]["value"] / total_value * 100, 1) if total_value else 0,
        "largest_position": sorted_h[0]["name"] if sorted_h else "",
        "avg_position_pct": round(100 / len(holdings), 2) if holdings else 0,
        "top10": [(h["name"], round(h["value"] / total_value * 100, 1)) for h in sorted_h[:10]],
    }


def quarter_from_date(filing_date: str) -> str:
    """Derive quarter string from filing date (e.g. '2026-02-17' -> 'Q4-2025')."""
    if not filing_date:
        return "Q4-2025"
    try:
        d = datetime.strptime(filing_date, "%Y-%m-%d")
        # 13F filings are for the PREVIOUS quarter
        # Filed in Feb = Q4 of previous year, May = Q1, Aug = Q2, Nov = Q3
        month = d.month
        year = d.year
        if month <= 4:     # Filed Jan-Apr = Q4 of prior year
            return f"Q4-{year - 1}"
        elif month <= 7:   # Filed May-Jul = Q1 of current year
            return f"Q1-{year}"
        elif month <= 10:  # Filed Aug-Oct = Q2 of current year
            return f"Q2-{year}"
        else:              # Filed Nov-Dec = Q3 of current year
            return f"Q3-{year}"
    except ValueError:
        return "Q4-2025"


# ── REAL LEARNING ENGINE ────────────────────────────────────────────
# Replaces fake static improvements with portfolio-specific, data-driven insights
# that change every run based on what smart money is actually doing.


from db import TICKER_COMPANY, COMPANY_TICKER


def _ticker_from_name(company_name: str) -> str:
    """Try to resolve a company name to a ticker symbol."""
    name_upper = (company_name or "").upper().strip()
    if name_upper in COMPANY_TICKER:
        return COMPANY_TICKER[name_upper]
    # Fuzzy match: check if company name starts with any known name
    for known_name, ticker in COMPANY_TICKER.items():
        if name_upper.startswith(known_name.split()[0]) and len(known_name.split()[0]) > 3:
            return ticker
    return ""


def cross_reference_portfolio(db) -> list:
    """Cross-reference ALL smart money signals against portfolio holdings.
    Returns list of learning dicts ready to save."""

    learnings = []
    today = datetime.now().strftime("%Y-%m-%d")
    holdings = db.get_holdings()
    portfolio_tickers = {h["ticker"] for h in holdings}

    # Also get active watchlist
    watchlist = db.get_active_watchlist()
    watchlist_tickers = {w["ticker"] for w in watchlist}

    # Gather all tickers we care about
    all_tickers = portfolio_tickers | watchlist_tickers

    for ticker in sorted(all_tickers):
        signals = []
        signal_data = {}
        bullish_count = 0
        bearish_count = 0

        relevance = "HOLDING" if ticker in portfolio_tickers else "WATCHLIST"

        # 1. Institutional 13F consensus
        holders = db.ticker_held_by(ticker)
        if holders:
            fund_names = [h["fund"] for h in holders]
            avg_pct = sum(h["pct_portfolio"] or 0 for h in holders) / len(holders)
            signals.append(f"Held by {len(holders)} institutional funds ({', '.join(fund_names[:3])}{'...' if len(fund_names) > 3 else ''})")
            signal_data["13f_funds"] = fund_names
            signal_data["13f_avg_pct"] = round(avg_pct, 2)
            if len(holders) >= 3:
                bullish_count += 2
            elif len(holders) >= 1:
                bullish_count += 1

        # 2. ARK conviction
        ark = db.get_ark_conviction(ticker)
        if ark and (ark["buy_count"] or ark["sell_count"]):
            if ark["buy_count"] >= 3:
                signals.append(f"ARK accumulating: {ark['buy_count']} buys ({ark['buy_shares']:,} shares)")
                bullish_count += 2
            elif ark["buy_count"] > ark["sell_count"]:
                signals.append(f"ARK net buying: {ark['buy_count']} buys vs {ark['sell_count']} sells")
                bullish_count += 1
            elif ark["sell_count"] > ark["buy_count"]:
                signals.append(f"ARK distributing: {ark['sell_count']} sells vs {ark['buy_count']} buys")
                bearish_count += 1
            signal_data["ark"] = ark

        # 3. Guru holdings
        guru_holdings = db.get_guru_holdings(ticker=ticker)
        if guru_holdings:
            guru_names = list(set(h["guru_name"] for h in guru_holdings))
            activities = [h["activity"] for h in guru_holdings if h["activity"]]
            signals.append(f"Held by {len(guru_names)} gurus ({', '.join(guru_names[:3])})")
            signal_data["gurus"] = guru_names
            # Check if any are adding
            adding = [a for a in activities if a and ("Buy" in a or "Add" in a)]
            reducing = [a for a in activities if a and ("Sell" in a or "Reduce" in a)]
            if adding:
                bullish_count += 1
            if reducing:
                bearish_count += 1
            else:
                bullish_count += 1  # holding = mild bullish

        # 4. Insider activity
        insider_buys = db.get_insider_buys(ticker, days=90)
        insider_sells_raw = db.conn.execute("""
            SELECT * FROM insider_txns
            WHERE ticker=? AND txn_type='SELL'
              AND txn_date >= date('now', '-90 days')
        """, (ticker,)).fetchall()

        if insider_buys:
            buy_value = sum(b["value"] or 0 for b in insider_buys)
            buy_names = list(set(b["insider_name"] or "unknown" for b in insider_buys))
            signals.append(f"{len(insider_buys)} insider buys (${buy_value:,.0f} by {', '.join(buy_names[:2])})")
            signal_data["insider_buys"] = len(insider_buys)
            signal_data["insider_buy_value"] = buy_value
            bullish_count += 2  # insider buying is a strong signal

        if len(insider_sells_raw) > 20:
            sell_names = list(set(s["insider_name"] or "unknown" for s in insider_sells_raw))
            if len(sell_names) >= 3:
                # Mega-cap tech insiders sell routinely (10b5-1 plans, tax, diversification)
                # Only flag as bearish if NOT strongly supported by institutions
                is_mega_cap = len(holders) >= 5 if holders else False
                if is_mega_cap:
                    signals.append(f"Insider selling: {len(insider_sells_raw)} sales by {len(sell_names)} insiders (likely routine — mega-cap with {len(holders)} fund holders)")
                    signal_data["insider_routine_sell"] = True
                    # Don't count as bearish for mega-caps with strong institutional support
                else:
                    signals.append(f"Heavy insider selling: {len(insider_sells_raw)} sales by {len(sell_names)} insiders — cluster warning")
                    bearish_count += 2
                    signal_data["insider_cluster_sell"] = True
            else:
                signals.append(f"Insider selling: {len(insider_sells_raw)} transactions (likely routine)")
                signal_data["insider_routine_sell"] = True

        # Skip tickers with no signals
        if not signals:
            continue

        # Determine direction and strength
        net = bullish_count - bearish_count
        if net >= 3:
            direction, strength = "BULLISH", "STRONG"
        elif net >= 1:
            direction, strength = "BULLISH", "MODERATE"
        elif net <= -2:
            direction, strength = "BEARISH", "STRONG"
        elif net < 0:
            direction, strength = "BEARISH", "MODERATE"
        else:
            direction, strength = "MIXED", "MODERATE"

        detail = "; ".join(signals)
        learnings.append({
            "run_date": today,
            "category": "portfolio_signal",
            "ticker": ticker,
            "signal_type": "cross_source",
            "direction": direction,
            "strength": strength,
            "detail": detail,
            "data": signal_data,
            "relevance": relevance,
        })

        # Risk flag: bearish signals on a holding
        if relevance == "HOLDING" and direction == "BEARISH":
            learnings.append({
                "run_date": today,
                "category": "risk_flag",
                "ticker": ticker,
                "signal_type": "cross_source",
                "direction": "BEARISH",
                "strength": strength,
                "detail": f"WARNING: {ticker} shows bearish smart money signals while you hold it. {detail}",
                "data": signal_data,
                "relevance": "HOLDING",
            })

    return learnings


def find_new_candidates(db) -> list:
    """Find tickers with strong smart money support that aren't in portfolio or watchlist."""
    learnings = []
    today = datetime.now().strftime("%Y-%m-%d")

    holdings = db.get_holdings()
    watchlist = db.get_active_watchlist()
    owned = {h["ticker"] for h in holdings} | {w["ticker"] for w in watchlist}

    # Get consensus picks held by 3+ funds
    consensus = db.get_consensus(min_funds=3)
    for row in consensus:
        company_name = row["company_name"] or row["ticker"]
        ticker = _ticker_from_name(company_name) or row["ticker"]
        if ticker in owned or not ticker.isalpha():
            continue

        fund_count = row["fund_count"]
        funds = row["funds"] or ""
        avg_pct = row["avg_pct"] or 0

        # Check if ARK is also buying
        ark = db.get_ark_conviction(ticker)
        ark_signal = ""
        if ark and ark["buy_count"] >= 3:
            ark_signal = f", ARK accumulating ({ark['buy_count']} buys)"

        # Check guru consensus
        guru_holds = db.get_guru_holdings(ticker=ticker)
        guru_signal = ""
        if guru_holds:
            guru_names = list(set(h["guru_name"] for h in guru_holds))
            guru_signal = f", {len(guru_names)} gurus hold"

        # Insider buying?
        insider = db.get_insider_buys(ticker, days=90)
        insider_signal = ""
        if insider:
            insider_signal = f", {len(insider)} insider buys"

        signal_count = (1 if fund_count >= 3 else 0) + \
                       (1 if ark and ark["buy_count"] >= 3 else 0) + \
                       (1 if guru_holds else 0) + \
                       (1 if insider else 0)

        if signal_count < 2:
            continue  # Need at least 2 sources agreeing

        strength = "STRONG" if signal_count >= 3 else "MODERATE"

        detail = (f"{fund_count} institutional funds (avg {avg_pct:.1f}%)"
                  f"{ark_signal}{guru_signal}{insider_signal}")

        learnings.append({
            "run_date": today,
            "category": "new_candidate",
            "ticker": ticker,
            "signal_type": "cross_source",
            "direction": "BULLISH",
            "strength": strength,
            "detail": detail,
            "data": {"fund_count": fund_count, "funds": funds,
                     "signal_count": signal_count},
            "relevance": "NEW_CANDIDATE",
        })

    return learnings[:10]  # Top 10 candidates


def detect_ark_patterns(db) -> list:
    """Detect ARK accumulation/distribution patterns."""
    learnings = []
    today = datetime.now().strftime("%Y-%m-%d")

    trades = db.get_ark_trades(days=30)
    if not trades:
        return []

    # Group by ticker
    by_ticker = defaultdict(list)
    for t in trades:
        by_ticker[t["ticker"]].append(t)

    for ticker, ticker_trades in by_ticker.items():
        buys = [t for t in ticker_trades if t["direction"] == "Buy"]
        sells = [t for t in ticker_trades if t["direction"] == "Sell"]

        # Strong accumulation: 5+ buys
        if len(buys) >= 5:
            funds = list(set(t["fund"] for t in buys))
            learnings.append({
                "run_date": today,
                "category": "change_detected",
                "ticker": ticker,
                "signal_type": "ark",
                "direction": "BULLISH",
                "strength": "STRONG" if len(buys) >= 8 else "MODERATE",
                "detail": f"ARK heavy accumulation: {len(buys)} buys across {', '.join(funds)} in 30 days",
                "data": {"buy_count": len(buys), "sell_count": len(sells), "funds": funds},
                "relevance": "NEW_CANDIDATE",
            })
        # Strong distribution: 5+ sells
        elif len(sells) >= 5:
            funds = list(set(t["fund"] for t in sells))
            learnings.append({
                "run_date": today,
                "category": "change_detected",
                "ticker": ticker,
                "signal_type": "ark",
                "direction": "BEARISH",
                "strength": "STRONG" if len(sells) >= 8 else "MODERATE",
                "detail": f"ARK distributing: {len(sells)} sells across {', '.join(funds)} in 30 days",
                "data": {"buy_count": len(buys), "sell_count": len(sells), "funds": funds},
                "relevance": "NEW_CANDIDATE",
            })

    return learnings


def detect_guru_activity(db) -> list:
    """Detect guru buys/sells from activity field."""
    learnings = []
    today = datetime.now().strftime("%Y-%m-%d")

    all_gurus = db.get_guru_holdings()
    for h in all_gurus:
        activity = h["activity"] or ""
        if not activity:
            continue

        ticker = h["ticker"]
        guru = h["guru_name"]
        pct = h["pct_portfolio"] or 0

        if "Buy" in activity or "New" in activity:
            learnings.append({
                "run_date": today,
                "category": "change_detected",
                "ticker": ticker,
                "signal_type": "guru",
                "direction": "BULLISH",
                "strength": "STRONG" if pct >= 5 else "MODERATE",
                "detail": f"{guru} — {activity} (now {pct:.1f}% of portfolio)",
                "data": {"guru": guru, "activity": activity, "pct": pct},
                "relevance": "NEW_CANDIDATE",
            })
        elif "Reduce" in activity or "Sell" in activity:
            learnings.append({
                "run_date": today,
                "category": "change_detected",
                "ticker": ticker,
                "signal_type": "guru",
                "direction": "BEARISH",
                "strength": "MODERATE",
                "detail": f"{guru} — {activity} (now {pct:.1f}% of portfolio)",
                "data": {"guru": guru, "activity": activity, "pct": pct},
                "relevance": "NEW_CANDIDATE",
            })

    return learnings


def detect_insider_clusters(db) -> list:
    """Detect cluster insider buying (strongest signal)."""
    learnings = []
    today = datetime.now().strftime("%Y-%m-%d")

    clusters = db.get_cluster_buys(days=90, min_insiders=2)
    for c in clusters:
        ticker = c["ticker"]
        num = c["num_insiders"]
        value = c["total_value"] or 0
        learnings.append({
            "run_date": today,
            "category": "change_detected",
            "ticker": ticker,
            "signal_type": "insider",
            "direction": "BULLISH",
            "strength": "STRONG",
            "detail": f"Cluster insider buying: {num} insiders bought ${value:,.0f} in 90 days ({c['first_buy']} to {c['last_buy']})",
            "data": {"num_insiders": num, "total_value": value},
            "relevance": "NEW_CANDIDATE",
        })

    return learnings


def save_learnings(db, all_learnings: list) -> int:
    """Save all learnings to DB, clearing previous unconsumed ones."""
    today = datetime.now().strftime("%Y-%m-%d")
    db.clear_learnings(run_date=today)

    saved = 0
    for l in all_learnings:
        db.add_learning(
            run_date=l["run_date"],
            category=l["category"],
            detail=l["detail"],
            ticker=l.get("ticker"),
            signal_type=l.get("signal_type"),
            direction=l.get("direction"),
            strength=l.get("strength"),
            data=l.get("data"),
            relevance=l.get("relevance"),
        )
        saved += 1

    return saved


# Keep extract_patterns for Step 1 display (but it no longer generates improvements)
def extract_patterns(analyses: list, extra_data: dict = None) -> dict:
    """Extract common patterns across ALL data sources (not just 13F)."""
    extra = extra_data or {}
    valid = [a for a in analyses if a]
    if not valid:
        return {}

    avg_positions = sum(a["num_positions"] for a in valid) / len(valid)
    avg_top5 = sum(a["top5_pct"] for a in valid) / len(valid)
    avg_top10 = sum(a["top10_pct"] for a in valid) / len(valid)
    avg_largest = sum(a["largest_position_pct"] for a in valid) / len(valid)

    # Most common holdings across funds
    all_holdings = Counter()
    for a in valid:
        for name, pct in a["top10"]:
            all_holdings[name] += 1

    consensus = [(name, count) for name, count in all_holdings.most_common(20) if count >= 2]

    min_pos = min(a["num_positions"] for a in valid)
    max_pos = max(a["num_positions"] for a in valid)

    concentrated = [a["name"] for a in valid if a["top5_pct"] > 50]
    diversified = [a["name"] for a in valid if a["num_positions"] > 500]

    result = {
        "num_funds": len(valid),
        "avg_positions": round(avg_positions),
        "position_range": (min_pos, max_pos),
        "avg_top5_concentration": round(avg_top5, 1),
        "avg_top10_concentration": round(avg_top10, 1),
        "avg_largest_position": round(avg_largest, 1),
        "consensus_holdings": consensus,
        "concentrated_funds": concentrated,
        "diversified_funds": diversified,
        "fund_details": valid,
    }

    # Merge extra data sources into patterns
    if extra.get("ark_trades"):
        trades = extra["ark_trades"]
        buys = [t for t in trades if t.get("direction") == "Buy"]
        sells = [t for t in trades if t.get("direction") == "Sell"]
        buy_tickers = Counter(t["ticker"] for t in buys)
        sell_tickers = Counter(t["ticker"] for t in sells)
        result["ark"] = {
            "total_trades": len(trades),
            "buys": len(buys),
            "sells": len(sells),
            "top_buys": buy_tickers.most_common(10),
            "top_sells": sell_tickers.most_common(10),
            "net_direction": "ACCUMULATING" if len(buys) > len(sells) else "DISTRIBUTING" if len(sells) > len(buys) else "NEUTRAL",
        }

    if extra.get("analyst_summary"):
        result["analyst"] = extra["analyst_summary"]

    if extra.get("insider_summary"):
        result["insider"] = extra["insider_summary"]

    if extra.get("guru_data"):
        result["gurus"] = extra["guru_data"]

    return result


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Learn from pros — real smart money analysis")
    parser.add_argument("--analyze", action="store_true", help="Analyze cached data only (no fetch)")
    parser.add_argument("--summary", action="store_true", help="Show latest learnings summary")
    parser.add_argument("--cleanup", action="store_true", help="Clear learning data from DB")
    args = parser.parse_args()

    if args.summary:
        with VaultDB() as db:
            print(db.get_learnings_summary())
        return

    if args.cleanup:
        with VaultDB() as db:
            db.conn.execute("DELETE FROM learnings")
            db.conn.commit()
            print("Cleared all learnings from vault.db")
        return

    all_analyses = []

    if not args.analyze:
        # ── STEP 1: Fetch 13F data from SEC EDGAR ───────────────
        print("=" * 60)
        print("STEP 1: Fetching 13F data from SEC EDGAR")
        print("=" * 60)

        for fund_name, cik in FUNDS.items():
            print(f"\n  {fund_name} (CIK: {cik})")

            # Check DB cache
            with VaultDB() as db:
                cached = db.reconstruct_fund_analysis(fund_name)
            if cached:
                print("    Using cached data from vault.db")
                all_analyses.append(cached)
                continue

            # Fetch filing list
            print("    Fetching filing list...")
            data = fetch_filing_list(cik)
            if not data:
                continue

            # Find latest 13F
            accession, filing_date = find_latest_13f(data)
            if not accession:
                print("    Warning: No 13F-HR filing found")
                continue

            print(f"    Latest 13F: {filing_date} ({accession})")
            quarter = quarter_from_date(filing_date)

            # Fetch holdings
            print("    Fetching holdings...")
            time.sleep(0.15)  # SEC rate limit
            holdings = fetch_13f_holdings(cik, accession)

            if not holdings:
                print("    Warning: No holdings parsed")
                continue

            print(f"    Found {len(holdings)} positions")

            # Analyze
            analysis = analyze_fund(fund_name, holdings, filing_date)
            all_analyses.append(analysis)

            # Persist to DB
            total_value = sum(h["value"] for h in holdings)
            with VaultDB() as db:
                db.add_fund(
                    name=fund_name,
                    quarter=quarter,
                    portfolio_value=analysis.get("total_value_millions"),
                    num_positions=analysis.get("num_positions"),
                    top5_conc=analysis.get("top5_pct"),
                    top10_conc=analysis.get("top10_pct"),
                    filing_date=filing_date,
                )
                for h in holdings:
                    db.add_institutional(
                        fund=fund_name,
                        ticker=h.get("name", ""),
                        company_name=h.get("name", ""),
                        shares=h.get("shares"),
                        value=h.get("value"),
                        pct_portfolio=round(h["value"] / total_value * 100, 2) if total_value else 0,
                        quarter=quarter,
                        filing_date=filing_date,
                    )

            time.sleep(0.15)

        # ── STEP 1b: Fetch ARK daily trades ───────────────────
        print("\n" + "=" * 60)
        print("STEP 1b: Fetching ARK Invest daily trades")
        print("=" * 60)
        try:
            from smart_money import fetch_all_ark_trades
            ark_trades = fetch_all_ark_trades(days=30)
            if ark_trades:
                with VaultDB() as db:
                    db.cache_ark_trades(ark_trades)
                ark_buys = [t for t in ark_trades if t.get("direction") == "Buy"]
                ark_sells = [t for t in ark_trades if t.get("direction") == "Sell"]
                buy_tickers = Counter(t["ticker"] for t in ark_buys)
                sell_tickers = Counter(t["ticker"] for t in ark_sells)
                print(f"\n  Total: {len(ark_trades)} trades (30 days)")
                print(f"  Buys: {len(ark_buys)} | Sells: {len(ark_sells)}")
                if buy_tickers:
                    print(f"  Top buys: {', '.join(f'{t}({c})' for t, c in buy_tickers.most_common(5))}")
                if sell_tickers:
                    print(f"  Top sells: {', '.join(f'{t}({c})' for t, c in sell_tickers.most_common(5))}")
            else:
                print("  No ARK trades fetched")
        except Exception as e:
            print(f"  ARK fetch error: {e}")

        # ── STEP 1c: Fetch Guru holdings (Dataroma) ───────────
        print("\n" + "=" * 60)
        print("STEP 1c: Fetching superinvestor holdings (Dataroma)")
        print("=" * 60)
        try:
            from smart_money import fetch_guru_holdings, DEFAULT_GURUS
            guru_count = 0
            with VaultDB() as db:
                for code, name in DEFAULT_GURUS.items():
                    cached = db.get_guru_holdings(guru_code=code)
                    if cached:
                        cached_at = datetime.fromisoformat(cached[0]["cached_at"])
                        age_days = (datetime.now() - cached_at).total_seconds() / 86400
                        if age_days < 7:
                            guru_count += 1
                            print(f"  {name}: {len(cached)} holdings (cached)")
                            continue

                    holdings_data, guru_name, quarter = fetch_guru_holdings(code)
                    if holdings_data:
                        db.cache_guru_holdings(code, guru_name or name, holdings_data, quarter)
                        guru_count += 1
                        print(f"  {guru_name or name}: {len(holdings_data)} holdings ({quarter})")
                    else:
                        print(f"  {name}: no data")
                    time.sleep(0.5)
            print(f"\n  Total gurus: {guru_count}")
        except Exception as e:
            print(f"  Guru fetch error: {e}")

        # ── STEP 1d: Fetch Analyst Recommendations (Finnhub) ──
        print("\n" + "=" * 60)
        print("STEP 1d: Fetching analyst recommendations (Finnhub)")
        print("=" * 60)
        try:
            from news import _load_api_keys
            keys = _load_api_keys()
            finnhub_key = os.environ.get("FINNHUB_API_KEY") or keys.get("FINNHUB_API_KEY", "")
            if finnhub_key:
                with VaultDB() as db:
                    port_holdings = db.get_holdings()
                port_tickers = [h["ticker"] for h in port_holdings]
                check_tickers = list(set(port_tickers + ["XOM", "NVDA", "AMZN", "MSFT", "AAPL", "META", "LMT", "XLU"]))

                from urllib.request import Request as Req, urlopen as uopen
                checked = 0
                for ticker in check_tickers:
                    try:
                        url = f"https://finnhub.io/api/v1/stock/recommendation?symbol={ticker}&token={finnhub_key}"
                        req = Req(url, headers={"Accept": "application/json"})
                        with uopen(req, timeout=10) as resp:
                            recs = json.loads(resp.read())
                        if recs:
                            r = recs[0]
                            bull = r.get('strongBuy', 0) + r.get('buy', 0)
                            bear = r.get('sell', 0) + r.get('strongSell', 0)
                            hold = r.get('hold', 0)
                            signal = 'BULLISH' if bull > bear else 'MIXED' if bull == bear else 'BEARISH'
                            print(f"  {ticker}: {bull} bullish / {hold} hold / {bear} bearish — {signal}")
                            checked += 1
                    except Exception:
                        pass
                print(f"\n  Checked {checked} tickers")
            else:
                print("  No FINNHUB_API_KEY — skipping")
        except Exception as e:
            print(f"  Analyst rec error: {e}")

        # ── STEP 1e: Fetch Insider Transactions (Finnhub) ─────
        print("\n" + "=" * 60)
        print("STEP 1e: Fetching insider transactions (Finnhub)")
        print("=" * 60)
        try:
            if finnhub_key:
                from urllib.request import Request as Req, urlopen as uopen
                insider_count = 0
                for ticker in check_tickers:
                    try:
                        from_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
                        to_date = datetime.now().strftime("%Y-%m-%d")
                        url = (f"https://finnhub.io/api/v1/stock/insider-transactions"
                               f"?symbol={ticker}&from={from_date}&to={to_date}&token={finnhub_key}")
                        req = Req(url, headers={"Accept": "application/json"})
                        with uopen(req, timeout=10) as resp:
                            data = json.loads(resp.read())
                        txns = data.get("data", [])
                        if txns:
                            buys = [t for t in txns if t.get("transactionCode") == "P"]
                            sells = [t for t in txns if t.get("transactionCode") == "S"]
                            if buys or sells:
                                # Save to DB
                                with VaultDB() as db:
                                    for txn in txns:
                                        code = txn.get("transactionCode", "")
                                        if code in ("P", "S"):
                                            db.add_insider_txn(
                                                ticker=ticker,
                                                insider_name=txn.get("name"),
                                                title=None,
                                                txn_type="BUY" if code == "P" else "SELL",
                                                shares=txn.get("share"),
                                                price=txn.get("transactionPrice"),
                                                value=abs((txn.get("share") or 0) * (txn.get("transactionPrice") or 0)),
                                                txn_date=txn.get("transactionDate"),
                                                filing_date=txn.get("filingDate"),
                                                source="finnhub",
                                            )
                                print(f"  {ticker}: {len(buys)} buys, {len(sells)} sells — "
                                      f"{'NET BUY' if len(buys) > len(sells) else 'NET SELL'}")
                                insider_count += 1
                    except Exception:
                        pass
                print(f"\n  Checked {len(check_tickers)} tickers, {insider_count} with activity")
            else:
                print("  No FINNHUB_API_KEY — skipping")
        except Exception as e:
            print(f"  Insider fetch error: {e}")

    else:
        # --analyze mode: load from DB
        print("Loading cached data from vault.db...")
        with VaultDB() as db:
            all_analyses = db.get_all_fund_analyses()
        print(f"  Loaded {len(all_analyses)} fund analyses")

    # ── STEP 2: Cross-reference with portfolio ─────────────────
    print("\n" + "=" * 60)
    print("STEP 2: Cross-referencing with your portfolio")
    print("=" * 60)

    # Rebuild consensus from 13F data
    with VaultDB() as db:
        db.rebuild_consensus()

    all_learnings = []

    with VaultDB() as db:
        # Portfolio cross-reference (the core learning)
        portfolio_signals = cross_reference_portfolio(db)
        all_learnings.extend(portfolio_signals)

        holdings_signals = [l for l in portfolio_signals if l["relevance"] == "HOLDING"]
        watchlist_signals = [l for l in portfolio_signals if l["relevance"] == "WATCHLIST"]

        print(f"\n  --- Your Holdings ---")
        for l in holdings_signals:
            tag = f"[{l['strength']} {l['direction']}]"
            print(f"  {l['ticker']} {tag}: {l['detail'][:100]}")

        if watchlist_signals:
            print(f"\n  --- Your Watchlist ---")
            for l in watchlist_signals:
                tag = f"[{l['strength']} {l['direction']}]"
                print(f"  {l['ticker']} {tag}: {l['detail'][:100]}")

        if not holdings_signals and not watchlist_signals:
            print("  No signals found for your portfolio. Add holdings to portfolio.md first.")

    # ── STEP 3: Detect changes and patterns ────────────────────
    print("\n" + "=" * 60)
    print("STEP 3: Detecting changes and patterns")
    print("=" * 60)

    with VaultDB() as db:
        # ARK accumulation/distribution patterns
        ark_patterns = detect_ark_patterns(db)
        all_learnings.extend(ark_patterns)
        if ark_patterns:
            print(f"\n  --- ARK Patterns ---")
            for l in ark_patterns:
                print(f"  {l['ticker']} [{l['direction']}]: {l['detail']}")

        # Guru activity (new buys, sells, additions)
        guru_changes = detect_guru_activity(db)
        all_learnings.extend(guru_changes)
        if guru_changes:
            print(f"\n  --- Guru Activity ---")
            for l in guru_changes[:10]:  # Show top 10
                print(f"  {l['ticker']} [{l['direction']}]: {l['detail']}")
            if len(guru_changes) > 10:
                print(f"  ... and {len(guru_changes) - 10} more")

        # Insider cluster buying
        insider_clusters = detect_insider_clusters(db)
        all_learnings.extend(insider_clusters)
        if insider_clusters:
            print(f"\n  --- Insider Cluster Buying ---")
            for l in insider_clusters:
                print(f"  {l['ticker']}: {l['detail']}")

        if not ark_patterns and not guru_changes and not insider_clusters:
            print("  No significant changes detected.")

    # ── STEP 4: Find new candidates ────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 4: New candidates (strong multi-source signals)")
    print("=" * 60)

    with VaultDB() as db:
        candidates = find_new_candidates(db)
        all_learnings.extend(candidates)

        if candidates:
            for l in candidates:
                print(f"  {l['ticker']} [{l['strength']}]: {l['detail']}")
        else:
            print("  No new candidates with multi-source support found.")

    # ── STEP 5: Save learnings to DB ───────────────────────────
    print("\n" + "=" * 60)
    print("STEP 5: Saving learnings to vault.db")
    print("=" * 60)

    with VaultDB() as db:
        saved = save_learnings(db, all_learnings)
        print(f"  Saved {saved} learnings to DB")

    # ── Summary ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("DONE — Learnings Summary")
    print("=" * 60)

    # Count by category
    by_cat = Counter(l["category"] for l in all_learnings)
    for cat, count in by_cat.most_common():
        print(f"  {cat}: {count}")

    # Count by direction
    bullish = sum(1 for l in all_learnings if l.get("direction") == "BULLISH")
    bearish = sum(1 for l in all_learnings if l.get("direction") == "BEARISH")
    mixed = sum(1 for l in all_learnings if l.get("direction") in ("MIXED", "NEUTRAL"))
    print(f"\n  Bullish: {bullish} | Bearish: {bearish} | Mixed: {mixed}")
    print(f"  Total: {len(all_learnings)} learnings")

    risk_flags = [l for l in all_learnings if l["category"] == "risk_flag"]
    if risk_flags:
        print(f"\n  ⚠ RISK FLAGS:")
        for r in risk_flags:
            print(f"    {r['ticker']}: {r['detail'][:80]}")

    print(f"\n  View full summary: python3 tools/learn_from_pros.py --summary")
    print(f"  Learnings feed into your next report automatically via vault.db")


if __name__ == "__main__":
    main()

