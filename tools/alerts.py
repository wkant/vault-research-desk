#!/usr/bin/env python3
"""
Alert monitor for the Vault Research Desk.

Reads alert conditions and thesis change triggers from the latest report
markdown file, checks current prices via yfinance, and reports which
alerts are triggered.

Usage:
    python3 tools/alerts.py                           # uses latest report
    python3 tools/alerts.py reports/report_2026-03-11.md  # specific report
"""

import os
import sys
import re
import glob
from datetime import datetime

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, '..')
sys.path.insert(0, SCRIPT_DIR)

from data_fetcher import fetch_quote

# ---------------------------------------------------------------------------
# Asset name -> yfinance ticker mapping
# ---------------------------------------------------------------------------
ASSET_MAP = {
    "wti oil": "CL=F", "wti": "CL=F", "oil": "CL=F",
    "vix": "^VIX",
    "s&p 500": "^GSPC", "s&p": "^GSPC", "spy": "^GSPC",
    "gold": "GC=F",
    "dxy": "DX-Y.NYB", "dollar": "DX-Y.NYB",
    "10y yield": "^TNX", "10y": "^TNX",
    "nasdaq": "^IXIC",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_latest_report():
    """Return the path to the most recent report_*.md file."""
    reports_dir = os.path.join(PROJECT_ROOT, 'reports')
    pattern = os.path.join(reports_dir, 'report_*.md')
    files = sorted(glob.glob(pattern))
    if not files:
        print("No report files found in", reports_dir)
        sys.exit(1)
    return files[-1]


def extract_section(lines, heading_prefix):
    """
    Extract lines between a heading that starts with `heading_prefix`
    and the next ## heading (or EOF).
    """
    collecting = False
    section = []
    for line in lines:
        if line.startswith(heading_prefix):
            collecting = True
            continue
        if collecting and line.startswith('## '):
            break
        if collecting:
            stripped = line.strip()
            if stripped:
                section.append(stripped)
    return section


def resolve_ticker(text):
    """
    Try to identify a yfinance ticker from a text fragment.
    First checks ASSET_MAP (longest match first), then looks for
    an all-caps ticker word (e.g. GOOGL, NVDA).
    """
    lower = text.lower()
    # Try asset map, longest keys first to prefer "wti oil" over "oil"
    for name in sorted(ASSET_MAP, key=len, reverse=True):
        if name in lower:
            return name, ASSET_MAP[name]

    # Try direct ticker match (all-caps word, 1-5 letters)
    m = re.search(r'\b([A-Z]{1,5})\b', text)
    if m:
        candidate = m.group(1)
        # Skip common English words that look like tickers
        skip = {'A', 'I', 'FOR', 'THE', 'AND', 'OR', 'IF', 'IN', 'ON',
                'AT', 'TO', 'NO', 'OK', 'ALL', 'ADD', 'RUN', 'SET', 'CPI'}
        if candidate not in skip:
            return candidate, candidate

    return None, None


def parse_threshold(text):
    """
    Extract a numeric threshold and direction (above/below) from text.
    Returns (direction, value) or (None, None).
    """
    # Match patterns like "above $100", "below 6,620", ">$100", "<6620"
    # Direction words
    above_words = r'(?:above|over|>|breaks above|spikes above|sustains above|exceeds)'
    below_words = r'(?:below|under|<|breaks below|drops below|falls below|breaks)'

    # Try "above/over/> $X"
    m = re.search(above_words + r'\s*\$?([\d,]+\.?\d*)', text, re.IGNORECASE)
    if m:
        val = float(m.group(1).replace(',', ''))
        return 'above', val

    m = re.search(below_words + r'\s*\$?([\d,]+\.?\d*)', text, re.IGNORECASE)
    if m:
        val = float(m.group(1).replace(',', ''))
        return 'below', val

    return None, None


def check_alert(description):
    """
    Parse a single alert line, fetch price, and determine status.
    Returns a dict with check results.
    """
    asset_name, ticker = resolve_ticker(description)
    direction, threshold = parse_threshold(description)

    if ticker is None or threshold is None:
        return {
            'description': description,
            'checkable': False,
            'label': description,
        }

    quote = fetch_quote(ticker)
    if quote is None or 'error' in quote:
        return {
            'description': description,
            'checkable': False,
            'label': f"{description} -> Could not fetch {ticker}",
        }

    price = quote['price']

    if direction == 'above':
        triggered = price > threshold
    else:
        triggered = price < threshold

    # Format price string
    if ticker in ('^VIX', '^TNX'):
        price_str = f"{price:,.2f}"
    else:
        price_str = f"${price:,.2f}"

    return {
        'description': description,
        'checkable': True,
        'triggered': triggered,
        'price': price,
        'price_str': price_str,
        'ticker': ticker,
        'asset_name': asset_name,
        'direction': direction,
        'threshold': threshold,
    }


def format_result(result):
    """Format a single check result as a display line."""
    if not result['checkable']:
        return f"  [  --  ] {result['description']} -> Cannot check automatically"

    if result['triggered']:
        tag = "[!!!!!]"
        suffix = " \u26a0 TRIGGERED"
    else:
        tag = "[  OK  ]"
        suffix = ""

    desc = result['description']
    price_str = result['price_str']
    return f"  {tag} {desc} -> Current: {price_str}{suffix}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Determine report path
    if len(sys.argv) > 1:
        report_path = sys.argv[1]
        if not os.path.isabs(report_path):
            report_path = os.path.join(PROJECT_ROOT, report_path)
    else:
        report_path = find_latest_report()

    if not os.path.exists(report_path):
        print(f"Report not found: {report_path}")
        sys.exit(1)

    report_name = os.path.basename(report_path)

    with open(report_path, 'r') as f:
        lines = f.readlines()

    # Extract sections
    alert_lines = extract_section(lines, '## Alert Conditions')
    thesis_lines = extract_section(lines, '## Thesis Change Triggers')

    # Clean numbered/bulleted prefixes
    def clean_line(line):
        line = re.sub(r'^\d+\.\s*', '', line)   # "1. foo" -> "foo"
        line = re.sub(r'^[-*]\s*', '', line)     # "- foo"  -> "foo"
        return line.strip()

    alert_items = [clean_line(l) for l in alert_lines]
    thesis_items = [clean_line(l) for l in thesis_lines]

    # Check all alerts
    alert_results = [check_alert(item) for item in alert_items]
    thesis_results = [check_alert(item) for item in thesis_items]

    # Count triggered
    triggered_count = sum(
        1 for r in alert_results + thesis_results
        if r.get('triggered', False)
    )

    # Print output
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    print()
    print(f"\u2550\u2550\u2550 ALERT CHECK ({now}) \u2550\u2550\u2550")
    print(f"Report: {report_name}")

    if alert_results:
        print()
        print("ALERT CONDITIONS:")
        for r in alert_results:
            print(format_result(r))

    if thesis_results:
        print()
        print("THESIS CHANGE TRIGGERS:")
        for r in thesis_results:
            print(format_result(r))

    print()
    if triggered_count > 0:
        noun = "ALERT" if triggered_count == 1 else "ALERTS"
        print(f"RESULT: {triggered_count} {noun} TRIGGERED. Run `flash` for quick analysis.")
    else:
        print("RESULT: No alerts triggered. All clear.")
    print()


if __name__ == '__main__':
    main()
