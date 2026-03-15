#!/usr/bin/env python3
"""
Vault Research Desk — Thesis Tracker

Tracks investment theses across reports to prevent unexplained flip-flopping
and build conviction tracking over time.

Usage:
    python3 tools/thesis_tracker.py                     Show all active theses
    python3 tools/thesis_tracker.py add TICKER ...      Add a new thesis
    python3 tools/thesis_tracker.py update TICKER ...   Add a history note
    python3 tools/thesis_tracker.py check               Review active theses for age/staleness
    python3 tools/thesis_tracker.py close TICKER ...    Close a thesis
    python3 tools/thesis_tracker.py extract REPORT.md   Auto-extract theses from a report
"""

import argparse
import os
import re
import sys
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from db import VaultDB

VALID_DIRECTIONS = ("BUY", "HOLD", "SELL", "AVOID")
VALID_CONVICTIONS = ("HIGH", "MEDIUM", "LOW")
VALID_STATUSES = ("ACTIVE", "CONFIRMED", "INVALIDATED", "EXPIRED")

AGE_REVIEW_DAYS = 90
AGE_STALE_DAYS = 180

# Direction pairs that constitute a flip (original -> new)
FLIP_PAIRS = {
    ("BUY", "SELL"), ("BUY", "AVOID"),
    ("SELL", "BUY"), ("SELL", "HOLD"),
    ("HOLD", "SELL"), ("HOLD", "AVOID"),
}


def today():
    return datetime.now().strftime("%Y-%m-%d")


def _normalize_conviction(raw):
    """Normalize conviction from DB which may be stars or text."""
    if not raw:
        return "MEDIUM"
    upper = raw.upper().strip()
    if upper in VALID_CONVICTIONS:
        return upper
    stars = raw.count("*")
    if stars >= 3:
        return "HIGH"
    elif stars == 2:
        return "MEDIUM"
    else:
        return "LOW"


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def fmt_thesis(entry, verbose=True):
    """Format a single thesis entry for display."""
    lines = []
    status = entry.get("status", "ACTIVE")
    direction = entry.get("direction", "")
    conviction = _normalize_conviction(entry.get("conviction", ""))
    ticker = entry.get("ticker", "")
    date_opened = entry.get("date_opened", "")

    status_icon = {
        "ACTIVE": "+", "CONFIRMED": "V", "INVALIDATED": "X", "EXPIRED": "~",
        "CLOSED": "X",
    }.get(status, "?")

    dir_color = {
        "BUY": "\033[32m", "SELL": "\033[31m",
        "HOLD": "\033[33m", "AVOID": "\033[31m"
    }.get(direction, "")
    reset = "\033[0m"

    age = thesis_age_days(entry)
    age_flag = ""
    if age is not None:
        if age > AGE_STALE_DAYS:
            age_flag = " [STALE — {} days]".format(age)
        elif age > AGE_REVIEW_DAYS:
            age_flag = " [REVIEW — {} days]".format(age)

    lines.append(
        "[{icon}] {color}{dir}{reset}  {ticker}  (conviction: {conv})  "
        "opened {date}  status: {status}{age}".format(
            icon=status_icon,
            color=dir_color, reset=reset,
            dir=direction,
            ticker=ticker,
            conv=conviction,
            date=date_opened,
            status=status,
            age=age_flag,
        )
    )
    if verbose:
        lines.append("    Thesis: {}".format(entry.get("thesis", "")))
        if entry.get("key_conditions"):
            lines.append("    Invalidation: {}".format(entry["key_conditions"]))
        if entry.get("history"):
            for h in entry["history"][-3:]:  # show last 3
                lines.append("    [{date}] {note}".format(**h))
    return "\n".join(lines)


