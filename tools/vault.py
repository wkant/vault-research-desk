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
import json

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


def cmd_search_log(args):
    """Generate Search Log for report from cached price data."""
    sys.path.insert(0, SCRIPT_DIR)
    from db import VaultDB
    with VaultDB() as db:
        # Get all tickers that should appear: holdings + watchlist + any extras from args
        tickers = set()
        for h in db.get_holdings():
            tickers.add(h['ticker'])
        for w in db.get_active_watchlist():
            tickers.add(w['ticker'])
        if args:
            for t in args:
                tickers.add(t.upper())
        if not tickers:
            print("No tickers found. Add holdings to portfolio.md or pass tickers as arguments.")
            return
        print(db.generate_search_log(tickers))


def cmd_preflight(args):
    """Phase 0: Run all data collection tools before a report."""
    print()
    print(f"{'=' * 55}")
    print(f"  PHASE 0 — PRE-REPORT DATA COLLECTION")
    print(f"{'=' * 55}")
    print()

    steps = [
        ("Data Fetch (prices, technicals, breadth, news)", "data_fetcher.py", None, 600),
        ("Screener (quick 50-stock scan)", "screener.py", ["--sample", "50"], 300),
        ("Correlation matrix", "correlation.py", None, 120),
        ("Thesis check", "thesis_tracker.py", ["check"], 60),
        ("Insider activity (portfolio)", "insider_check.py", ["--portfolio"], 120),
        ("Self-analyze (refresh auto-patches)", "self_analyze.py", None, 120),
    ]

    results = []
    for label, script, tool_args, timeout in steps:
        print(f"  [{len(results)+1}/{len(steps)}] {label}...")
        rc = run_tool(script, tool_args, timeout=timeout)
        status = "OK" if rc == 0 else f"WARN (exit {rc})"
        results.append((label, status))
        print()

    print(f"{'=' * 55}")
    print(f"  PRE-FLIGHT SUMMARY")
    print(f"{'=' * 55}")
    for label, status in results:
        icon = "[OK]" if "OK" in status else "[!!]"
        print(f"  {icon} {label}: {status}")

    ok_count = sum(1 for _, s in results if "OK" in s)
    print(f"\n  {ok_count}/{len(results)} steps completed successfully")
    if ok_count == len(results):
        print("  Ready for report generation!")
    else:
        print("  Some steps had issues — review output above")
    print(f"{'=' * 55}")
    print()


