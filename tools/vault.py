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


def cmd_health():
    """System health check — validates everything is working."""
    sys.path.insert(0, SCRIPT_DIR)

    checks = []
    warnings = []

    # 1. Database
    try:
        from db import VaultDB, DB_PATH
        if os.path.exists(DB_PATH):
            size_kb = os.path.getsize(DB_PATH) / 1024
            checks.append(f"Database: OK ({size_kb:.0f} KB)")
            with VaultDB() as db:
                holdings = db.get_holdings()
                checks.append(f"Holdings: {len(holdings)} positions in DB")
                if not holdings:
                    warnings.append("No holdings in DB — run `vault fetch` first")
        else:
            warnings.append("Database: vault.db not found — will be created on first use")
    except Exception as e:
        warnings.append(f"Database: ERROR — {e}")

    # 2. Portfolio.md
    portfolio_path = os.path.join(PROJECT_ROOT, "portfolio.md")
    if os.path.exists(portfolio_path):
        size = os.path.getsize(portfolio_path)
        checks.append(f"portfolio.md: OK ({size} bytes)")
        backup = portfolio_path + ".backup"
        if os.path.exists(backup):
            checks.append(f"portfolio.md.backup: exists (safety net)")
    else:
        warnings.append("portfolio.md: NOT FOUND — create it before running reports")

    # 3. API Keys
    finnhub = os.environ.get("FINNHUB_API_KEY", "")
    marketaux = os.environ.get("MARKETAUX_API_KEY", "")
    if finnhub:
        checks.append(f"FINNHUB_API_KEY: set ({finnhub[:4]}...)")
    else:
        warnings.append("FINNHUB_API_KEY: not set — news + analyst data unavailable")
    if marketaux:
        checks.append(f"MARKETAUX_API_KEY: set ({marketaux[:4]}...)")
    else:
        warnings.append("MARKETAUX_API_KEY: not set — sentiment scoring unavailable")

    # 4. Data freshness
    try:
        with VaultDB() as db:
            latest_quote = db.conn.execute(
                "SELECT max(fetched_at) as latest FROM price_cache"
            ).fetchone()
            if latest_quote and latest_quote['latest']:
                from datetime import datetime as dt
                fetched = dt.fromisoformat(latest_quote['latest'])
                age_hours = (dt.now() - fetched).total_seconds() / 3600
                if age_hours < 1:
                    checks.append(f"Price data: fresh ({age_hours:.0f}min old)")
                elif age_hours < 24:
                    checks.append(f"Price data: {age_hours:.0f}h old")
                else:
                    warnings.append(f"Price data: STALE ({age_hours:.0f}h old) — run `vault fetch`")
            else:
                warnings.append("Price data: NO DATA — run `vault fetch`")

            # Reports
            report_count = db.conn.execute("SELECT count(*) as c FROM reports").fetchone()
            checks.append(f"Reports: {report_count['c']} in DB")

            # Learnings
            learnings = db.conn.execute(
                "SELECT count(*) as c FROM learnings WHERE consumed=0"
            ).fetchone()
            if learnings['c'] > 0:
                checks.append(f"Unconsumed learnings: {learnings['c']}")

    except Exception as e:
        warnings.append(f"Data check: ERROR — {e}")

    # 5. Tool imports
    tool_ok = 0
    tool_fail = []
    for mod in ['data_fetcher', 'screener', 'alerts', 'scorer', 'correlation',
                'news', 'insider_check', 'smart_money', 'thesis_tracker',
                'watchlist_extract', 'learn_from_pros', 'html_report', 'ibkr_sync']:
        try:
            __import__(mod)
            tool_ok += 1
        except Exception as e:
            tool_fail.append(f"{mod}: {e}")

    checks.append(f"Tools: {tool_ok}/13 import OK")
    for f in tool_fail:
        warnings.append(f"Tool import failed: {f}")

    # 6. Reports directory
    reports_dir = os.path.join(PROJECT_ROOT, "reports")
    if os.path.isdir(reports_dir):
        import glob
        report_files = glob.glob(os.path.join(reports_dir, "report_*.md"))
        checks.append(f"Reports dir: {len(report_files)} report files")
    else:
        warnings.append("Reports dir: reports/ not found — will be created on first report")

    # Print results
    print()
    print(f"{'=' * 50}")
    print(f"  SYSTEM HEALTH CHECK")
    print(f"{'=' * 50}")
    print()
    for c in checks:
        print(f"  [OK] {c}")
    if warnings:
        print()
        for w in warnings:
            print(f"  [!!] {w}")
    else:
        print()
        print("  All systems operational.")
    print()
    total = len(checks) + len(warnings)
    print(f"  {len(checks)}/{total} checks passed"
          f"{f', {len(warnings)} warnings' if warnings else ''}")
    print(f"{'=' * 50}")
    print()


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
    print("    vault health             System health check")
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
    "health":      lambda args: cmd_health(),
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