def thesis_age_days(entry):
    """Return number of days since thesis was opened, or None."""
    try:
        opened = datetime.strptime(entry["date_opened"], "%Y-%m-%d")
        return (datetime.now() - opened).days
    except (ValueError, KeyError):
        return None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_show(args):
    """Show all active theses (default command)."""
    with VaultDB() as db:
        entries = db.get_all_theses()
    active = [e for e in entries if e["status"] == "ACTIVE"]
    if not active:
        print("No active theses.")
        return
    print("=== Active Theses ({}) ===\n".format(len(active)))
    for entry in active:
        print(fmt_thesis(entry))
        print()


def cmd_add(args):
    """Add a new thesis."""
    ticker = args.ticker.upper()
    direction = args.direction.upper()
    conviction = args.conviction.upper()
    conditions = args.conditions or ""
    thesis_text = args.thesis

    if direction not in VALID_DIRECTIONS:
        print("ERROR: direction must be one of {}".format(VALID_DIRECTIONS))
        return
    if conviction not in VALID_CONVICTIONS:
        print("ERROR: conviction must be one of {}".format(VALID_CONVICTIONS))
        return

    with VaultDB() as db:
        existing = db.get_thesis_full(ticker)
        if existing:
            print("WARNING: Active thesis already exists for {}:".format(ticker))
            print(fmt_thesis(existing))
            print("\nUse 'close' first, or 'update' to add a note.")
            return

        success = db.add_thesis(
            ticker=ticker,
            direction=direction,
            conviction=conviction,
            thesis=thesis_text,
            key_conditions=conditions,
            date_opened=today(),
        )
        if success:
            db.add_thesis_history(ticker, "Thesis opened.")

        entry = db.get_thesis_full(ticker)

    if entry:
        print("Added thesis for {}:".format(ticker))
        print(fmt_thesis(entry))
    else:
        print("ERROR: Failed to add thesis for {}.".format(ticker))


def cmd_update(args):
    """Add a history note to an active thesis."""
    ticker = args.ticker.upper()

    with VaultDB() as db:
        entry = db.get_thesis_full(ticker)
        if not entry:
            print("No active thesis found for {}.".format(ticker))
            return

        note = args.note
        update_kwargs = {}

        if args.conviction:
            old_conv = _normalize_conviction(entry["conviction"])
            new_conv = args.conviction.upper()
            update_kwargs["conviction"] = new_conv
            note += " [conviction {} -> {}]".format(old_conv, new_conv)

        if args.direction:
            old_dir = entry["direction"]
            new_dir = args.direction.upper()
            if (old_dir, new_dir) in FLIP_PAIRS:
                print(
                    "\n*** WARNING: FLIP detected — {} was {} ({}) now {}. "
                    "Explain in report. ***\n".format(
                        ticker, old_dir, entry["date_opened"], new_dir
                    )
                )
            update_kwargs["direction"] = new_dir
            note += " [direction {} -> {}]".format(old_dir, new_dir)

        if update_kwargs:
            db.update_thesis(ticker, **update_kwargs)

        db.add_thesis_history(ticker, note)

        entry = db.get_thesis_full(ticker)

    print("Updated {}:".format(ticker))
    print(fmt_thesis(entry))


def cmd_check(args):
    """Review active theses for age and staleness."""
    with VaultDB() as db:
        all_theses = db.get_all_theses()
    active = [e for e in all_theses if e["status"] == "ACTIVE"]
    if not active:
        print("No active theses to check.")
        return

    stale = []
    review = []
    ok = []

    for entry in active:
        age = thesis_age_days(entry)
        if age is None:
            ok.append(entry)
        elif age > AGE_STALE_DAYS:
            stale.append((entry, age))
        elif age > AGE_REVIEW_DAYS:
            review.append((entry, age))
        else:
            ok.append(entry)

    if stale:
        print("=== STALE (>{} days) — consider closing ===\n".format(AGE_STALE_DAYS))
        for entry, age in stale:
            print(fmt_thesis(entry))
            print("    Age: {} days — thesis may no longer be relevant.\n".format(age))

    if review:
        print("=== REVIEW (>{} days) — re-evaluate conditions ===\n".format(AGE_REVIEW_DAYS))
        for entry, age in review:
            print(fmt_thesis(entry))
            print("    Age: {} days — check if key conditions still hold.\n".format(age))

    if ok:
        print("=== OK ({}) ===\n".format(len(ok)))
        for entry in ok:
            print(fmt_thesis(entry, verbose=False))

    print("\nTotal active: {}  |  Stale: {}  |  Review: {}  |  OK: {}".format(
        len(active), len(stale), len(review), len(ok)
    ))