def cmd_audit(args):
    """Audit the latest report for pipeline compliance."""
    import glob
    import re

    reports_dir = os.path.join(PROJECT_ROOT, "reports")
    if args:
        report_path = args[0]
    else:
        md_files = sorted(glob.glob(os.path.join(reports_dir, "report_*.md")))
        if not md_files:
            print("No reports found in reports/")
            return
        report_path = md_files[-1]

    with open(report_path, "r") as f:
        content = f.read()

    filename = os.path.basename(report_path)
    content_lower = content.lower()
    checks = []
    warnings = []
    fails = []

    # 1. Devil's Gate / Validation Summary
    has_dg = any(term in content_lower for term in [
        "validation summary", "devil's gate", "devils gate",
        "test 0:", "test 1:", "approved with flags", "approved"
    ])
    if has_dg:
        checks.append("Devil's Gate: present")
    else:
        fails.append("Devil's Gate: NOT FOUND — validation summary missing from report")

    # 2. Search Log
    has_search_log = "search log" in content_lower
    if has_search_log:
        checks.append("Search Log: present")
    else:
        warnings.append("Search Log: not found in report (mandated by 00_system.md)")

    # 3. Price Verification
    has_price_verify = "price verification" in content_lower or "all prices verified" in content_lower
    if has_price_verify:
        checks.append("Price Verification: present")
    else:
        warnings.append("Price Verification: sign-off not found")

    # 4. Gut Check (mandatory)
    has_gut = "gut check" in content_lower
    if has_gut:
        checks.append("Gut Check: present")
    else:
        fails.append("Gut Check: MISSING — this section is mandatory")

    # 5. Stop-losses on BUY recommendations
    buy_section = ""
    in_buy = False
    for line in content.split("\n"):
        if re.match(r"^#{1,3}\s.*(?:what to buy|new buy|buy recommendations)", line, re.IGNORECASE):
            in_buy = True
            continue
        if in_buy and re.match(r"^#{1,3}\s", line):
            break
        if in_buy:
            buy_section += line + "\n"

    if buy_section:
        ticker_rows = re.findall(r"\|\s*([A-Z]{1,5})\s*\|", buy_section)
        stop_mentions = len(re.findall(r"stop|Stop|\$\d+.*(?:stop|support|DMA)", buy_section, re.IGNORECASE))
        if ticker_rows and stop_mentions == 0:
            fails.append(f"Stop-Loss: {len(ticker_rows)} BUY picks found but no stop-loss mentions")
        elif ticker_rows:
            checks.append(f"Stop-Loss: {len(ticker_rows)} BUY picks with stop references")

    # 6. Benchmark comparison
    has_bench = "voo" in content_lower
    if has_bench:
        checks.append("Benchmark (VOO): referenced")
    else:
        warnings.append("Benchmark: no VOO comparison found")

    # 7. Biggest Risks / Doomsday
    has_risks = "biggest risk" in content_lower or "doomsday" in content_lower
    if has_risks:
        checks.append("Risk Section: present")
    else:
        warnings.append("Risk Section: no 'Biggest Risks' or doomsday scenario found")

    # 8. Profit-taking check for existing holdings
    has_profit_taking = any(term in content_lower for term in ["trim", "profit-taking", "profit taking", "+30%", "+50%"])
    if has_profit_taking:
        checks.append("Profit-Taking: referenced")
    else:
        warnings.append("Profit-Taking: no trim/profit-taking language found")

    # 9. Report length
    word_count = len(content.split())
    if word_count < 300:
        warnings.append(f"Length: {word_count} words — very short")
    elif word_count > 3000:
        warnings.append(f"Length: {word_count} words — very long, may lose focus")
    else:
        checks.append(f"Length: {word_count} words")

    # Print results
    print()
    print(f"{'=' * 55}")
    print(f"  REPORT AUDIT — {filename}")
    print(f"{'=' * 55}")
    print()

    for c in checks:
        print(f"  [OK] {c}")

    if warnings:
        print()
        for w in warnings:
            print(f"  [!!] {w}")

    if fails:
        print()
        for f_item in fails:
            print(f"  [FAIL] {f_item}")

    print()
    total = len(checks) + len(warnings) + len(fails)
    score = len(checks) / total * 100 if total else 0
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D"
    print(f"  Score: {len(checks)}/{total} passed ({score:.0f}%) — Grade: {grade}")
    if fails:
        print(f"  {len(fails)} CRITICAL issue(s) need fixing before next report")
    print(f"{'=' * 55}")
    print()


