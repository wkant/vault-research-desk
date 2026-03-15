#!/usr/bin/env python3
"""
Vault Research Desk — Portfolio Correlation Checker
Computes pairwise correlation matrix for portfolio holdings using daily returns.

Usage:
    python3 correlation.py                  # Check current portfolio
    python3 correlation.py AAPL MSFT GOOGL  # Check specific tickers
    python3 correlation.py --add NVDA       # Check how adding NVDA changes correlation
"""

import sys
import os
import math
from datetime import datetime, timedelta

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance not installed.")
    print("Run: pip3 install yfinance")
    sys.exit(1)

# Try numpy for faster computation; fall back to manual calculation
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Portfolio reader (mirrors data_fetcher.py logic)
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from db import VaultDB


def read_portfolio_tickers():
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
    tickers = []
    try:
        with open(portfolio_path, "r") as f:
            lines = f.readlines()

        in_table = False
        for line in lines:
            line = line.strip()
            if "|" in line and "Ticker" in line:
                in_table = True
                continue
            if in_table and "|" in line and "---" not in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if parts and parts[0].isalpha():
                    tickers.append(parts[0].upper())
            elif in_table and "|" not in line:
                in_table = False
    except FileNotFoundError:
        print("WARNING: portfolio.md not found — pass tickers as arguments.")
    return tickers


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_daily_returns(ticker, days=90):
    """Fetch daily percentage returns for *days* calendar days."""
    end = datetime.now()
    start = end - timedelta(days=days + 10)  # small buffer for weekends/holidays
    try:
        hist = yf.Ticker(ticker).history(start=start.strftime("%Y-%m-%d"),
                                         end=end.strftime("%Y-%m-%d"))
        if hist.empty or len(hist) < 2:
            return None
        closes = list(hist["Close"])
        returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] != 0:
                returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
        return returns
    except Exception as e:
        print(f"  WARNING: could not fetch {ticker}: {e}")
        return None


# ---------------------------------------------------------------------------
# Correlation math (pure-Python fallback)
# ---------------------------------------------------------------------------

def _mean(xs):
    return sum(xs) / len(xs)


def _std(xs, mean_x=None):
    if mean_x is None:
        mean_x = _mean(xs)
    n = len(xs)
    return math.sqrt(sum((x - mean_x) ** 2 for x in xs) / (n - 1))


def _pearson(xs, ys):
    """Pearson correlation between two equal-length lists."""
    n = min(len(xs), len(ys))
    xs, ys = xs[:n], ys[:n]
    if n < 3:
        return float("nan")
    mx, my = _mean(xs), _mean(ys)
    sx, sy = _std(xs, mx), _std(ys, my)
    if sx == 0 or sy == 0:
        return float("nan")
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / (n - 1)
    return cov / (sx * sy)


def compute_correlation_matrix(tickers, returns_map):
    """Return NxN correlation matrix as list-of-lists."""
    n = len(tickers)
    matrix = [[0.0] * n for _ in range(n)]

    if HAS_NUMPY:
        # Align lengths to shortest series
        min_len = min(len(returns_map[t]) for t in tickers)
        if min_len < 3:
            print("WARNING: Not enough overlapping data points for reliable correlations.", file=sys.stderr)
            for i in range(n):
                matrix[i][i] = 1.0
            return matrix
        data = np.array([returns_map[t][:min_len] for t in tickers])
        corr = np.corrcoef(data)
        for i in range(n):
            for j in range(n):
                matrix[i][j] = float(corr[i][j])
    else:
        for i in range(n):
            for j in range(n):
                if i == j:
                    matrix[i][j] = 1.0
                elif j > i:
                    r = _pearson(returns_map[tickers[i]], returns_map[tickers[j]])
                    matrix[i][j] = r
                    matrix[j][i] = r
                # lower triangle already filled by symmetry
    return matrix


# ---------------------------------------------------------------------------
# Risk assessment
# ---------------------------------------------------------------------------

