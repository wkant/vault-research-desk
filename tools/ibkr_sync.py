#!/usr/bin/env python3
"""
Parse Interactive Brokers CSV exports and update portfolio.md.

Usage:
    python3 tools/ibkr_sync.py export.csv          # Preview changes
    python3 tools/ibkr_sync.py export.csv --write   # Update portfolio.md
"""

import argparse
import csv
import os
import re
import sys
from datetime import date
from typing import Dict, List, NamedTuple, Optional, Tuple

PORTFOLIO_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "portfolio.md"
)

TICKER_MAP = {
    "GOOG": "GOOGL",
    "BRK B": "BRK-B",
    "BF B": "BF-B",
}

# Columns that identify the simpler Portfolio export format
PORTFOLIO_EXPORT_COLUMNS = {
    "symbol",
    "quantity",
    "close price",
    "average cost",
}


class Position(NamedTuple):
    ticker: str
    shares: float
    avg_cost: float


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def _detect_format(filepath: str) -> str:
    """Return 'activity' or 'portfolio' based on CSV content."""
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        first_line = f.readline().lower()
    # The simple portfolio export has recognisable column headers on row 1
    if all(col in first_line for col in PORTFOLIO_EXPORT_COLUMNS):
        return "portfolio"
    return "activity"


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _normalize_ticker(raw: str) -> str:
    raw = raw.strip()
    return TICKER_MAP.get(raw, raw)


def parse_activity_statement(filepath: str) -> List[Position]:
    """Parse the multi-section Activity Statement CSV."""
    positions: List[Position] = []
    in_open_positions = False

    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 2:
                continue

            section = row[0].strip()
            row_type = row[1].strip() if len(row) > 1 else ""

            # Track which section we are in
            if section == "Open Positions":
                in_open_positions = True
                if row_type == "Header":
                    # Build column index from the header row
                    col_names = [c.strip() for c in row]
                    col_idx = {name: i for i, name in enumerate(col_names)}
                    continue

            if section != "Open Positions" and in_open_positions:
                in_open_positions = False
                continue

            if not in_open_positions:
                continue

            if row_type != "Data":
                continue

            # Only stock positions
            asset_cat = row[col_idx.get("Asset Category", 2)].strip()
            if asset_cat != "Stocks":
                continue

            # Skip non-USD
            currency = row[col_idx.get("Currency", 3)].strip()
            if currency and currency != "USD":
                print(f"  WARNING: skipping {row[col_idx.get('Symbol', 4)].strip()} — currency {currency}")
                continue

            symbol = _normalize_ticker(row[col_idx.get("Symbol", 4)])
            try:
                qty = float(row[col_idx.get("Quantity", 5)])
                cost = float(row[col_idx.get("Cost Price", 7)])
            except (ValueError, IndexError):
                continue

            if qty == 0:
                continue

            positions.append(Position(ticker=symbol, shares=qty, avg_cost=cost))

    return positions


def parse_portfolio_export(filepath: str) -> List[Position]:
    """Parse the simpler Portfolio CSV export."""
    positions: List[Position] = []

    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # Normalise header names to lowercase
        reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]  # type: ignore[union-attr]

        for row in reader:
            symbol = _normalize_ticker(row.get("symbol", ""))
            if not symbol:
                continue

            try:
                qty = float(row.get("quantity", 0))
                cost = float(row.get("average cost", 0))
            except ValueError:
                continue

            if qty == 0:
                continue

            positions.append(Position(ticker=symbol, shares=qty, avg_cost=cost))

    return positions


# ---------------------------------------------------------------------------
# portfolio.md helpers
# ---------------------------------------------------------------------------

def _parse_portfolio_md(path: str) -> Tuple[Dict[str, Position], str, str, str]:
    """
    Read portfolio.md and return:
      - dict of ticker -> Position (from Holdings table)
      - settings section text
      - profile section text
      - notes section text
    """
    holdings: Dict[str, Position] = {}
    settings_text = ""
    profile_text = ""
    notes_text = ""

    if not os.path.exists(path):
        return holdings, settings_text, profile_text, notes_text

    with open(path, encoding="utf-8") as f:
        content = f.read()

    # Split on ## headings
    sections: Dict[str, str] = {}
    current_heading: Optional[str] = None
    buf: List[str] = []
    for line in content.splitlines(True):
        m = re.match(r"^##\s+(.+)", line)
        if m:
            if current_heading is not None:
                sections[current_heading] = "".join(buf)
            current_heading = m.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if current_heading is not None:
        sections[current_heading] = "".join(buf)

    settings_text = sections.get("Settings", "").strip()
    profile_text = sections.get("Profile", "").strip()
    notes_text = sections.get("Notes", "").strip()

    # Parse Holdings table
    holdings_raw = sections.get("Holdings", "")
    for line in holdings_raw.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 3:
            continue
        ticker = cells[0]
        if ticker in ("Ticker", "--------", "---"):
            continue
        if re.match(r"^-+$", ticker):
            continue
        try:
            shares = float(cells[1])
            cost = float(cells[2].replace("$", "").replace(",", ""))
        except ValueError:
            continue
        holdings[ticker] = Position(ticker=ticker, shares=shares, avg_cost=cost)

    return holdings, settings_text, profile_text, notes_text