def cmd_validate(args):
    """Pre-report validation gate — blocks report if critical checks fail."""
    import glob
    import re
    sys.path.insert(0, SCRIPT_DIR)
    from db import VaultDB

    print()
    print(f"{'=' * 55}")
    print(f"  PRE-REPORT VALIDATION GATE")
    print(f"{'=' * 55}")
    print()

    checks = []
    blockers = []

    with VaultDB() as db:
        # 1. Data freshness
        latest = db.conn.execute("SELECT max(fetched_at) as l FROM price_cache").fetchone()
        if latest and latest['l']:
            from datetime import datetime as dt
            age_h = (dt.now() - dt.fromisoformat(latest['l'])).total_seconds() / 3600
            if age_h > 24:
                blockers.append(f"Price data is {age_h:.0f}h stale — run `vault fetch` first")
            else:
                checks.append(f"Price data: {age_h:.0f}h old")
        else:
            blockers.append("No price data — run `vault fetch` first")

        # 2. Holdings synced
        holdings = db.get_holdings()
        if holdings:
            checks.append(f"Holdings: {len(holdings)} in DB")
        else:
            blockers.append("No holdings in DB — run `vault fetch`")

        # 3. Active improvements checked (concentration blockers)
        improvements = db.get_active_improvements()
        high = [i for i in improvements if i['priority'] == 'HIGH']
        if high:
            checks.append(f"Active issues: {len(high)} HIGH priority (acknowledged)")
        else:
            checks.append("No high-priority issues")

        # 4. Thesis tracker
        theses = db.get_active_theses()
        stale = [t for t in theses
                 if (dt.now().date() - dt.strptime(t['date_opened'], '%Y-%m-%d').date()).days > 90]
        if stale:
            checks.append(f"Stale theses: {len(stale)} (>90 days) — review before report")
        else:
            checks.append(f"Active theses: {len(theses)} (none stale)")

        # 5. Regime detection
        regime = db.detect_regime()
        if regime['regime'] != 'UNKNOWN':
            checks.append(f"Market regime: {regime['regime']} ({regime['confidence']}%)")
        else:
            blockers.append("No market snapshot — run `vault fetch` for regime detection")

        # 6. Smart money divergence
        divs = db.detect_smart_money_divergence()
        if divs:
            for d in divs[:3]:
                checks.append(f"Divergence: {d['ticker']} — bull({','.join(d['bullish_sources'])}) vs bear({','.join(d['bearish_sources'])})")

    # Print
    for c in checks:
        print(f"  [OK] {c}")
    if blockers:
        print()
        for b in blockers:
            print(f"  [BLOCK] {b}")

    print()
    if blockers:
        print(f"  RESULT: BLOCKED — {len(blockers)} issue(s) must be resolved")
        print(f"  Fix blockers, then run `vault validate` again")
    else:
        print(f"  RESULT: PASSED — ready for report generation")
        print(f"  All {len(checks)} pre-flight checks passed")
    print(f"{'=' * 55}")
    print()


def cmd_drift(args):
    """Portfolio drift dashboard."""
    sys.path.insert(0, SCRIPT_DIR)
    from db import VaultDB

    with VaultDB() as db:
        drift = db.portfolio_drift()
        if not drift:
            print("No holdings found.")
            return

        print()
        print(f"{'=' * 60}")
        print(f"  PORTFOLIO DRIFT ANALYSIS")
        print(f"{'=' * 60}")
        print(f"  Total value: ${drift['total_value']:,.2f}")
        print(f"  Target per position: {drift['target_per_position']:.1f}%")
        print()
        print(f"  {'Ticker':<8} {'Value':>10} {'Actual':>8} {'Target':>8} {'Drift':>8} {'Action'}")
        print(f"  {'─' * 56}")

        for p in drift['positions']:
            action_str = p['action']
            if p['action'] == 'TRIM':
                action_str = f"TRIM (over by {p['drift_pct']:.1f}%)"
            elif p['action'] == 'ADD':
                action_str = f"ADD (under by {abs(p['drift_pct']):.1f}%)"

            print(f"  {p['ticker']:<8} ${p['market_value']:>9,.2f} {p['actual_pct']:>7.1f}% {p['target_pct']:>7.1f}% {p['drift_pct']:>+7.1f}% {action_str}")

        print(f"{'=' * 60}")
        print()