def assess_risk(tickers, matrix):
    """Return (score_label, high_pairs, negative_pairs, avg_corr)."""
    n = len(tickers)
    high_pairs = []
    negative_pairs = []
    pair_vals = []

    for i in range(n):
        for j in range(i + 1, n):
            val = matrix[i][j]
            if math.isnan(val):
                continue
            pair_vals.append(val)
            if val > 0.7:
                high_pairs.append((tickers[i], tickers[j], val))
            if val < 0:
                negative_pairs.append((tickers[i], tickers[j], val))

    avg_corr = _mean(pair_vals) if pair_vals else 0.0

    if len(high_pairs) >= 3 or avg_corr > 0.5:
        score = "HIGH"
    elif len(high_pairs) >= 1:
        score = "MEDIUM"
    else:
        score = "LOW"

    return score, high_pairs, negative_pairs, avg_corr


# ---------------------------------------------------------------------------
# Pretty-print helpers
# ---------------------------------------------------------------------------

SECTOR_HINTS = {
    "AAPL": "mega-cap tech", "MSFT": "mega-cap tech", "GOOGL": "mega-cap tech",
    "AMZN": "mega-cap tech/consumer", "META": "mega-cap tech",
    "NVDA": "semis/AI", "AVGO": "semis", "AMD": "semis",
    "TSLA": "EV/consumer disc.", "NFLX": "streaming/comm",
    "XLK": "tech ETF", "XLE": "energy ETF", "XLV": "healthcare ETF",
    "XLF": "financials ETF", "XLY": "cons disc ETF", "XLP": "cons staples ETF",
    "XLI": "industrials ETF", "XLB": "materials ETF", "XLRE": "real estate ETF",
    "XLU": "utilities ETF", "XLC": "comm services ETF",
    "GLD": "gold ETF", "SLV": "silver ETF",
    "SPY": "S&P 500 ETF", "VOO": "S&P 500 ETF", "QQQ": "Nasdaq ETF",
    "TLT": "long-term bonds", "BND": "total bond",
    "JPM": "financials", "BAC": "financials", "GS": "financials",
    "XOM": "energy", "CVX": "energy", "COP": "energy",
    "JNJ": "healthcare", "UNH": "healthcare", "LLY": "pharma",
}


def _hint(t1, t2):
    h1 = SECTOR_HINTS.get(t1, "")
    h2 = SECTOR_HINTS.get(t2, "")
    if h1 and h2:
        if h1 == h2:
            return f"both {h1}, same risk factor"
        return f"{h1} vs {h2}"
    return ""


