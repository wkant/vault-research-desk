#!/usr/bin/env python3
"""
Extract watchlist picks from report's "What to Buy" section
and save them to vault.db.

Usage:
    python3 tools/watchlist_extract.py reports/report_2026-03-14.md
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import VaultDB

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def extract_report_date(text):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    return m.group(1) if m else ""


def extract_watchlist(text):
    """Parse 'What to Buy' table for watchlist picks."""
    picks = []

    # Find "What to Buy" section
    section_match = re.search(
        r"##\s*What to Buy.*?\n(.*?)(?=\n##|\Z)", text, re.DOTALL | re.IGNORECASE
    )
    if not section_match:
        return picks

    section = section_match.group(1)
    lines = section.split("\n")
    header_idx = None
    col_map = {}

    for i, line in enumerate(lines):
        if "|" not in line:
            continue

        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c]

        lower_cells = [c.lower() for c in cells]

        # Detect header
        if "ticker" in lower_cells:
            for j, cell in enumerate(lower_cells):
                if cell == "ticker":
                    col_map["ticker"] = j
                elif cell in ("conv.", "conviction", "conv"):
                    col_map["conviction"] = j
                elif cell in ("entry", "entry zone", "entry price"):
                    col_map["entry"] = j
                elif cell in ("why",):
                    col_map["why"] = j
            header_idx = i
            continue

        # Skip separator
        if header_idx is not None and all(
            c.replace("-", "").replace(":", "").strip() == "" for c in cells
        ):
            continue

        # Data row
        if header_idx is not None and col_map and "ticker" in col_map:
            ticker_idx = col_map["ticker"]
            if ticker_idx >= len(cells):
                continue

            ticker = cells[ticker_idx].replace("**", "").replace("*", "").strip()
            if not re.match(r"^[A-Z]{1,5}$", ticker):
                continue

            # Skip "Cash" rows
            if ticker in ("CASH",):
                continue

            # Extract entry price (first $ amount in entry column)
            entry = ""
            if "entry" in col_map and col_map["entry"] < len(cells):
                price_match = re.search(r"\$(\d+\.?\d*)", cells[col_map["entry"]])
                if price_match:
                    entry = price_match.group(1)

            # Extract conviction
            conv = ""
            if "conviction" in col_map and col_map["conviction"] < len(cells):
                conv_raw = cells[col_map["conviction"]]
                stars = conv_raw.count("*")
                if stars >= 3:
                    conv = "***"
                elif stars >= 2:
                    conv = "**"
                elif stars >= 1:
                    conv = "*"

            # Extract reason
            why = ""
            if "why" in col_map and col_map["why"] < len(cells):
                why = cells[col_map["why"]].strip()[:100]  # truncate

            picks.append({
                "ticker": ticker,
                "entry": entry,
                "conviction": conv,
                "why": why,
            })

    return picks


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tools/watchlist_extract.py reports/report_YYYY-MM-DD.md")
        sys.exit(1)

    report_path = sys.argv[1]
    if not os.path.isabs(report_path):
        project_root = os.path.join(SCRIPT_DIR, "..")
        if os.path.exists(os.path.join(project_root, report_path)):
            report_path = os.path.join(project_root, report_path)
        elif os.path.exists(report_path):
            report_path = os.path.abspath(report_path)

    if not os.path.exists(report_path):
        print(f"ERROR: Report not found: {report_path}")
        sys.exit(1)

    with open(report_path, "r", encoding="utf-8") as f:
        text = f.read()

    report_date = extract_report_date(text)
    report_name = os.path.basename(report_path)
    picks = extract_watchlist(text)

    if not picks:
        print(f"No watchlist picks found in {report_name}")
        return

    added = 0
    skipped = 0
    with VaultDB() as db:
        for pick in picks:
            # Check if exists in DB
            if db.watchlist_exists(report_date, pick["ticker"]):
                skipped += 1
                continue
            db.add_watchlist(
                date=report_date,
                ticker=pick["ticker"],
                price_at_rec=float(pick["entry"]) if pick["entry"] else None,
                conviction=pick["conviction"],
                report=report_name,
                notes=pick["why"],
            )
            added += 1

    print(f"Watchlist extract — {report_name}")
    print(f"  Added: {added} | Skipped (duplicate): {skipped}")


if __name__ == "__main__":
    main()