def cmd_size(args):
    """Position sizing calculator."""
    if not args or len(args) < 1:
        print("Usage: vault size TICKER [--conviction ***|**|*] [--entry PRICE]")
        return

    sys.path.insert(0, SCRIPT_DIR)
    from db import VaultDB

    ticker = args[0].upper()
    conviction = '**'
    entry = None

    for i, a in enumerate(args[1:], 1):
        if a in ('***', '**', '*'):
            conviction = a
        elif a == '--conviction' and i + 1 < len(args):
            conviction = args[i + 1]
        elif a == '--entry' and i + 1 < len(args):
            try:
                entry = float(args[i + 1].replace('$', ''))
            except ValueError:
                pass
        else:
            try:
                val = float(a.replace('$', ''))
                if val > 10:
                    entry = val
                else:
                    conviction = a
            except ValueError:
                pass

    with VaultDB() as db:
        # Try to get current price if no entry specified
        if not entry:
            cached = db.get_cached_quote(ticker, max_age_minutes=1440)
            if cached and cached.get('price'):
                entry = cached['price']

        result = db.calculate_position_size(ticker, conviction, entry)
        if not result:
            print("No portfolio data. Run `vault fetch` first.")
            return

        print()
        print(f"{'=' * 55}")
        print(f"  POSITION SIZING — {ticker}")
        print(f"{'=' * 55}")
        print(f"  Conviction: {conviction}")
        print(f"  Portfolio: ${result['portfolio_value']:,.2f}")
        print(f"  Max position: {result['max_position_pct']}%")
        if result['existing_pct'] > 0:
            print(f"  Existing: {result['existing_pct']:.1f}%")
        print(f"  Available: {result['available_pct']:.1f}% = ${result['max_investment']:,.2f}")

        if entry:
            print(f"\n  Entry: ${entry:.2f}")
            print(f"  Stop: ${result['stop_price']:.2f} ({result['stop_distance_pct']:.0f}% below)")
            print()
            print(f"  SCALING PLAN:")
            for t in result['tranches']:
                shares = t['shares']
                print(f"    {t['label']}: ${t['amount']:,.2f} ({shares:.4f} shares)")
        else:
            print("\n  Add --entry PRICE for scaling plan")

        print(f"{'=' * 55}")
        print()


def cmd_convert(args):
    """Convert watchlist pick to trade."""
    if not args or len(args) < 1:
        print("Usage: vault convert TICKER PRICE SHARES")
        print("  Example: vault convert XOM 156.12 5")
        return

    sys.path.insert(0, SCRIPT_DIR)
    from db import VaultDB

    ticker = args[0].upper()
    price = float(args[1].replace('$', '')) if len(args) > 1 else 0
    shares = float(args[2]) if len(args) > 2 else 0

    if not price:
        print("Error: price required. vault convert TICKER PRICE SHARES")
        return

    with VaultDB() as db:
        result = db.convert_watchlist_to_trade(ticker, price, shares)

    print(f"Converted {ticker}:")
    print(f"  Price: ${result['price']:.2f}")
    print(f"  Shares: {shares}")
    if result['from_watchlist']:
        print(f"  Was on watchlist at ${result['rec_price']:.2f}")
        gain = (price - result['rec_price']) / result['rec_price'] * 100
        print(f"  Entry vs recommendation: {gain:+.1f}%")
    print(f"  Trade logged in vault.db")
    print(f"  Remember to update portfolio.md!")


def cmd_journal(args):
    """Trade journal — reflect on trades."""
    sys.path.insert(0, SCRIPT_DIR)
    from db import VaultDB

    if not args:
        # Show recent entries
        with VaultDB() as db:
            entries = db.get_journal_entries(limit=10)
        if not entries:
            print("No journal entries. Usage: vault journal TICKER \"reflection text\"")
            return

        print()
        print(f"{'=' * 55}")
        print(f"  TRADE JOURNAL (last {len(entries)} entries)")
        print(f"{'=' * 55}")
        for e in entries:
            meta = json.loads(e['meta']) if e['meta'] else {}
            ticker = meta.get('ticker', e['source'] if e['source'] else '?')
            print(f"\n  [{e['date']}] {ticker}")
            print(f"  {e['finding']}")
            if e['action']:
                print(f"  Lesson: {e['action']}")
        print(f"{'=' * 55}")
        return

    ticker = args[0].upper()
    reflection = ' '.join(args[1:]) if len(args) > 1 else None

    if not reflection:
        # Show entries for this ticker
        with VaultDB() as db:
            entries = db.get_journal_entries(ticker=ticker)
        if entries:
            print(f"\nJournal for {ticker}:")
            for e in entries:
                print(f"  [{e['date']}] {e['finding']}")
        else:
            print(f"No journal entries for {ticker}")
        print(f"\nAdd entry: vault journal {ticker} \"your reflection\"")
        return

    with VaultDB() as db:
        db.add_journal_entry(ticker, reflection=reflection)
    print(f"Journal entry saved for {ticker}")