def print_report(tickers, matrix, add_ticker=None):
    """Print the formatted correlation report."""
    score, high_pairs, neg_pairs, avg_corr = assess_risk(tickers, matrix)

    col_w = max(len(t) for t in tickers) + 2  # column width

    print()
    print(f"\u2550\u2550\u2550 PORTFOLIO CORRELATION CHECK \u2550\u2550\u2550")
    if add_ticker:
        print(f"  (simulating addition of {add_ticker})")
    print(f"  Period: 90-day daily returns")
    print(f"  Date:   {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # --- Matrix ---
    print("\nCorrelation Matrix:")
    header = " " * col_w + "".join(f"{t:>{col_w}}" for t in tickers)
    print(header)
    for i, t in enumerate(tickers):
        row = f"{t:<{col_w}}"
        for j in range(len(tickers)):
            val = matrix[i][j]
            if math.isnan(val):
                row += f"{'N/A':>{col_w}}"
            else:
                row += f"{val:>{col_w}.2f}"
        print(row)

    # --- High correlation pairs ---
    print(f"\nHIGH CORRELATION PAIRS (>0.7):")
    if high_pairs:
        for t1, t2, val in sorted(high_pairs, key=lambda x: x[2], reverse=True):
            hint = _hint(t1, t2)
            suffix = f" \u2014 {hint}" if hint else ""
            print(f"  {t1} / {t2}: {val:.2f}{suffix}")
    else:
        print("  None \u2014 good diversification")

    # --- Negative correlations ---
    print(f"\nNEGATIVE CORRELATIONS (natural hedges):")
    if neg_pairs:
        for t1, t2, val in sorted(neg_pairs, key=lambda x: x[2]):
            hint = _hint(t1, t2)
            suffix = f" \u2014 {hint}" if hint else ""
            print(f"  {t1} / {t2}: {val:.2f}{suffix}")
    else:
        print("  None found")

    # --- Risk score ---
    print(f"\nPORTFOLIO RISK SCORE: {score}")
    print(f"  Average pairwise correlation: {avg_corr:.2f}")
    if score == "LOW":
        print("  No pairs >0.7 \u2014 portfolio is well diversified.")
    elif score == "MEDIUM":
        print(f"  {len(high_pairs)} pair(s) >0.7 \u2014 moderate concentration risk.")
    else:
        reasons = []
        if len(high_pairs) >= 3:
            reasons.append(f"{len(high_pairs)} pairs >0.7")
        if avg_corr > 0.5:
            reasons.append(f"avg correlation {avg_corr:.2f} > 0.5")
        print(f"  {'; '.join(reasons)} \u2014 high concentration risk.")

    # --- Recommendation ---
    if score == "HIGH":
        print("\nRECOMMENDATION:")
        print("  Consider adding uncorrelated assets to reduce portfolio risk:")
        existing_hints = set(SECTOR_HINTS.get(t, "") for t in tickers)
        suggestions = []
        if "gold ETF" not in existing_hints:
            suggestions.append("GLD (gold \u2014 often negatively correlated with equities)")
        if "long-term bonds" not in existing_hints and "total bond" not in existing_hints:
            suggestions.append("TLT/BND (bonds \u2014 low correlation to stocks)")
        if "energy ETF" not in existing_hints and "energy" not in existing_hints:
            suggestions.append("XLE (energy \u2014 different macro drivers)")
        if "healthcare ETF" not in existing_hints and "healthcare" not in existing_hints:
            suggestions.append("XLV (healthcare \u2014 defensive sector)")
        if not suggestions:
            suggestions.append("Look for assets in sectors not currently held")
        for s in suggestions:
            print(f"    - {s}")
    elif score == "MEDIUM":
        print("\nRECOMMENDATION:")
        print("  Portfolio has moderate overlap. Consider whether correlated")
        print("  positions are intentional overweights or accidental doubling.")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]

    add_ticker = None
    explicit_tickers = []

    # Parse arguments
    i = 0
    while i < len(args):
        if args[i] == "--add" and i + 1 < len(args):
            add_ticker = args[i + 1].upper()
            i += 2
        elif not args[i].startswith("--"):
            explicit_tickers.append(args[i].upper())
            i += 1
        else:
            i += 1

    # Determine ticker list
    if explicit_tickers:
        tickers = explicit_tickers
    else:
        tickers = read_portfolio_tickers()
        if not tickers:
            print("ERROR: No tickers found. Pass tickers as arguments or populate portfolio.md.")
            sys.exit(1)

    if add_ticker and add_ticker not in tickers:
        tickers = tickers + [add_ticker]

    if len(tickers) < 2:
        print("ERROR: Need at least 2 tickers to compute correlations.")
        sys.exit(1)

    print(f"Fetching 90-day returns for: {', '.join(tickers)} ...")

    # Fetch returns
    returns_map = {}
    failed = []
    for t in tickers:
        ret = fetch_daily_returns(t)
        if ret and len(ret) >= 5:
            returns_map[t] = ret
        else:
            failed.append(t)

    if failed:
        print(f"WARNING: Could not get data for: {', '.join(failed)}")
        tickers = [t for t in tickers if t in returns_map]

    if len(tickers) < 2:
        print("ERROR: Not enough valid data to compute correlations.")
        sys.exit(1)

    # Compute and display
    matrix = compute_correlation_matrix(tickers, returns_map)
    print_report(tickers, matrix, add_ticker=add_ticker)


if __name__ == "__main__":
    main()