def cmd_close(args):
    """Close an active thesis."""
    ticker = args.ticker.upper()
    new_status = args.status.upper()

    if new_status not in ("CONFIRMED", "INVALIDATED", "EXPIRED"):
        print("ERROR: status must be CONFIRMED, INVALIDATED, or EXPIRED.")
        return

    with VaultDB() as db:
        existing = db.get_thesis_full(ticker)
        if not existing:
            print("No active thesis found for {}.".format(ticker))
            return

        old_status = existing["status"]
        close_note = "Thesis closed: {} -> {}.".format(old_status, new_status)
        if args.note:
            close_note += " " + args.note

        db.close_thesis_with_status(ticker, status=new_status, note=close_note)

        # Re-fetch to show final state (now closed)
        entries = db.get_all_theses()
        entry = None
        for e in entries:
            if e["ticker"] == ticker and e["status"] == new_status:
                entry = e
                break

    if entry:
        print("Closed {} as {}:".format(ticker, new_status))
        print(fmt_thesis(entry))
    else:
        print("Closed {} as {}.".format(ticker, new_status))


# ---------------------------------------------------------------------------
# Report extraction
# ---------------------------------------------------------------------------

def parse_report_table(text):
    """
    Parse markdown tables with columns like Ticker, Action, Entry, Stop, Target, Conviction.
    Also handles "What to Buy" tables that have Conv. column instead of Action.
    Returns list of dicts with keys: ticker, action, entry, stop, target, conviction.
    """
    results = []
    lines = text.split("\n")
    header_idx = None
    col_map = {}

    for i, line in enumerate(lines):
        if "|" not in line:
            # Reset when we leave a table
            if header_idx is not None:
                header_idx = None
                col_map = {}
            continue
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c]  # drop empty from leading/trailing |

        # Detect header row
        lower_cells = [c.lower() for c in cells]
        has_ticker = "ticker" in lower_cells or "stock" in lower_cells
        has_action = any(a in lower_cells for a in ("action", "direction", "call"))
        has_conv = any(a in lower_cells for a in ("conv.", "conviction", "conv"))

        if has_ticker and (has_action or has_conv):
            col_map = {}
            for j, cell in enumerate(lower_cells):
                if cell in ("ticker", "stock"):
                    col_map["ticker"] = j
                elif cell in ("action", "direction", "call"):
                    col_map["action"] = j
                elif cell in ("entry", "entry price", "price", "entry zone"):
                    col_map["entry"] = j
                elif cell in ("stop", "stop-loss", "stoploss", "stop loss"):
                    col_map["stop"] = j
                elif cell in ("target", "price target", "target price"):
                    col_map["target"] = j
                elif cell in ("conviction", "conv.", "conv"):
                    col_map["conviction"] = j
                elif cell in ("date",):
                    col_map["date"] = j
                elif cell in ("why",):
                    col_map["why"] = j
            header_idx = i
            continue

        # Skip separator row (e.g. |---|---|)
        if header_idx is not None and all(
            c.replace("-", "").replace(":", "").strip() == "" for c in cells
        ):
            continue

        # Data row
        if header_idx is not None and col_map and "ticker" in col_map:
            row = {}
            for key, idx in col_map.items():
                if idx < len(cells):
                    row[key] = cells[idx].strip()

            if "ticker" not in row:
                continue

            ticker = row["ticker"]
            # Skip non-ticker rows (Cash, headers, bold formatting)
            ticker_clean = ticker.replace("**", "").replace("*", "").strip()
            if not ticker_clean or not re.match(r'^[A-Z]{1,5}$', ticker_clean):
                continue
            row["ticker"] = ticker_clean

            # If no "action" column, infer from context
            if "action" not in row:
                # Tables in "What to Buy" section = BUY recommendations
                # Tables in "Your Portfolio" section = check for HOLD/SELL/BUY
                row["action"] = "BUY"  # default for watchlist tables

            # Clean action field (remove bold markers)
            if "action" in row:
                row["action"] = row["action"].replace("**", "").replace("*", "").strip()

            results.append(row)

    return results