def cmd_simulate(args):
    """Simulate adding positions to portfolio."""
    if not args or len(args) < 2:
        print("Usage: vault simulate TICKER1 AMOUNT1 [TICKER2 AMOUNT2 ...]")
        print("  Example: vault simulate XOM 1000 LMT 800 XLU 700")
        return

    sys.path.insert(0, SCRIPT_DIR)
    from db import VaultDB

    positions = []
    i = 0
    while i < len(args) - 1:
        ticker = args[i].upper()
        try:
            amount = float(args[i + 1].replace('$', '').replace(',', ''))
            positions.append({'ticker': ticker, 'amount': amount})
            i += 2
        except (ValueError, IndexError):
            i += 1

    if not positions:
        print("Could not parse positions. Use: TICKER AMOUNT pairs")
        return

    with VaultDB() as db:
        result = db.simulate_additions(positions)

    print()
    print(f"{'=' * 60}")
    print(f"  PORTFOLIO SIMULATION")
    print(f"{'=' * 60}")
    print(f"  Current: ${result['current_total']:,.2f}")
    print(f"  Adding: ${result['added']:,.2f}")
    print(f"  New total: ${result['new_total']:,.2f}")
    print(f"  Positions: {result['position_count']}")
    print()
    print(f"  {'Ticker':<8} {'Value':>10} {'Before':>8} {'After':>8} {'Change':>8} {'Note'}")
    print(f"  {'─' * 58}")

    for p in result['positions']:
        note = "NEW" if p['is_new'] else ""
        print(f"  {p['ticker']:<8} ${p['current_value']:>9,.2f} {p['current_pct']:>7.1f}% {p['new_pct']:>7.1f}% {p['change_pct']:>+7.1f}% {note}")

    if result['violations']:
        print()
        print(f"  VIOLATIONS:")
        for v in result['violations']:
            print(f"    [!] {v}")
    else:
        print(f"\n  No allocation violations detected")

    print(f"{'=' * 60}")
    print()


def cmd_compare(args):
    """Compare two reports."""
    if not args or len(args) < 2:
        print("Usage: vault compare DATE1 DATE2")
        print("  Example: vault compare 2026-03-11 2026-03-15")
        return

    sys.path.insert(0, SCRIPT_DIR)
    from db import VaultDB

    date1, date2 = args[0], args[1]

    with VaultDB() as db:
        result = db.compare_reports(date1, date2)

    print()
    print(f"{'=' * 60}")
    print(f"  REPORT COMPARISON: {date1} vs {date2}")
    print(f"{'=' * 60}")

    changes = result['changes']
    new = [c for c in changes if c['type'] == 'NEW']
    dropped = [c for c in changes if c['type'] == 'DROPPED']
    flipped = [c for c in changes if c['type'] == 'FLIPPED']
    conv_changes = [c for c in changes if c['type'] == 'CONVICTION_CHANGE']
    unchanged = [c for c in changes if c['type'] == 'UNCHANGED']

    if new:
        print(f"\n  NEW PICKS ({len(new)}):")
        for c in new:
            print(f"    + {c['ticker']} — {c['new']['direction']} {c['new']['conviction']}")
    if dropped:
        print(f"\n  DROPPED ({len(dropped)}):")
        for c in dropped:
            print(f"    - {c['ticker']} — was {c['old']['direction']} {c['old']['conviction']}")
    if flipped:
        print(f"\n  FLIPPED ({len(flipped)}):")
        for c in flipped:
            print(f"    ! {c['ticker']} — {c['old']['direction']} -> {c['new']['direction']}")
    if conv_changes:
        print(f"\n  CONVICTION CHANGES ({len(conv_changes)}):")
        for c in conv_changes:
            print(f"    ~ {c['ticker']} — {c['old']['conviction']} -> {c['new']['conviction']}")
    if unchanged:
        print(f"\n  UNCHANGED ({len(unchanged)}):")
        for c in unchanged:
            print(f"    = {c['ticker']} — {c['new']['direction']} {c['new']['conviction']}")

    b1, b2 = result.get('bench1'), result.get('bench2')
    if b1 and b2:
        print(f"\n  BENCHMARK:")
        print(f"    {date1}: portfolio {b1.get('portfolio_pct', 0):+.2f}% | VOO {b1.get('voo_pct', 0):+.2f}% | alpha {b1.get('alpha', 0):+.2f}%")
        print(f"    {date2}: portfolio {b2.get('portfolio_pct', 0):+.2f}% | VOO {b2.get('voo_pct', 0):+.2f}% | alpha {b2.get('alpha', 0):+.2f}%")

    print(f"{'=' * 60}")
    print()


