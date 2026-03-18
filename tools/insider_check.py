#!/usr/bin/env python3
"""
insider_check.py — Insider buying/selling checker

Fetches SEC EDGAR Form 4 filings to detect insider transactions
(CEO/CFO/Director purchases and sales) for given tickers.

CEO/CFO open-market purchases outperform the market by 4-8% annually
(Harvard Business School, 2022).

Usage:
    python3 tools/insider_check.py GOOGL AAPL NVDA   # check specific tickers
    python3 tools/insider_check.py --portfolio        # check all portfolio holdings

Standard library only — no pip dependencies.
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
from urllib.parse import quote
from xml.etree import ElementTree as ET

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from db import VaultDB

# ── Config ─────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "VaultResearchDesk research@vaultresearch.local",
    "Accept": "application/json",
}

REQUEST_DELAY = 0.15  # SEC rate limit: 10 req/sec
LOOKBACK_DAYS = 90

# Insider role classification
C_SUITE_TITLES = {"ceo", "chief executive officer", "cfo", "chief financial officer",
                  "coo", "chief operating officer", "cto", "chief technology officer",
                  "president", "chairman", "vice chairman"}

DIRECTOR_TITLES = {"director", "independent director", "lead independent director"}

# ── HTTP Helpers ───────────────────────────────────────────────────


def _read_response(resp) -> bytes:
    """Read response, handling gzip encoding."""
    raw = resp.read()
    try:
        return gzip.decompress(raw)
    except (gzip.BadGzipFile, OSError):
        return raw


def _fetch_url(url: str, accept: str = "application/json", timeout: int = 20) -> bytes:
    """Fetch a URL with proper headers and error handling."""
    headers = dict(HEADERS)
    headers["Accept"] = accept
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return _read_response(resp)
    except (URLError, HTTPError) as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}")


# ── CIK Lookup ────────────────────────────────────────────────────


def lookup_cik(ticker: str) -> tuple:
    """Look up company CIK number and name from ticker.

    Returns (cik_str, company_name) or (None, None) on failure.
    Uses the SEC company tickers JSON endpoint.
    """
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        data = json.loads(_fetch_url(url))
    except RuntimeError as e:
        print(f"  Warning: {e}")
        return None, None

    ticker_upper = ticker.upper()
    for entry in data.values():
        if entry.get("ticker", "").upper() == ticker_upper:
            cik = str(entry["cik_str"])
            name = entry.get("title", ticker_upper)
            return cik, name

    return None, None


# ── Form 4 Filing Discovery ───────────────────────────────────────


def fetch_recent_form4_filings(cik: str, days: int = LOOKBACK_DAYS) -> list:
    """Fetch recent Form 4 filings for a company from SEC EDGAR submissions.

    Returns list of dicts with keys: accessionNumber, filingDate, primaryDocument.
    """
    cik_padded = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"

    try:
        data = json.loads(_fetch_url(url))
    except RuntimeError as e:
        print(f"  Warning: {e}")
        return []

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    primary_docs = recent.get("primaryDocument", [])

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    filings = []

    for i, form in enumerate(forms):
        if form in ("4", "4/A") and i < len(dates) and dates[i] >= cutoff:
            filing = {
                "accessionNumber": accessions[i] if i < len(accessions) else "",
                "filingDate": dates[i],
                "primaryDocument": primary_docs[i] if i < len(primary_docs) else "",
            }
            filings.append(filing)

    return filings


# ── Form 4 XML Parsing ────────────────────────────────────────────


def fetch_and_parse_form4(cik: str, accession: str, primary_doc: str) -> list:
    """Fetch and parse a single Form 4 XML filing.

    Returns list of transaction dicts.
    """
    acc_clean = accession.replace("-", "")
    cik_clean = cik.lstrip("0") or "0"

    # Try primary document first (usually the XML)
    urls_to_try = []
    if primary_doc:
        urls_to_try.append(
            f"https://www.sec.gov/Archives/edgar/data/{cik_clean}/{acc_clean}/{primary_doc}"
        )
    # Also try common Form 4 XML naming
    urls_to_try.append(
        f"https://www.sec.gov/Archives/edgar/data/{cik_clean}/{acc_clean}/{accession}.xml"
    )

    xml_data = None
    for url in urls_to_try:
        try:
            xml_data = _fetch_url(url, accept="application/xml")
            break
        except RuntimeError:
            continue

    if not xml_data:
        return []

    return parse_form4_xml(xml_data)


def parse_form4_xml(xml_data: bytes) -> list:
    """Parse Form 4 XML into a list of transaction dicts.

    Each dict has: insider_name, insider_title, transaction_type (P/S/A/other),
    shares, price_per_share, total_value, transaction_date, is_direct.
    """
    transactions = []

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError:
        return []

    # Handle namespace
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    # Extract reporting person info
    insider_name = ""
    insider_titles = []

    # reportingOwner -> reportingOwnerId -> rptOwnerName
    for owner in root.iter(f"{ns}reportingOwner"):
        owner_id = owner.find(f"{ns}reportingOwnerId")
        if owner_id is not None:
            name_el = owner_id.find(f"{ns}rptOwnerName")
            if name_el is not None and name_el.text:
                insider_name = name_el.text.strip()

        # reportingOwnerRelationship
        rel = owner.find(f"{ns}reportingOwnerRelationship")
        if rel is not None:
            if _get_bool(rel, f"{ns}isOfficer"):
                title_el = rel.find(f"{ns}officerTitle")
                if title_el is not None and title_el.text:
                    insider_titles.append(title_el.text.strip())
                else:
                    insider_titles.append("Officer")
            if _get_bool(rel, f"{ns}isDirector"):
                insider_titles.append("Director")
            if _get_bool(rel, f"{ns}isTenPercentOwner"):
                insider_titles.append("10% Owner")
            if _get_bool(rel, f"{ns}isOther"):
                other_el = rel.find(f"{ns}otherText")
                if other_el is not None and other_el.text:
                    insider_titles.append(other_el.text.strip())

    insider_title = ", ".join(insider_titles) if insider_titles else "Unknown"

    # Parse non-derivative transactions
    for table in root.iter(f"{ns}nonDerivativeTable"):
        for txn in table.iter(f"{ns}nonDerivativeTransaction"):
            t = _parse_transaction(txn, ns, insider_name, insider_title)
            if t:
                transactions.append(t)

    # Parse derivative transactions (options exercises, etc.)
    for table in root.iter(f"{ns}derivativeTable"):
        for txn in table.iter(f"{ns}derivativeTransaction"):
            t = _parse_transaction(txn, ns, insider_name, insider_title, derivative=True)
            if t:
                t["is_derivative"] = True
                transactions.append(t)

    return transactions


def _get_bool(element, tag: str) -> bool:
    """Get boolean value from XML element."""
    el = element.find(tag)
    if el is not None and el.text:
        return el.text.strip() in ("1", "true", "True")
    return False


def _parse_transaction(txn, ns: str, insider_name: str, insider_title: str,
                       derivative: bool = False) -> dict:
    """Parse a single transaction element from Form 4 XML."""
    result = {
        "insider_name": insider_name,
        "insider_title": insider_title,
        "is_derivative": derivative,
    }

    # Transaction date
    date_el = txn.find(f".//{ns}transactionDate/{ns}value")
    if date_el is not None and date_el.text:
        result["transaction_date"] = date_el.text.strip()
    else:
        result["transaction_date"] = ""

    # Transaction code (P=Purchase, S=Sale, A=Award/Grant, M=Exercise, etc.)
    code_el = txn.find(f".//{ns}transactionCoding/{ns}transactionCode")
    if code_el is not None and code_el.text:
        result["transaction_code"] = code_el.text.strip()
    else:
        result["transaction_code"] = ""

    # Acquired or Disposed (A=acquired, D=disposed)
    ad_el = txn.find(f".//{ns}transactionAmounts/{ns}transactionAcquiredDisposedCode/{ns}value")
    if ad_el is not None and ad_el.text:
        result["acquired_disposed"] = ad_el.text.strip()
    else:
        result["acquired_disposed"] = ""

    # Number of shares
    shares_el = txn.find(f".//{ns}transactionAmounts/{ns}transactionShares/{ns}value")
    if shares_el is not None and shares_el.text:
        try:
            result["shares"] = float(shares_el.text.strip())
        except ValueError:
            result["shares"] = 0.0
    else:
        result["shares"] = 0.0

    # Price per share
    price_el = txn.find(f".//{ns}transactionAmounts/{ns}transactionPricePerShare/{ns}value")
    if price_el is not None and price_el.text:
        try:
            result["price_per_share"] = float(price_el.text.strip())
        except ValueError:
            result["price_per_share"] = 0.0
    else:
        result["price_per_share"] = 0.0

    result["total_value"] = result["shares"] * result["price_per_share"]

    # Direct or indirect ownership
    ownership_el = txn.find(f".//{ns}ownershipNature/{ns}directOrIndirectOwnership/{ns}value")
    if ownership_el is not None and ownership_el.text:
        result["is_direct"] = ownership_el.text.strip() == "D"
    else:
        result["is_direct"] = True

    return result


# ── Signal Analysis ────────────────────────────────────────────────


def classify_insider_role(title: str) -> str:
    """Classify insider role for signal strength."""
    title_lower = title.lower()
    for keyword in C_SUITE_TITLES:
        if keyword in title_lower:
            return "C_SUITE"
    for keyword in DIRECTOR_TITLES:
        if keyword in title_lower:
            return "DIRECTOR"
    if "10%" in title_lower or "owner" in title_lower:
        return "10PCT_OWNER"
    return "OTHER"


def is_open_market_purchase(txn: dict) -> bool:
    """Check if transaction is an open-market purchase (strongest signal)."""
    return (txn.get("transaction_code") == "P"
            and txn.get("acquired_disposed") == "A"
            and not txn.get("is_derivative", False))


def is_sale(txn: dict) -> bool:
    """Check if transaction is a sale."""
    return (txn.get("transaction_code") == "S"
            and txn.get("acquired_disposed") == "D")


def analyze_signal(transactions: list) -> dict:
    """Analyze all transactions for a ticker and determine signal strength.

    Returns dict with: signal, signal_detail, buyers, sellers, purchase_count, sale_count.
    """
    purchases = [t for t in transactions if is_open_market_purchase(t)]
    sales = [t for t in transactions if is_sale(t)]

    # Unique buyers by name
    buyer_names = set()
    c_suite_buyers = set()
    director_buyers = set()
    for t in purchases:
        name = t.get("insider_name", "")
        buyer_names.add(name)
        role = classify_insider_role(t.get("insider_title", ""))
        if role == "C_SUITE":
            c_suite_buyers.add(name)
        elif role == "DIRECTOR":
            director_buyers.add(name)

    seller_names = set()
    for t in sales:
        seller_names.add(t.get("insider_name", ""))

    # Determine signal
    signal = "NO DATA"
    signal_detail = "No insider transactions in last {days} days".format(days=LOOKBACK_DAYS)

    if not purchases and not sales:
        pass  # NO DATA
    elif purchases and not sales:
        if len(c_suite_buyers) >= 2:
            signal = "VERY STRONG BULLISH"
            signal_detail = "Multiple C-suite buying"
        elif len(buyer_names) >= 3:
            signal = "VERY STRONG BULLISH"
            signal_detail = f"{len(buyer_names)} insiders buying"
        elif c_suite_buyers:
            signal = "STRONG BULLISH"
            names = ", ".join(c_suite_buyers)
            signal_detail = f"C-suite purchase ({names})"
        elif director_buyers:
            signal = "MODERATE BULLISH"
            signal_detail = f"{len(director_buyers)} director(s) buying"
        elif len(buyer_names) >= 2:
            signal = "MODERATE BULLISH"
            signal_detail = f"{len(buyer_names)} insiders buying"
        else:
            signal = "MILD BULLISH"
            signal_detail = "Single insider purchase"
    elif not purchases and sales:
        if len(seller_names) >= 3:
            signal = "BEARISH WARNING"
            signal_detail = f"Cluster selling ({len(seller_names)} insiders)"
        else:
            signal = "NEUTRAL"
            signal_detail = "Insider selling (often routine/planned)"
    else:
        # Both purchases and sales
        if c_suite_buyers:
            signal = "STRONG BULLISH"
            signal_detail = "C-suite buying (despite some insider selling)"
        elif len(buyer_names) > len(seller_names):
            signal = "MODERATE BULLISH"
            signal_detail = "More buyers than sellers"
        elif len(seller_names) >= 3 and not purchases:
            signal = "BEARISH WARNING"
            signal_detail = f"Cluster selling ({len(seller_names)} insiders)"
        else:
            signal = "MIXED"
            signal_detail = f"{len(buyer_names)} buying, {len(seller_names)} selling"

    return {
        "signal": signal,
        "signal_detail": signal_detail,
        "purchase_count": len(purchases),
        "sale_count": len(sales),
        "unique_buyers": len(buyer_names),
        "unique_sellers": len(seller_names),
    }


# ── Transaction Display Helpers ────────────────────────────────────


def format_transaction_type(txn: dict) -> str:
    """Format transaction type for display."""
    code = txn.get("transaction_code", "")
    ad = txn.get("acquired_disposed", "")

    if code == "P" and ad == "A":
        return "BUY"
    elif code == "S" and ad == "D":
        return "SELL"
    elif code == "A":
        return "AWARD"
    elif code == "M":
        return "EXERCISE"
    elif code == "G":
        return "GIFT"
    elif code == "F":
        return "TAX"       # shares withheld for tax
    elif code == "J":
        return "OTHER"
    else:
        return code or "?"


def format_dollar(value: float) -> str:
    """Format dollar value for display."""
    if value >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    elif value >= 1_000:
        return f"${value:,.0f}"
    elif value > 0:
        return f"${value:,.2f}"
    else:
        return "$0"


def shorten_name(name: str) -> str:
    """Convert 'LAST FIRST MIDDLE' to 'First Last' format."""
    if not name:
        return "Unknown"
    parts = name.split()
    if len(parts) >= 2 and parts[0].isupper() and parts[1].isupper():
        # Likely "LAST FIRST" format
        return f"{parts[1].title()} {parts[0].title()}"
    return name.title()


def shorten_title(title: str) -> str:
    """Shorten insider title for display."""
    title_lower = title.lower()
    # Map common full titles to abbreviations
    abbreviations = [
        ("chief executive officer", "CEO"),
        ("chief financial officer", "CFO"),
        ("chief operating officer", "COO"),
        ("chief technology officer", "CTO"),
        ("chief information officer", "CIO"),
        ("chief legal officer", "CLO"),
        ("chief marketing officer", "CMO"),
        ("executive vice president", "EVP"),
        ("senior vice president", "SVP"),
        ("vice president", "VP"),
        ("general counsel", "GC"),
        ("10% owner", "10% Owner"),
        ("independent director", "Director"),
    ]
    result = title
    for long, short in abbreviations:
        if long in title_lower:
            result = result[:title_lower.index(long)] + short + result[title_lower.index(long) + len(long):]
            break
    # Truncate if still long
    if len(result) > 30:
        result = result[:27] + "..."
    return result


# ── Portfolio Reading ──────────────────────────────────────────────


def read_portfolio_tickers() -> list:
    """Read tickers from DB (primary), fallback to portfolio.md."""
    try:
        with VaultDB() as db:
            holdings = db.get_holdings()
            if holdings:
                return [r['ticker'] for r in holdings]
    except Exception:
        pass
    # Fallback: parse portfolio.md directly (in case DB not synced yet)
    portfolio_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "portfolio.md"
    )
    if not os.path.exists(portfolio_path):
        print(f"Error: portfolio.md not found at {portfolio_path}")
        sys.exit(1)

    tickers = []
    with open(portfolio_path, "r") as f:
        in_table = False
        for line in f:
            line = line.strip()
            if line.startswith("| Ticker"):
                in_table = True
                continue
            if in_table and line.startswith("|---"):
                continue
            if in_table and line.startswith("|"):
                cols = [c.strip() for c in line.split("|")]
                # cols[0] is empty (before first |), cols[1] is ticker
                if len(cols) >= 2 and cols[1]:
                    tickers.append(cols[1])
            elif in_table and not line.startswith("|"):
                in_table = False

    return tickers


# ── Main Check Logic ──────────────────────────────────────────────


def check_insider_activity(ticker: str, days: int = None) -> dict:
    """Check insider activity for a single ticker.

    Returns dict with: ticker, company_name, transactions, signal_analysis,
    error (if any).
    """
    result = {
        "ticker": ticker.upper(),
        "company_name": "",
        "transactions": [],
        "signal_analysis": None,
        "error": None,
    }

    # Step 1: Look up CIK
    cik, company_name = lookup_cik(ticker)
    if not cik:
        result["error"] = f"Could not find CIK for {ticker}"
        return result

    result["company_name"] = company_name
    time.sleep(REQUEST_DELAY)

    # Step 2: Get recent Form 4 filings
    _days = days or LOOKBACK_DAYS
    filings = fetch_recent_form4_filings(cik, days=_days)
    time.sleep(REQUEST_DELAY)

    if not filings:
        result["signal_analysis"] = {
            "signal": "NO DATA",
            "signal_detail": f"No Form 4 filings in last {_days} days",
            "purchase_count": 0,
            "sale_count": 0,
            "unique_buyers": 0,
            "unique_sellers": 0,
        }
        return result

    # Step 3: Parse Form 4 XML for each filing (limit to avoid hammering SEC)
    max_filings = 20  # Parse up to 20 most recent
    all_transactions = []

    for filing in filings[:max_filings]:
        acc = filing["accessionNumber"]
        primary = filing.get("primaryDocument", "")

        try:
            txns = fetch_and_parse_form4(cik, acc, primary)
            for t in txns:
                t["filing_date"] = filing["filingDate"]
            all_transactions.extend(txns)
        except Exception as e:
            print(f"  Warning: could not parse filing {acc}: {e}", file=sys.stderr)

        time.sleep(REQUEST_DELAY)

    # Deduplicate by (name, date, code, shares)
    seen = set()
    unique_txns = []
    for t in all_transactions:
        key = (t.get("insider_name", ""), t.get("transaction_date", ""),
               t.get("transaction_code", ""), t.get("shares", 0))
        if key not in seen:
            seen.add(key)
            unique_txns.append(t)

    # Sort by date descending
    unique_txns.sort(key=lambda x: x.get("transaction_date", ""), reverse=True)

    result["transactions"] = unique_txns
    result["signal_analysis"] = analyze_signal(unique_txns)

    # Save transactions to DB for historical tracking
    try:
        with VaultDB() as _db:
            for t in unique_txns:
                txn_type_map = {"P": "BUY", "S": "SELL", "A": "AWARD", "M": "EXERCISE"}
                _db.add_insider_txn(
                    ticker=ticker.upper(),
                    insider_name=t.get("insider_name"),
                    title=t.get("insider_title"),
                    txn_type=txn_type_map.get(t.get("transaction_code"), t.get("transaction_code", "")),
                    shares=t.get("shares"),
                    price=t.get("price_per_share"),
                    value=t.get("total_value"),
                    txn_date=t.get("transaction_date"),
                    filing_date=t.get("filing_date"),
                    source="SEC EDGAR Form 4",
                )
    except Exception as e:
        print(f"  Warning: could not save insider transactions to DB: {e}", file=sys.stderr)

    return result


# ── Output Formatting ─────────────────────────────────────────────


def print_report(results: list, days: int = None):
    """Print formatted insider activity report."""
    _days = days or LOOKBACK_DAYS
    print()
    print("\u2550" * 50)
    print("  INSIDER ACTIVITY CHECK")
    print("\u2550" * 50)
    cutoff_date = (datetime.now() - timedelta(days=_days)).strftime("%Y-%m-%d")
    print(f"  Period: {cutoff_date} to {datetime.now().strftime('%Y-%m-%d')} ({_days} days)")
    print()

    for r in results:
        ticker = r["ticker"]
        name = r["company_name"]
        header = f"{ticker} ({name})" if name else ticker

        if r.get("error"):
            print(f"  {header}:")
            print(f"    Error: {r['error']}")
            print()
            continue

        print(f"  {header}:")

        txns = r.get("transactions", [])
        signal = r.get("signal_analysis", {})

        if not txns:
            print(f"    No insider transactions in last {_days} days")
        else:
            # Filter to show only meaningful transactions (P and S)
            display_txns = [t for t in txns if t.get("transaction_code") in ("P", "S")]

            # If no P/S, show all with their codes
            if not display_txns:
                display_txns = txns[:15]

            for t in display_txns[:15]:  # Cap display at 15 rows
                date = t.get("transaction_date", "N/A")
                name_short = shorten_name(t.get("insider_name", ""))
                title = shorten_title(t.get("insider_title", ""))
                txn_type = format_transaction_type(t)
                shares = t.get("shares", 0)
                total = t.get("total_value", 0)

                # Format shares
                try:
                    import math
                    if math.isfinite(shares) and shares == int(shares):
                        shares_str = f"{int(shares):,}"
                    elif math.isfinite(shares):
                        shares_str = f"{shares:,.2f}"
                    else:
                        shares_str = "N/A"
                except (ValueError, TypeError, OverflowError):
                    shares_str = "N/A"

                # Build the line
                value_str = format_dollar(total) if total > 0 else ""
                role_str = f"({title})" if title else ""

                print(f"    {date}  {name_short:<22s} {role_str:<20s} "
                      f"{txn_type:<8s} {shares_str:>12s} shares  {value_str}")

            remaining = len(display_txns) - 15
            if remaining > 0:
                print(f"    ... and {remaining} more transactions")

        # Signal line
        sig = signal.get("signal", "NO DATA")
        detail = signal.get("signal_detail", "")

        # Color-code signal with simple markers
        if "BULLISH" in sig:
            marker = ">>>"
        elif "BEARISH" in sig:
            marker = "!!!"
        elif sig == "MIXED":
            marker = "~~~"
        else:
            marker = "   "

        print(f"    {marker} Signal: {sig} ({detail})")
        print()

    # Summary
    print("\u2500" * 50)
    print("  SIGNAL LEGEND:")
    print("    VERY STRONG BULLISH  = Multiple C-suite / 3+ insiders buying")
    print("    STRONG BULLISH       = CEO or CFO open-market purchase")
    print("    MODERATE BULLISH     = Director purchase or multiple insiders")
    print("    MILD BULLISH         = Single insider purchase")
    print("    NEUTRAL              = Routine selling (often 10b5-1 plans)")
    print("    BEARISH WARNING      = Cluster selling (3+ insiders)")
    print("    NO DATA              = No Form 4 filings in period")
    print()
    print("  Source: SEC EDGAR Form 4 filings")
    print("  Note: Insider selling alone is often routine and not bearish.")
    print("        Insider BUYING is the stronger signal (Harvard 2022: +4-8%/yr).")
    print()


# ── CLI Entry Point ────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Check SEC Form 4 insider buying/selling activity"
    )
    parser.add_argument(
        "tickers", nargs="*",
        help="Ticker symbols to check (e.g., GOOGL AAPL NVDA)"
    )
    parser.add_argument(
        "--portfolio", action="store_true",
        help="Check all tickers in portfolio.md"
    )
    parser.add_argument(
        "--days", type=int, default=LOOKBACK_DAYS,
        help=f"Lookback period in days (default: {LOOKBACK_DAYS})"
    )

    args = parser.parse_args()

    lookback_days = args.days

    # Determine tickers
    tickers = []
    if args.portfolio:
        tickers = read_portfolio_tickers()
        if not tickers:
            print("Error: No tickers found in portfolio.md")
            sys.exit(1)
        # Filter out ETFs that won't have insider filings
        # (ETFs like XLE, XLV, GLD don't have Form 4 filings)
        etf_tickers = set()
        stock_tickers = []
        for t in tickers:
            # Common ETF patterns — 3-letter tickers starting with X, or known ETFs
            if t.upper() in ("SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "TLT",
                             "XLE", "XLF", "XLK", "XLV", "XLI", "XLP", "XLU",
                             "XLB", "XLY", "XLRE", "XLC", "VTI", "VOO", "VGT",
                             "VIG", "VXUS", "BND", "AGG", "EEM", "EFA", "HYG",
                             "LQD", "ARKK", "ARKG", "ARKW", "ARKF", "SCHD"):
                etf_tickers.add(t.upper())
            else:
                stock_tickers.append(t)

        if etf_tickers:
            print(f"  Note: Skipping ETFs (no insider filings): {', '.join(sorted(etf_tickers))}")

        tickers = stock_tickers

        if not tickers:
            print("  No individual stocks in portfolio to check.")
            print("  ETFs do not have insider transaction filings.")
            sys.exit(0)

    elif args.tickers:
        tickers = args.tickers
    else:
        parser.print_help()
        sys.exit(1)

    # Check each ticker
    results = []
    for i, ticker in enumerate(tickers):
        ticker = ticker.upper().strip()
        if not ticker:
            continue

        print(f"  Checking {ticker}... ({i + 1}/{len(tickers)})")
        result = check_insider_activity(ticker, days=lookback_days)
        results.append(result)

        # Brief summary while fetching
        sig = result.get("signal_analysis", {})
        txn_count = len(result.get("transactions", []))
        signal = sig.get("signal", "NO DATA") if sig else "ERROR"
        print(f"    Found {txn_count} transactions -> {signal}")

    # Print full report
    print_report(results, days=lookback_days)


if __name__ == "__main__":
    main()