def parse_thesis_sections(text):
    """
    Parse 'Thesis Per Pick' or similar sections for per-ticker thesis text.
    Returns dict mapping ticker -> thesis string.
    """
    theses = {}
    # Match lines like: - **GOOGL (44%):** AI + ads + cloud...
    # or: - **GOOGL:** AI + ads + cloud...
    pattern = re.compile(
        r"[-*]\s*\*{0,2}([A-Z]{1,5})(?:\s*\([^)]*\))?\s*:?\*{0,2}\s*:?\s*(.+)",
        re.MULTILINE,
    )
    for m in pattern.finditer(text):
        ticker = m.group(1).strip()
        thesis = m.group(2).strip()
        theses[ticker] = thesis
    return theses


def parse_avoid_section(text):
    """
    Parse 'What to Avoid' or 'SELL' sections.
    Returns list of (ticker, reason) tuples.
    """
    avoids = []
    # Find the avoid/sell section
    section_pat = re.compile(
        r"##\s*(?:What to Avoid|Avoid|Sells?|SELL Calls?).*?\n(.*?)(?=\n##|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    m = section_pat.search(text)
    if not m:
        return avoids

    section_text = m.group(1)
    # Parse lines like: - Consumer Discretionary (XLY): reason
    # or: - XLY: reason
    line_pat = re.compile(
        r"-\s*(?:[^(]*?\()?([A-Z]{1,5})\)?[:\s]*(.+)", re.MULTILINE
    )
    for lm in line_pat.finditer(section_text):
        ticker = lm.group(1).strip()
        reason = lm.group(2).strip()
        avoids.append((ticker, reason))
    return avoids


def parse_invalidation_conditions(text):
    """
    Parse 'Thesis Change Triggers' or similar sections.
    Returns dict mapping ticker -> condition string.
    """
    conditions = {}
    section_pat = re.compile(
        r"##\s*(?:Thesis Change Triggers|Invalidation|Stop Conditions).*?\n(.*?)(?=\n##|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    m = section_pat.search(text)
    if not m:
        return conditions

    section_text = m.group(1)
    # Look for ticker mentions in condition lines
    line_pat = re.compile(r"-\s*(.+)", re.MULTILINE)
    for lm in line_pat.finditer(section_text):
        line = lm.group(1)
        # Find tickers mentioned (uppercase 1-5 letter words that aren't common words)
        tickers_found = re.findall(r"\b([A-Z]{2,5})\b", line)
        common_words = {
            "THE", "AND", "FOR", "BUT", "NOT", "ALL", "HAS", "HAD",
            "ARE", "WAS", "CPI", "GDP", "FED", "VIX", "WTI", "IEA",
            "IF", "OR", "AT", "TO", "IN", "OF", "ON", "IS", "IT",
        }
        for t in tickers_found:
            if t not in common_words and len(t) >= 2:
                conditions.setdefault(t, []).append(line.strip())

    # Flatten condition lists
    return {k: "; ".join(v) for k, v in conditions.items()}


def extract_report_date(text):
    """Try to extract a date from the report header."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        return m.group(1)
    # Try M/D/YY or M/D/YYYY format
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", text)
    if m:
        month, day, year = m.groups()
        if len(year) == 2:
            year = "20" + year
        return "{}-{:02d}-{:02d}".format(year, int(month), int(day))
    return today()


def conviction_stars_to_level(raw):
    """Convert star-based conviction (e.g. '***') to HIGH/MEDIUM/LOW."""
    if not raw:
        return "MEDIUM"
    stars = raw.count("*")
    if stars >= 3:
        return "HIGH"
    elif stars == 2:
        return "MEDIUM"
    else:
        return "LOW"


def cmd_extract(args):
    """Extract theses from a report markdown file."""
    report_path = args.report
    if not os.path.isabs(report_path):
        # Try relative to CWD, then relative to project root
        if os.path.exists(report_path):
            report_path = os.path.abspath(report_path)
        else:
            project_root = os.path.dirname(SCRIPT_DIR)
            report_path = os.path.join(project_root, report_path)

    if not os.path.exists(report_path):
        print("ERROR: Report not found: {}".format(report_path))
        return

    with open(report_path, "r") as f:
        text = f.read()

    report_date = extract_report_date(text)

    # Parse components
    table_rows = parse_report_table(text)
    thesis_texts = parse_thesis_sections(text)
    avoid_list = parse_avoid_section(text)
    invalidation_conds = parse_invalidation_conditions(text)

    created = []
    updated = []
    flipped = []
    avoid_closed = []

    with VaultDB() as db:
        # --- Process BUY/HOLD table rows ---
        for row in table_rows:
            ticker = row["ticker"].upper()
            action = row.get("action", "").upper().strip()

            if action not in VALID_DIRECTIONS:
                # Try to extract just the direction keyword
                for d in VALID_DIRECTIONS:
                    if d in action:
                        action = d
                        break
                else:
                    continue

            conv_raw = row.get("conviction", "")
            conviction = conviction_stars_to_level(conv_raw)
            thesis_text = thesis_texts.get(ticker, "See report for details.")
            conditions = invalidation_conds.get(ticker, "")

            existing = db.get_thesis_full(ticker)

            if existing:
                # Check for flip
                old_dir = existing["direction"]
                if (old_dir, action) in FLIP_PAIRS:
                    flipped.append((ticker, old_dir, action, existing["date_opened"]))
                    print(
                        "\n*** WARNING: FLIP detected — {} was {} ({}) now {}. "
                        "Explain in report. ***\n".format(
                            ticker, old_dir, existing["date_opened"], action
                        )
                    )

                # Update existing thesis
                update_kwargs = {}
                if existing["direction"] != action:
                    update_kwargs["direction"] = action
                if _normalize_conviction(existing["conviction"]) != conviction:
                    update_kwargs["conviction"] = conviction
                if conditions:
                    update_kwargs["key_conditions"] = conditions
                if update_kwargs:
                    db.update_thesis(ticker, **update_kwargs)

                note = "Report {}: direction={}, conviction={}. {}".format(
                    report_date, action, conviction, thesis_text
                )
                db.add_thesis_history(ticker, note)
                updated.append(ticker)
            else:
                # Create new thesis
                if action in ("SELL", "AVOID"):
                    # Don't create new theses for SELL/AVOID — only for BUY/HOLD
                    continue
                success = db.add_thesis(
                    ticker=ticker,
                    direction=action,
                    conviction=conviction,
                    thesis=thesis_text,
                    key_conditions=conditions,
                    date_opened=report_date,
                    source_report=os.path.basename(report_path),
                )
                if success:
                    db.add_thesis_history(ticker, "Auto-extracted from report.")
                    created.append(ticker)

        # --- Process AVOID / SELL section ---
        for ticker, reason in avoid_list:
            existing = db.get_thesis_full(ticker)
            if existing:
                old_dir = existing["direction"]
                if (old_dir, "AVOID") in FLIP_PAIRS:
                    flipped.append((ticker, old_dir, "AVOID", existing["date_opened"]))
                    print(
                        "\n*** WARNING: FLIP detected — {} was {} ({}) now AVOID. "
                        "Explain in report. ***\n".format(
                            ticker, old_dir, existing["date_opened"]
                        )
                    )
                # Close the thesis
                close_note = "Closed by AVOID in report: {}".format(reason)
                db.close_thesis_with_status(ticker, status="INVALIDATED", note=close_note)
                avoid_closed.append(ticker)

        # Count active for summary
        all_theses = db.get_all_theses()
        total_active = sum(1 for e in all_theses if e["status"] == "ACTIVE")

    # --- Summary ---
    print("=" * 60)
    print("Thesis Extraction — Report {}".format(report_date))
    print("=" * 60)

    if created:
        print("\nCreated ({}):\n  {}".format(len(created), ", ".join(created)))
    if updated:
        print("\nUpdated ({}):\n  {}".format(len(updated), ", ".join(updated)))
    if avoid_closed:
        print(
            "\nClosed by AVOID ({}):\n  {}".format(
                len(avoid_closed), ", ".join(avoid_closed)
            )
        )
    if flipped:
        print("\nFLIPS DETECTED ({}):\n".format(len(flipped)))
        for ticker, old_dir, new_dir, date_opened in flipped:
            print(
                "  WARNING: {} was {} ({}) now {} — needs explanation".format(
                    ticker, old_dir, date_opened, new_dir
                )
            )

    if not (created or updated or avoid_closed or flipped):
        print("\nNo theses extracted. Check report format.")

    print("\nTotal active theses: {}".format(total_active))


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        description="Vault Research Desk — Thesis Tracker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command")

    # add
    p_add = subparsers.add_parser("add", help="Add a new thesis")
    p_add.add_argument("ticker", help="Stock ticker (e.g. AAPL)")
    p_add.add_argument("thesis", help="1-2 sentence thesis summary")
    p_add.add_argument(
        "--direction", "-d", required=True,
        choices=["BUY", "HOLD", "SELL", "AVOID"],
        help="Investment direction",
    )
    p_add.add_argument(
        "--conviction", "-c", required=True,
        choices=["HIGH", "MEDIUM", "LOW"],
        help="Conviction level",
    )
    p_add.add_argument(
        "--conditions", "-k", default="",
        help="What would invalidate this thesis",
    )

    # update
    p_update = subparsers.add_parser("update", help="Add a note to an active thesis")
    p_update.add_argument("ticker", help="Stock ticker")
    p_update.add_argument("note", help="Update note")
    p_update.add_argument(
        "--conviction", "-c", choices=["HIGH", "MEDIUM", "LOW"],
        help="Optionally change conviction",
    )
    p_update.add_argument(
        "--direction", "-d", choices=["BUY", "HOLD", "SELL", "AVOID"],
        help="Optionally change direction (will trigger flip detection)",
    )

    # check
    subparsers.add_parser("check", help="Review active theses for age/staleness")

    # close
    p_close = subparsers.add_parser("close", help="Close an active thesis")
    p_close.add_argument("ticker", help="Stock ticker")
    p_close.add_argument(
        "--status", "-s", required=True,
        choices=["CONFIRMED", "INVALIDATED", "EXPIRED"],
        help="Closing status",
    )
    p_close.add_argument(
        "--note", "-n", default="",
        help="Optional closing note",
    )

    # extract
    p_extract = subparsers.add_parser(
        "extract", help="Auto-extract theses from a report"
    )
    p_extract.add_argument("report", help="Path to report markdown file")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        cmd_show(args)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "update":
        cmd_update(args)
    elif args.command == "check":
        cmd_check(args)
    elif args.command == "close":
        cmd_close(args)
    elif args.command == "extract":
        cmd_extract(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