def cmd_regime(args):
    """Market regime detection."""
    sys.path.insert(0, SCRIPT_DIR)
    from db import VaultDB

    with VaultDB() as db:
        regime = db.detect_regime()

    if regime['regime'] == 'UNKNOWN':
        print("No market data. Run `vault fetch` first.")
        return

    print()
    print(f"{'=' * 55}")
    print(f"  MARKET REGIME — {regime['date']}")
    print(f"{'=' * 55}")
    print(f"  Regime: {regime['regime']} ({regime['confidence']}% confidence)")
    print(f"  Posture: {regime['posture']}")
    print(f"  Risk-On: {regime['risk_on_score']} | Risk-Off: {regime['risk_off_score']}")
    print()
    print(f"  {'Signal':<12} {'Value':>8} {'Reading':<28} {'Direction'}")
    print(f"  {'─' * 60}")
    for signal, value, reading, direction in regime['signals']:
        print(f"  {signal:<12} {value:>8} {reading:<28} {direction}")
    print(f"{'=' * 55}")
    print()


def cmd_backtest(args):
    """Backtest historical recommendations."""
    sys.path.insert(0, SCRIPT_DIR)
    from db import VaultDB

    conviction = args[0] if args else None

    with VaultDB() as db:
        result = db.backtest_recommendations(conviction)

    if not result:
        print("No closed trades to backtest.")
        return

    print()
    print(f"{'=' * 55}")
    print(f"  BACKTEST RESULTS")
    print(f"{'=' * 55}")
    print(f"  Total closed trades: {result['total']}")
    print(f"  Cumulative return: {result['cumulative_return']:+.1f}%")
    print(f"  Max drawdown: {result['max_drawdown']:.1f}%")
    print()

    print("  BY CONVICTION:")
    for conv in ['***', '**', '*']:
        if conv in result['by_conviction']:
            b = result['by_conviction'][conv]
            print(f"    {conv}: {b['count']} trades, win rate {b['win_rate']:.0f}%, avg return {b['avg_return']:+.1f}%")

    if result['by_year']:
        print("\n  BY YEAR:")
        for year, data in sorted(result['by_year'].items()):
            print(f"    {year}: {data['count']} trades, total return {data['total_return']:+.1f}%")

    print(f"{'=' * 55}")
    print()


def cmd_peers(args):
    """Peer portfolio comparison."""
    sys.path.insert(0, SCRIPT_DIR)
    from db import VaultDB

    with VaultDB() as db:
        peers = db.peer_comparison()

    if not peers:
        print("No peer data. Run `vault learn` first.")
        return

    print()
    print(f"{'=' * 55}")
    print(f"  PEER COMPARISON")
    print(f"{'=' * 55}")

    for name, data in peers.items():
        overlap = data['overlap_count']
        total = data['total_positions']
        overlap_str = ', '.join(data['overlap'][:5]) if data['overlap'] else 'none'
        print(f"\n  {name}")
        print(f"    Positions: {total} | Overlap: {overlap}")
        if data['overlap']:
            print(f"    Shared: {overlap_str}")
        if data['top5']:
            top = ', '.join(f"{t}({p:.1f}%)" for t, p in data['top5'])
            print(f"    Top 5: {top}")

    print(f"\n{'=' * 55}")
    print()


def cmd_skeleton(args):
    """Generate pre-filled report skeleton."""
    sys.path.insert(0, SCRIPT_DIR)
    from db import VaultDB
    from datetime import datetime as dt

    with VaultDB() as db:
        skeleton = db.generate_report_skeleton()

    filename = f"reports/report_{dt.now().strftime('%Y-%m-%d')}_draft.md"
    filepath = os.path.join(PROJECT_ROOT, filename)

    with open(filepath, 'w') as f:
        f.write(skeleton)

    print(f"Report skeleton saved: {filename}")
    print(f"  Pre-filled: Search Log, Portfolio, Benchmark, Regime")
    print(f"  TODO sections marked for manual completion")
    print(f"  Edit, then run `report` to finalize")