def _build_portfolio_md(
    positions: List[Position],
    settings_text: str,
    profile_text: str,
    notes_text: str,
) -> str:
    """Build the full portfolio.md content."""
    today = date.today().isoformat()

    lines: List[str] = []
    lines.append("## Holdings")
    lines.append("| Ticker | Shares | Avg Cost | Date Bought |")
    lines.append("|--------|--------|----------|-------------|")
    for p in sorted(positions, key=lambda x: x.ticker):
        cost_str = f"${p.avg_cost:,.0f}" if p.avg_cost == int(p.avg_cost) else f"${p.avg_cost:,.2f}"
        lines.append(f"| {p.ticker:<6} | {p.shares:<6} | {cost_str:<8} | {today:<11} |")
    lines.append("")

    if settings_text:
        lines.append("## Settings")
        lines.append(settings_text)
        lines.append("")

    if profile_text:
        lines.append("## Profile")
        lines.append(profile_text)
        lines.append("")

    if notes_text:
        lines.append("## Notes")
        lines.append(notes_text)
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Preview / diff
# ---------------------------------------------------------------------------

def _print_preview(
    filepath: str,
    fmt: str,
    new_positions: List[Position],
    old_holdings: Dict[str, Position],
) -> None:
    print()
    print("=" * 3 + " IBKR PORTFOLIO SYNC " + "=" * 3)
    print(f"File: {os.path.basename(filepath)}")
    print(f"Format: {'Activity Statement' if fmt == 'activity' else 'Portfolio Export'}")
    print()

    if not new_positions:
        print("No positions found in export.")
        return

    print("POSITIONS FOUND:")
    for p in new_positions:
        print(f"  {p.ticker:<8} {p.shares} shares @ ${p.avg_cost:,.2f}")
    print()

    new_map = {p.ticker: p for p in new_positions}
    all_tickers = sorted(set(list(new_map.keys()) + list(old_holdings.keys())))

    print("CHANGES vs current portfolio.md:")
    for t in all_tickers:
        old = old_holdings.get(t)
        new = new_map.get(t)
        if old and new:
            if old.shares == new.shares and old.avg_cost == new.avg_cost:
                print(f"  {t}: no change")
            else:
                print(f"  {t}: {old.shares} @ ${old.avg_cost:,.2f} -> {new.shares} @ ${new.avg_cost:,.2f}")
        elif new and not old:
            print(f"  NEW: {t} {new.shares} shares @ ${new.avg_cost:,.2f}")
        elif old and not new:
            print(f"  REMOVED: {t} (in portfolio.md but not in IBKR export)")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Sync IBKR CSV export to portfolio.md")
    parser.add_argument("csv_file", help="Path to IBKR CSV export")
    parser.add_argument("--write", action="store_true", help="Actually update portfolio.md")
    args = parser.parse_args()

    if not os.path.isfile(args.csv_file):
        print(f"Error: file not found: {args.csv_file}", file=sys.stderr)
        sys.exit(1)

    fmt = _detect_format(args.csv_file)

    if fmt == "activity":
        positions = parse_activity_statement(args.csv_file)
    else:
        positions = parse_portfolio_export(args.csv_file)

    if not positions:
        print("No stock positions found in the export.", file=sys.stderr)
        sys.exit(1)

    old_holdings, settings_text, profile_text, notes_text = _parse_portfolio_md(PORTFOLIO_PATH)

    _print_preview(args.csv_file, fmt, positions, old_holdings)

    if args.write:
        # Safety: create backup before overwriting
        if os.path.exists(PORTFOLIO_PATH):
            import shutil
            backup_path = PORTFOLIO_PATH + ".backup"
            shutil.copy2(PORTFOLIO_PATH, backup_path)
            print(f"Backup saved: {os.path.basename(backup_path)}")

        md = _build_portfolio_md(positions, settings_text, profile_text, notes_text)
        with open(PORTFOLIO_PATH, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"portfolio.md updated ({len(positions)} positions).")
    else:
        print("Use --write to update portfolio.md")


if __name__ == "__main__":
    main()
