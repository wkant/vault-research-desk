#!/usr/bin/env python3
"""
vault — Unified CLI for the Vault Research Desk

One command to rule them all. Routes to the right tool with minimal friction.

Usage:
    python3 tools/vault.py morning              Morning briefing (portfolio + theses + watchlist + learnings)
    python3 tools/vault.py score                Performance scorecard with trending
    python3 tools/vault.py alerts               Check alert conditions from latest report
    python3 tools/vault.py screen [--sample N]  S&P 500 screener
    python3 tools/vault.py news [TICKER...]     Fetch news (or --portfolio, --market)
    python3 tools/vault.py insider [TICKER...]  Check insider buying/selling (or --portfolio)
    python3 tools/vault.py correlation          Portfolio correlation matrix
    python3 tools/vault.py learn                Fetch smart money data + cross-reference portfolio
    python3 tools/vault.py theses               Show active theses
    python3 tools/vault.py smart-money TICKER   Full smart money check for a ticker
    python3 tools/vault.py fetch [TICKER...]    Run data fetcher (or --portfolio-only)
    python3 tools/vault.py changes              What changed since last report
    python3 tools/vault.py help                 Show this help
"""

import os
import sys
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, "..")
PYTHON = sys.executable


def run_tool(script, args=None, timeout=300):
    """Run a tool script and stream output."""
    cmd = [PYTHON, os.path.join(SCRIPT_DIR, script)]
    if args:
        cmd.extend(args)
    try:
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, timeout=timeout)
        return result.returncode
    except subprocess.TimeoutExpired:
        print(f"\nTimeout after {timeout}s. Try a smaller scope.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


def cmd_morning():
    """Morning briefing."""
    sys.path.insert(0, SCRIPT_DIR)
    from db import VaultDB
    with VaultDB() as db:
        print(db.morning_briefing())


def cmd_changes():
    """What changed since last report."""
    sys.path.insert(0, SCRIPT_DIR)
    from db import VaultDB
    with VaultDB() as db:
        print(db.changes_since_last_report())


def cmd_help():
    """Print help."""
    print()
    print("=" * 55)
    print("  VAULT RESEARCH DESK — Command Reference")
    print("=" * 55)
    print()
    print("  Daily:")
    print("    vault morning            Full overview (start here)")
    print("    vault changes            What moved since last report")
    print("    vault alerts             Check alert thresholds")
    print("    vault score              Performance scorecard")
    print()
    print("  Research:")
    print("    vault fetch              Full data fetch (macro + sectors + portfolio)")
    print("    vault fetch --portfolio-only   Portfolio data only (faster)")
    print("    vault screen             S&P 500 screener (full scan)")
    print("    vault screen --sample 50 Quick scan (50 random tickers)")
    print("    vault news GOOGL NVDA    News for specific tickers")
    print("    vault news --portfolio   News for all holdings")
    print("    vault news --market      General market news")
    print()
    print("  Analysis:")
    print("    vault insider GOOGL      Check insider activity")
    print("    vault insider --portfolio Check all holdings")
    print("    vault correlation        Portfolio correlation matrix")
    print("    vault smart-money GOOGL  Full smart money check")
    print("    vault learn              Fetch + analyze smart money signals")
    print("    vault theses             Show active investment theses")
    print()
    print("  System:")
    print("    vault self-analyze       System self-review")
    print("    vault dashboard          Portfolio P&L (quick)")
    print("    vault help               This help")
    print()
    print("  Tip: Start each day with `vault morning`")
    print()


# ── Route commands ────────────────────────────────────────────────

COMMANDS = {
    "morning":     lambda args: cmd_morning(),
    "changes":     lambda args: cmd_changes(),
    "score":       lambda args: run_tool("scorer.py"),
    "alerts":      lambda args: run_tool("alerts.py", args),
    "screen":      lambda args: run_tool("screener.py", args),
    "news":        lambda args: run_tool("news.py", args),
    "insider":     lambda args: run_tool("insider_check.py", args),
    "correlation": lambda args: run_tool("correlation.py", args),
    "learn":       lambda args: run_tool("learn_from_pros.py", args),
    "theses":      lambda args: run_tool("thesis_tracker.py", args if args else []),
    "smart-money": lambda args: run_tool("db.py", ["smart-money"] + (args or [])),
    "fetch":       lambda args: run_tool("data_fetcher.py", args, timeout=600),
    "self-analyze": lambda args: run_tool("self_analyze.py"),
    "dashboard":   lambda args: run_tool("db.py", ["dashboard"]),
    "help":        lambda args: cmd_help(),
}

# Aliases
COMMANDS["m"] = COMMANDS["morning"]
COMMANDS["s"] = COMMANDS["score"]
COMMANDS["a"] = COMMANDS["alerts"]
COMMANDS["n"] = COMMANDS["news"]
COMMANDS["c"] = COMMANDS["changes"]
COMMANDS["h"] = COMMANDS["help"]


def main():
    if len(sys.argv) < 2:
        cmd_help()
        return

    command = sys.argv[1].lower()
    args = sys.argv[2:] if len(sys.argv) > 2 else None

    if command in COMMANDS:
        COMMANDS[command](args)
    else:
        print(f"Unknown command: {command}")
        print(f"Run 'vault help' for available commands.")
        sys.exit(1)


if __name__ == "__main__":
    main()