def cmd_weekly(args):
    """Full weekly pipeline: preflight → skeleton → audit."""
    print()
    print(f"{'=' * 55}")
    print(f"  WEEKLY PIPELINE")
    print(f"{'=' * 55}")
    print()

    # Step 1: Preflight
    print("  STEP 1: Pre-flight data collection")
    print(f"  {'─' * 50}")
    cmd_preflight(None)

    # Step 2: Validate
    print("\n  STEP 2: Pre-report validation")
    print(f"  {'─' * 50}")
    cmd_validate(None)

    # Step 3: Generate skeleton
    print("\n  STEP 3: Report skeleton")
    print(f"  {'─' * 50}")
    cmd_skeleton(None)

    # Step 4: Regime check
    print("\n  STEP 4: Market regime")
    print(f"  {'─' * 50}")
    cmd_regime(None)

    print()
    print(f"{'=' * 55}")
    print("  NEXT STEPS:")
    print("  1. Review the draft report skeleton")
    print("  2. Run `report` to generate full analysis")
    print("  3. After report: `vault audit` to check quality")
    print("  4. Run `vault score` to update performance")
    print(f"{'=' * 55}")
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
    print("    vault regime             Market regime detection (risk-on/off)")
    print()
    print("  Research:")
    print("    vault preflight          Phase 0: all data collection before report")
    print("    vault fetch              Full data fetch (prices + technicals)")
    print("    vault screen             S&P 500 screener")
    print("    vault screen --sample 50 Quick scan (50 random tickers)")
    print("    vault news GOOGL         News for specific tickers")
    print()
    print("  Analysis:")
    print("    vault insider GOOGL      Check insider activity")
    print("    vault insider --portfolio Check all holdings")
    print("    vault correlation        Portfolio correlation matrix")
    print("    vault smart-money GOOGL  Full smart money check")
    print("    vault learn              Fetch + analyze smart money signals")
    print("    vault theses             Show active investment theses")
    print("    vault peers              Compare portfolio to top investors")
    print("    vault backtest           Backtest closed trade history")
    print()
    print("  Portfolio:")
    print("    vault drift              Allocation drift analysis")
    print("    vault size TICKER [***]  Position sizing calculator")
    print("    vault simulate T1 $X ... Simulate adding new positions")
    print("    vault convert TICKER P S Convert watchlist pick to trade")
    print("    vault journal [TICKER]   Trade journal / reflections")
    print()
    print("  Report Pipeline:")
    print("    vault weekly             Full weekly pipeline (auto)")
    print("    vault skeleton           Generate pre-filled report draft")
    print("    vault validate           Pre-report validation gate")
    print("    vault search-log         Generate Search Log from cache")
    print("    vault audit              Audit report for compliance")
    print("    vault compare D1 D2      Compare two reports side-by-side")
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
    "rebalance":   lambda args: run_tool("correlation.py", args),
    "sync":        lambda args: run_tool("ibkr_sync.py", args),
    "search-log":  lambda args: cmd_search_log(args),
    "preflight":   lambda args: cmd_preflight(args),
    "validate":    lambda args: cmd_validate(args),
    "drift":       lambda args: cmd_drift(args),
    "size":        lambda args: cmd_size(args),
    "convert":     lambda args: cmd_convert(args),
    "journal":     lambda args: cmd_journal(args),
    "simulate":    lambda args: cmd_simulate(args),
    "compare":     lambda args: cmd_compare(args),
    "regime":      lambda args: cmd_regime(args),
    "backtest":    lambda args: cmd_backtest(args),
    "peers":       lambda args: cmd_peers(args),
    "skeleton":    lambda args: cmd_skeleton(args),
    "weekly":      lambda args: cmd_weekly(args),
    "audit":       lambda args: cmd_audit(args),
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
