#!/usr/bin/env python3
"""
Vault Research Desk — Self-Analysis Engine
Analyzes all past reports, trades, and performance data to identify
patterns, mistakes, and improvement opportunities.

Usage:
    python3 tools/self_analyze.py

Output:
    All results stored in vault.db (improvements table).
"""

import sys
import os
import re
import glob
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.join(SCRIPT_DIR, "..")
REPORTS_DIR = os.path.join(PROJECT_DIR, "reports")
TRADES_DIR = os.path.join(PROJECT_DIR, "trades")
PORTFOLIO_PATH = os.path.join(PROJECT_DIR, "portfolio.md")

sys.path.insert(0, SCRIPT_DIR)

from db import VaultDB

try:
    import yfinance as yf
    import pandas as pd
    from data_fetcher import fetch_quote, fetch_technicals
except ImportError:
    print("ERROR: Required packages not installed.")
    sys.exit(1)


def fetch_historical_price(ticker, date_str):
    """Get closing price for a ticker on a specific date (or nearest trading day)."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        start = (dt - timedelta(days=7)).strftime("%Y-%m-%d")
        end = (dt + timedelta(days=3)).strftime("%Y-%m-%d")
        t = yf.Ticker(ticker)
        hist = t.history(start=start, end=end)
        if hist.empty:
            return None
        # Make index timezone-naive for comparison
        hist.index = hist.index.tz_localize(None)
        target = pd.Timestamp(dt)
        # Find closest date on or before the target
        valid = hist.index[hist.index <= target]
        if len(valid) > 0:
            return round(float(hist.loc[valid[-1]]["Close"]), 2)
        # Fallback: take the first available
        return round(float(hist.iloc[0]["Close"]), 2)
    except Exception:
        return None


def load_reports():
    """Load all report markdown files."""
    reports = []
    pattern = os.path.join(REPORTS_DIR, "report_*.md")
    for path in sorted(glob.glob(pattern)):
        filename = os.path.basename(path)
        date_match = re.search(r"report_(\d{4}-\d{2}-\d{2})", filename)
        date = date_match.group(1) if date_match else "unknown"
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        reports.append({"date": date, "path": path, "content": content})
    return reports


def load_trades():
    """Load all trade log files."""
    trades = []
    pattern = os.path.join(TRADES_DIR, "trade_*.md")
    for path in sorted(glob.glob(pattern)):
        filename = os.path.basename(path)
        date_match = re.search(r"trade_(\d{4}-\d{2}-\d{2})", filename)
        date = date_match.group(1) if date_match else "unknown"
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        trades.append({"date": date, "path": path, "content": content})
    return trades


def load_performance_log():
    """Load performance log from DB."""
    with VaultDB() as db:
        rows = db.get_all_trades()
    entries = []
    for r in rows:
        entries.append({
            "date": r["date"],
            "ticker": r["ticker"],
            "action": r["action"],
            "entry": str(r["entry_price"]) if r["entry_price"] else "",
            "status": r["status"] or "",
            "conviction": r["conviction"] or "",
            "exit_price": str(r["exit_price"]) if r["exit_price"] else "",
            "exit_date": r["exit_date"] or "",
            "return_pct": str(r["return_pct"]) if r["return_pct"] is not None else "",
            "report": r["report"] or "",
            "notes": r["notes"] or "",
            "target": r["target"] or "",
            "stop": str(r["stop_loss"]) if r["stop_loss"] else "",
        })
    return entries


def load_portfolio():
    """Read current portfolio holdings."""
    holdings = []
    if not os.path.exists(PORTFOLIO_PATH):
        return holdings
    with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    in_table = False
    for line in lines:
        line = line.strip()
        if "|" in line and "Ticker" in line:
            in_table = True
            continue
        if in_table and "|" in line and "---" not in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 3:
                holdings.append({
                    "ticker": parts[0],
                    "shares": parts[1],
                    "cost": parts[2].replace("$", ""),
                    "date": parts[3] if len(parts) > 3 else "",
                })
    return holdings


def _load_watchlist_log():
    """Load watchlist log from DB."""
    with VaultDB() as db:
        rows = db.get_active_watchlist()
        if rows:
            return [dict(r) for r in rows]
    return []


def _load_benchmark_log():
    """Load benchmark log from DB."""
    with VaultDB() as db:
        rows = db.get_benchmarks()
        if rows:
            return [dict(r) for r in rows]
    return []


# --- Analysis functions ---

def extract_section(content, heading):
    """Extract content under a markdown ## heading."""
    pattern = rf"^## {re.escape(heading)}.*?\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def extract_buy_recommendations(content):
    """Extract tickers with actual BUY action from portfolio table (not watchlist).

    We look for BUY in the Action column of "Your Portfolio" table,
    NOT in the "What to Buy" watchlist section.
    """
    buys = []

    # Only look in "Your Portfolio" or "Changes Since Last Report" sections
    # for actual BUY actions (not watchlist recommendations)
    portfolio_section = extract_section(content, "Your Portfolio")
    changes_section = extract_section(content, "Changes Since Last Report")

    for section in [portfolio_section, changes_section]:
        if not section:
            continue
        for match in re.finditer(r"\|\s*(\w+)\s*\|.*?\*{0,2}BUY\*{0,2}", section, re.IGNORECASE):
            ticker = match.group(1).upper()
            # Skip header/formatting artifacts
            if ticker not in ("STOCK", "PICK", "TICKER", "DAY", "RANK"):
                buys.append(ticker)

    # Also check performance log for traded BUYs
    return list(set(buys))


def extract_avoid_list(content):
    """Extract tickers/sectors from Avoid section."""
    section = extract_section(content, "What to Avoid")
    if not section:
        return []
    avoids = []
    for line in section.split("\n"):
        # Look for ticker symbols in parentheses
        tickers = re.findall(r"\(([A-Z]{2,5})\)", line)
        avoids.extend(tickers)
    return avoids


def extract_alerts(content):
    """Extract alert conditions."""
    section = extract_section(content, "Alert Conditions")
    if not section:
        return []
    alerts = []
    for line in section.split("\n"):
        line = line.strip()
        if line and re.match(r"^\d+\.", line):
            alerts.append(re.sub(r"^\d+\.\s*", "", line))
    return alerts


def extract_macro_regime(content):
    """Extract macro regime label."""
    section = extract_section(content, "Macro Regime")
    if section:
        # First sentence
        return section.split(".")[0].strip()
    return ""


def analyze_prediction_accuracy(reports, perf_log):
    """Compare report predictions to actual outcomes."""
    results = {
        "buy_calls": [],
        "avoid_calls": [],
        "alert_accuracy": [],
        "regime_changes": [],
    }

    for report in reports:
        date = report["date"]
        content = report["content"]

        # BUY recommendations
        buys = extract_buy_recommendations(content)
        for ticker in buys:
            # Find in performance log (match ticker, allow ±7 day window on date)
            log_entry = None
            for entry in perf_log:
                if entry.get("ticker", "").upper() == ticker:
                    try:
                        report_dt = datetime.strptime(date, "%Y-%m-%d")
                        entry_dt = datetime.strptime(entry.get("date", ""), "%Y-%m-%d")
                        if abs((report_dt - entry_dt).days) <= 7:
                            log_entry = entry
                            break
                    except ValueError:
                        if entry.get("date", "") == date:
                            log_entry = entry
                            break

            # Get current price for open positions
            current_price = None
            return_pct = None
            status = "NOT TRADED"

            if log_entry:
                status = log_entry.get("status", "NOT TRADED").upper()
                entry_price = float(log_entry.get("entry", "0").replace("$", ""))
                if status == "OPEN" and entry_price > 0:
                    q = fetch_quote(ticker)
                    if q and "error" not in q:
                        current_price = q["price"]
                        return_pct = round((current_price - entry_price) / entry_price * 100, 2)
                elif log_entry.get("return_pct"):
                    try:
                        return_pct = float(log_entry["return_pct"].replace("+", "").replace("%", ""))
                    except ValueError:
                        pass
            else:
                # Not traded — check what would have happened
                historical = fetch_historical_price(ticker, date)
                q = fetch_quote(ticker)
                if historical and q and "error" not in q:
                    current_price = q["price"]
                    return_pct = round((current_price - historical) / historical * 100, 2)

            results["buy_calls"].append({
                "date": date,
                "ticker": ticker,
                "status": status,
                "return_pct": return_pct,
                "current_price": current_price,
            })

        # AVOID recommendations — compare price at report date vs now
        # Deduplicate: only track first occurrence of each ticker
        avoids = extract_avoid_list(content)
        for ticker in avoids:
            # Skip if we already tracked this ticker from an earlier report
            already_tracked = any(
                c["ticker"] == ticker for c in results["avoid_calls"]
            )
            if already_tracked:
                continue

            q = fetch_quote(ticker)
            if q and "error" not in q:
                current = q["price"]
                historical = fetch_historical_price(ticker, date)
                change_pct = None
                if historical and historical > 0:
                    change_pct = round((current - historical) / historical * 100, 2)
                # Correct if price dropped. Flat (0%) = inconclusive, not wrong.
                if change_pct is not None:
                    correct = change_pct < -0.1  # Must drop at least 0.1%
                else:
                    correct = None
                results["avoid_calls"].append({
                    "date": date,
                    "ticker": ticker,
                    "price_at_report": historical,
                    "current_price": current,
                    "change_pct": change_pct,
                    "correct": correct,
                })

        # Macro regime
        regime = extract_macro_regime(content)
        if regime:
            results["regime_changes"].append({
                "date": date,
                "regime": regime,
            })

    return results


def analyze_report_quality(reports):
    """Check structural quality of reports."""
    issues = []

    required_sections = [
        "What's Happening", "Your Portfolio", "What to Buy",
        "What to Avoid", "Biggest Risks", "Gut Check", "Bottom Line",
        "Search Log", "Validation Summary",
    ]

    for report in reports:
        date = report["date"]
        content = report["content"]

        # Check for required sections
        for section in required_sections:
            # Match flexibly: "## What's Happening" or "## Your Portfolio" etc.
            # Also allow the section text to appear as a heading at any level
            section_found = (
                f"## {section}" in content
                or f"### {section}" in content
                or section.lower() in content.lower()
            )
            if not section_found:
                issues.append({
                    "date": date,
                    "type": "Missing Section",
                    "detail": f"'{section}' section not found",
                    "severity": "HIGH",
                })

        # Check for vague language
        vague_phrases = [
            "could go either way",
            "time will tell",
            "hard to say",
            "it depends",
            "we'll see",
        ]
        for phrase in vague_phrases:
            if phrase in content.lower():
                issues.append({
                    "date": date,
                    "type": "Vague Language",
                    "detail": f'Used: "{phrase}"',
                    "severity": "LOW",
                })

        # Check for data citations — only flag if no evidence of data pipeline usage
        has_data_source = any(term in content.lower() for term in [
            "data_fetcher", "verified", "search log", "yfinance",
            "rsi", "50 dma", "200 dma", "52-wk", "52-week",
        ])
        if not has_data_source:
            price_count = len(re.findall(r"\$\d+", content))
            if price_count > 5:
                issues.append({
                    "date": date,
                    "type": "Unverified Data",
                    "detail": f"{price_count} price mentions with no evidence of data pipeline",
                    "severity": "MEDIUM",
                })

        # Check for stop-loss on actual BUY recommendations (not watchlist/headers)
        # Count BUY actions in table rows: "| **BUY**" or "| BUY |"
        actual_buys = len(re.findall(r"\|\s*\*{0,2}BUY\*{0,2}\s*\|", content, re.IGNORECASE))
        # Also count new picks in "What to Buy" with entry zones (these need stops too)
        buy_section = extract_section(content, "What to Buy")
        watchlist_picks = 0
        watchlist_with_stops = 0
        if buy_section:
            # Count table rows with ticker symbols (skip cash/header rows)
            for line in buy_section.split("\n"):
                if "|" in line and "---" not in line and "Ticker" not in line and "Cash" not in line:
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if parts and re.match(r'^[A-Z]{1,5}$', parts[0]):
                        watchlist_picks += 1
                        # Check if this row has a stop defined (not TBD/—)
                        line_lower = line.lower()
                        if "tbd" not in line_lower and "—" not in line_lower.split("stop")[0] if "stop" in line_lower else True:
                            if re.search(r'\$\d+', line):
                                watchlist_with_stops += 1

        picks_without_stops = watchlist_picks - watchlist_with_stops
        if picks_without_stops > 0:
            issues.append({
                "date": date,
                "type": "Missing Stop-Loss",
                "detail": f"{picks_without_stops} watchlist pick(s) without defined stop-loss",
                "severity": "MEDIUM",
            })

        # Check word count
        word_count = len(content.split())
        if word_count > 2000:
            issues.append({
                "date": date,
                "type": "Too Long",
                "detail": f"Report is {word_count} words (target: <1500)",
                "severity": "LOW",
            })
        elif word_count < 300:
            issues.append({
                "date": date,
                "type": "Too Short",
                "detail": f"Report is only {word_count} words — may lack depth",
                "severity": "MEDIUM",
            })

    return issues


def analyze_portfolio_concentration(holdings):
    """Check portfolio for concentration risks."""
    issues = []
    if not holdings:
        return issues

    total_cost = 0
    positions = []
    for h in holdings:
        try:
            shares = float(h["shares"])
            cost = float(h["cost"])
            value = shares * cost
            positions.append({"ticker": h["ticker"], "value": value})
            total_cost += value
        except ValueError:
            continue

    if total_cost == 0:
        return issues

    for p in positions:
        pct = p["value"] / total_cost * 100
        if pct > 40:
            issues.append({
                "type": "Concentration Risk",
                "detail": f"{p['ticker']} is {pct:.1f}% of portfolio (limit: 15%)",
                "severity": "HIGH",
            })
        elif pct > 15:
            issues.append({
                "type": "Concentration Warning",
                "detail": f"{p['ticker']} is {pct:.1f}% of portfolio (limit: 15%)",
                "severity": "MEDIUM",
            })

    if len(positions) < 5:
        issues.append({
            "type": "Low Diversification",
            "detail": f"Only {len(positions)} positions — consider adding more for diversification",
            "severity": "MEDIUM",
        })

    return issues


def generate_report(reports, trades, perf_log, holdings):
    """Generate the self-improvement report."""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y-%m-%d %H:%M")

    print("Analyzing prediction accuracy...")
    predictions = analyze_prediction_accuracy(reports, perf_log)

    print("Analyzing report quality...")
    quality_issues = analyze_report_quality(reports)

    print("Analyzing portfolio concentration...")
    concentration_issues = analyze_portfolio_concentration(holdings)

    # --- Build report ---
    lines = []
    lines.append(f"# Self-Improvement Report — {timestamp}")
    lines.append(f"## System Analysis")
    lines.append("")
    lines.append(f"Reports analyzed: {len(reports)}")
    lines.append(f"Trades executed: {len(trades)}")
    lines.append(f"Performance entries: {len(perf_log)}")
    lines.append(f"Current holdings: {len(holdings)}")
    lines.append("")

    # --- Prediction Accuracy ---
    lines.append("## Prediction Accuracy")
    lines.append("")

    if predictions["buy_calls"]:
        lines.append("### BUY Calls")
        lines.append("| Date | Ticker | Status | Return |")
        lines.append("|------|--------|--------|--------|")
        wins = 0
        losses = 0
        not_traded = 0
        for call in predictions["buy_calls"]:
            ret = f"{call['return_pct']:+.1f}%" if call["return_pct"] is not None else "-"
            lines.append(f"| {call['date']} | {call['ticker']} | {call['status']} | {ret} |")
            if call["return_pct"] is not None:
                if call["return_pct"] > 0:
                    wins += 1
                else:
                    losses += 1
            if call["status"] == "NOT TRADED":
                not_traded += 1
        lines.append("")
        total = wins + losses
        if total > 0:
            lines.append(f"Win rate: {wins}/{total} ({wins/total*100:.0f}%)")
        if not_traded > 0:
            lines.append(f"Not traded: {not_traded} calls were recommended but not executed")
        lines.append("")

    if predictions["avoid_calls"]:
        lines.append("### AVOID Calls — Were We Right?")
        lines.append("| Date | Ticker | Price Then | Price Now | Change | Correct? |")
        lines.append("|------|--------|-----------|-----------|--------|----------|")
        avoid_correct = 0
        avoid_total = 0
        for call in predictions["avoid_calls"]:
            then = f"${call['price_at_report']:.2f}" if call["price_at_report"] else "-"
            now = f"${call['current_price']:.2f}"
            chg = f"{call['change_pct']:+.1f}%" if call["change_pct"] is not None else "-"
            if call["correct"] is not None:
                avoid_total += 1
                if call["correct"]:
                    avoid_correct += 1
                    verdict = "YES (dropped)"
                elif call["change_pct"] is not None and abs(call["change_pct"]) <= 0.1:
                    verdict = "FLAT (inconclusive)"
                    avoid_total -= 1  # Don't count flat as wrong
                else:
                    verdict = "NO (went up)"
            else:
                verdict = "-"
            lines.append(f"| {call['date']} | {call['ticker']} | {then} | {now} | {chg} | {verdict} |")
        if avoid_total > 0:
            lines.append(f"\nAVOID accuracy: {avoid_correct}/{avoid_total} ({avoid_correct/avoid_total*100:.0f}%)")
        lines.append("")

    # --- Watchlist Tracking ---
    watchlist_entries = _load_watchlist_log()
    if watchlist_entries:
        active_wl = [w for w in watchlist_entries if w.get("status", "").upper() == "ACTIVE"]
        if active_wl:
            lines.append("### Watchlist Picks — Would They Have Worked?")
            lines.append("| Date | Ticker | Rec. Price | Current | Change | Status |")
            lines.append("|------|--------|-----------|---------|--------|--------|")
            for w in active_wl:
                ticker = w["ticker"]
                rec_price = w.get("price_at_rec", "")
                q = fetch_quote(ticker)
                if q and "error" not in q and rec_price:
                    try:
                        rp = float(rec_price)
                        current = q["price"]
                        chg = round((current - rp) / rp * 100, 2)
                        lines.append(f"| {w['date']} | {ticker} | ${rp:.2f} | ${current:.2f} | {chg:+.1f}% | {w.get('notes', '')} |")
                    except (ValueError, TypeError):
                        lines.append(f"| {w['date']} | {ticker} | {rec_price} | — | — | {w.get('notes', '')} |")
                else:
                    lines.append(f"| {w['date']} | {ticker} | {rec_price or 'TBD'} | — | — | {w.get('notes', '')} |")
            lines.append("")

    # --- Benchmark History ---
    bench_history = _load_benchmark_log()
    if bench_history and len(bench_history) > 1:
        lines.append("### Portfolio vs VOO Over Time")
        lines.append("| Date | Portfolio | VOO | Alpha |")
        lines.append("|------|----------|-----|-------|")
        for b in bench_history[-10:]:  # last 10 entries
            lines.append(f"| {b['date']} | {b['portfolio_pct']}% | {b['voo_pct']}% | {b['alpha']}% |")
        lines.append("")

    if predictions["regime_changes"]:
        lines.append("### Macro Regime Calls")
        for r in predictions["regime_changes"]:
            lines.append(f"- **{r['date']}:** {r['regime']}")
        lines.append("")

    # --- Report Quality ---
    lines.append("## Report Quality Issues")
    lines.append("")

    if quality_issues:
        high = [i for i in quality_issues if i["severity"] == "HIGH"]
        medium = [i for i in quality_issues if i["severity"] == "MEDIUM"]
        low = [i for i in quality_issues if i["severity"] == "LOW"]

        if high:
            lines.append("### Critical Issues")
            for issue in high:
                lines.append(f"- **[{issue['date']}]** {issue['type']}: {issue['detail']}")
            lines.append("")

        if medium:
            lines.append("### Warnings")
            for issue in medium:
                lines.append(f"- **[{issue['date']}]** {issue['type']}: {issue['detail']}")
            lines.append("")

        if low:
            lines.append("### Minor")
            for issue in low:
                lines.append(f"- **[{issue['date']}]** {issue['type']}: {issue['detail']}")
            lines.append("")
    else:
        lines.append("No structural issues found.")
        lines.append("")

    # --- Portfolio Issues ---
    lines.append("## Portfolio Health")
    lines.append("")

    if concentration_issues:
        for issue in concentration_issues:
            severity_tag = "!!!" if issue["severity"] == "HIGH" else "!"
            lines.append(f"- **{severity_tag} {issue['type']}:** {issue['detail']}")
        lines.append("")
    else:
        lines.append("Portfolio concentration looks healthy.")
        lines.append("")

    # --- Patterns & Mistakes ---
    lines.append("## Identified Patterns")
    lines.append("")

    patterns = identify_patterns(predictions, quality_issues, perf_log, reports)
    for pattern in patterns:
        lines.append(f"### {pattern['name']}")
        lines.append(f"{pattern['description']}")
        lines.append(f"**Evidence:** {pattern['evidence']}")
        lines.append(f"**Fix:** {pattern['fix']}")
        lines.append("")

    # --- Improvement Recommendations ---
    lines.append("## Improvement Recommendations")
    lines.append("")

    recommendations = generate_recommendations(
        predictions, quality_issues, concentration_issues, perf_log, reports
    )
    for i, rec in enumerate(recommendations, 1):
        lines.append(f"### {i}. {rec['title']}")
        lines.append(f"**Priority:** {rec['priority']}")
        lines.append(f"**Problem:** {rec['problem']}")
        lines.append(f"**Solution:** {rec['solution']}")
        lines.append("")

    # --- Stats ---
    lines.append("## System Stats")
    lines.append("")
    lines.append(f"- Reports generated: {len(reports)}")
    lines.append(f"- Trades executed: {len(trades)}")
    lines.append(f"- Total BUY calls made: {len(predictions['buy_calls'])}")
    lines.append(f"- AVOID calls made: {len(predictions['avoid_calls'])}")
    lines.append(f"- Quality issues found: {len(quality_issues)}")
    lines.append(f"- Analysis date: {timestamp}")
    lines.append("")

    return "\n".join(lines)


def identify_patterns(predictions, quality_issues, perf_log, reports):
    """Identify behavioral patterns from the data."""
    patterns = []

    # Pattern: Not enough data
    if len(reports) < 3:
        patterns.append({
            "name": "Insufficient History",
            "description": "Too few reports to identify reliable patterns.",
            "evidence": f"Only {len(reports)} report(s) generated so far.",
            "fix": "Generate at least 4-5 weekly reports before drawing conclusions. Keep running the system consistently.",
        })

    # Pattern: Buy bias (catches gradations, not just zero sells)
    buy_count = sum(1 for e in perf_log if e.get("action", "").upper() == "BUY")
    sell_count = sum(1 for e in perf_log if e.get("action", "").upper() in ("SELL", "TRIM"))
    total_actions = buy_count + sell_count
    if total_actions > 3:
        buy_ratio = buy_count / total_actions
        if sell_count == 0:
            patterns.append({
                "name": "Buy Bias",
                "description": "The system recommends buys but never sells.",
                "evidence": f"{buy_count} BUY calls, {sell_count} SELL calls.",
                "fix": "Review stop-loss levels on every report. If a thesis breaks, recommend SELL explicitly. Don't wait for the investor to ask.",
            })
        elif buy_ratio > 0.85:
            patterns.append({
                "name": "Buy Bias",
                "description": "The system strongly favors buys over sells.",
                "evidence": f"{buy_count} BUY vs {sell_count} SELL ({buy_ratio:.0%} buy ratio).",
                "fix": "For EVERY holding, explicitly ask: is there a reason to SELL or TRIM? Evaluate before recommending new BUYs.",
            })

    # Pattern: Concentration in recommendations
    tickers = [c["ticker"] for c in predictions["buy_calls"]]
    if tickers:
        from collections import Counter
        counts = Counter(tickers)
        repeated = [(t, c) for t, c in counts.items() if c > 1]
        if repeated:
            patterns.append({
                "name": "Repetitive Recommendations",
                "description": "Same tickers recommended across multiple reports without new evidence.",
                "evidence": ", ".join(f"{t} ({c}x)" for t, c in repeated),
                "fix": "If a ticker was already recommended and bought, switch to HOLD analysis. Only recommend again with new catalyst.",
            })

    # Pattern: Missing sections in reports
    section_issues = [i for i in quality_issues if i["type"] == "Missing Section"]
    if section_issues:
        patterns.append({
            "name": "Incomplete Reports",
            "description": "Reports are missing required sections.",
            "evidence": "; ".join(f"[{i['date']}] {i['detail']}" for i in section_issues),
            "fix": "Follow the 04_report.md template strictly. Use a checklist before finalizing.",
        })

    # Pattern: High conviction but low returns
    high_conv = [e for e in perf_log if e.get("conviction") == "***"]
    if high_conv:
        returns = []
        for e in high_conv:
            try:
                r = float(e.get("return_pct", "0").replace("+", "").replace("%", ""))
                returns.append(r)
            except ValueError:
                pass
        if returns:
            avg = sum(returns) / len(returns)
            if avg < 0:
                patterns.append({
                    "name": "Overconfident Calls",
                    "description": "High conviction (***) calls are underperforming.",
                    "evidence": f"Average return on *** calls: {avg:+.1f}%",
                    "fix": "Be more selective with *** ratings. Reserve for truly exceptional setups with multiple confirming signals.",
                })

    return patterns


def generate_recommendations(predictions, quality_issues, concentration_issues, perf_log, reports):
    """Generate actionable improvement recommendations."""
    recs = []

    # Always recommend based on report count
    if len(reports) < 4:
        recs.append({
            "title": "Build More History",
            "priority": "HIGH",
            "problem": f"Only {len(reports)} report(s). Can't evaluate system accuracy yet.",
            "solution": "Run `report` weekly for at least 4 weeks. Track every call in vault.db. Then re-run `self-analyze` for meaningful insights.",
        })

    # Data quality
    data_issues = [i for i in quality_issues if i["type"] == "Unverified Data"]
    if data_issues:
        recs.append({
            "title": "Improve Data Verification",
            "priority": "HIGH",
            "problem": "Some reports contain prices without verification source.",
            "solution": "Always run data_fetcher.py first. Reference it explicitly in the report. Include Search Log before Devil's Gate.",
        })

    # Concentration
    high_conc = [i for i in concentration_issues if i["severity"] == "HIGH"]
    if high_conc:
        recs.append({
            "title": "Reduce Position Concentration",
            "priority": "HIGH",
            "problem": high_conc[0]["detail"],
            "solution": "Follow the 15% single-stock limit in 00_system.md. Use next month's capital to add new positions rather than adding to existing ones.",
        })

    # Diversification
    low_div = [i for i in concentration_issues if i["type"] == "Low Diversification"]
    if low_div:
        recs.append({
            "title": "Increase Diversification",
            "priority": "MEDIUM",
            "problem": low_div[0]["detail"],
            "solution": "Target 6-8 positions across different sectors. Use screener to find candidates in underrepresented sectors.",
        })

    # Screener integration
    recs.append({
        "title": "Use Screener Before Every Report",
        "priority": "MEDIUM",
        "problem": "BUY candidates are selected narratively, not data-driven.",
        "solution": "Run `python3 tools/screener.py --sample 50` before Phase 1. Use oversold/golden-cross signals as starting candidates, then validate with fundamental analysis.",
    })

    # Performance tracking
    open_trades = [e for e in perf_log if e.get("status", "").upper() == "OPEN"]
    if open_trades:
        oldest = min(open_trades, key=lambda x: x.get("date", ""))
        recs.append({
            "title": "Review Open Positions",
            "priority": "MEDIUM",
            "problem": f"{len(open_trades)} positions open since {oldest.get('date', '?')}. No exits recorded.",
            "solution": "Every report must evaluate each open position against its stop-loss and target. If a stop is hit, log it as CLOSED in vault.db.",
        })

    # Emotional discipline
    recs.append({
        "title": "Track Gut Check Accuracy",
        "priority": "LOW",
        "problem": "Gut Check section gives behavioral advice but we don't track if it was useful.",
        "solution": "After each report cycle, note in trades/ whether behavioral coaching prevented a mistake or was irrelevant. Over time this shows if Gut Check adds value.",
    })

    return recs


def _write_active_improvements(reports, trades, perf_log, holdings):
    """Write active improvements to vault.db — read by the pipeline during Phase 2."""
    predictions = analyze_prediction_accuracy(reports, perf_log)
    quality_issues = analyze_report_quality(reports)
    concentration_issues = analyze_portfolio_concentration(holdings)
    patterns = identify_patterns(predictions, quality_issues, perf_log, reports)
    today = datetime.now().strftime("%Y-%m-%d")

    with VaultDB() as db:
        # Clear previous active improvements from self_analysis
        db.clear_improvements('self_analysis')

        # Concentration issues
        for c in concentration_issues:
            if c["severity"] in ("HIGH", "MEDIUM"):
                db.add_improvement(
                    date=today, imp_type='self_analysis',
                    category='concentration', priority=c["severity"],
                    finding=c['detail'], source='self_analyze.py',
                )

        # Bias patterns
        for p in patterns:
            if p["name"] in ("Buy Bias", "Overconfident Calls", "Repetitive Recommendations"):
                db.add_improvement(
                    date=today, imp_type='self_analysis',
                    category='bias', priority='HIGH',
                    finding=p['description'], action=p['fix'],
                    source='self_analyze.py',
                )

        # Process gaps
        for i in quality_issues:
            if i["severity"] in ("HIGH", "MEDIUM"):
                db.add_improvement(
                    date=today, imp_type='self_analysis',
                    category='process', priority=i["severity"],
                    finding=f"{i['type']}: {i['detail']}",
                    source='self_analyze.py',
                )

        # What worked / didn't work — store as meta
        winners = [c for c in predictions["buy_calls"]
                   if c.get("return_pct") is not None and c["return_pct"] > 0]
        losers = [c for c in predictions["buy_calls"]
                  if c.get("return_pct") is not None and c["return_pct"] < 0]
        avoid_correct = sum(1 for c in predictions["avoid_calls"] if c.get("correct"))
        avoid_total = sum(1 for c in predictions["avoid_calls"] if c.get("correct") is not None)
        buy_total = sum(1 for c in predictions["buy_calls"] if c.get("return_pct") is not None)
        buy_wins = len(winners)

        performance_meta = {
            'winners': [{'ticker': w['ticker'], 'return': w['return_pct']} for w in winners[:3]],
            'losers': [{'ticker': l['ticker'], 'return': l['return_pct']} for l in losers[:3]],
            'buy_win_rate': f"{buy_wins}/{buy_total}" if buy_total else "N/A",
            'avoid_accuracy': f"{avoid_correct}/{avoid_total}" if avoid_total else "N/A",
        }
        db.add_improvement(
            date=today, imp_type='self_analysis',
            category='performance_summary', priority='LOW',
            finding=f"Win rate: {buy_wins}/{buy_total}, AVOID accuracy: {avoid_correct}/{avoid_total}",
            source='self_analyze.py', meta=performance_meta,
        )

    print("  Active improvements saved to vault.db")


# ═══════════════════════════════════════════════════════════════
# Self-Improving Patch Engine
# ═══════════════════════════════════════════════════════════════

class PatchEngine:
    """Registry-driven auto-fix engine. Patches system files based on analysis findings.

    Each rule has a detector (should we patch?) and a formatter (what to write).
    Patches are idempotent via HTML comment markers. Reversible when conditions clear.
    """

    def __init__(self, project_dir):
        self.project_dir = project_dir
        self.applied = []

    def _read_file(self, rel_path):
        fpath = os.path.join(self.project_dir, rel_path)
        if not os.path.exists(fpath):
            return None
        with open(fpath, "r", encoding="utf-8") as f:
            return f.read()

    def _write_file(self, rel_path, content):
        fpath = os.path.join(self.project_dir, rel_path)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)

    def _apply_patch(self, target_file, marker_name, patch_text, insert_before=None):
        """Insert or update a marker-bounded block. Returns True if file changed."""
        content = self._read_file(target_file)
        if content is None:
            return False

        start_marker = f"<!-- AUTO-FIX: {marker_name} -->"
        end_marker = f"<!-- END {marker_name} -->"
        block = f"\n{start_marker}\n{patch_text}\n{end_marker}\n"

        if start_marker in content:
            # Update existing block
            pat = re.compile(
                re.escape(start_marker) + r".*?" + re.escape(end_marker),
                re.DOTALL,
            )
            new_content = pat.sub(block.strip(), content)
            if new_content == content:
                return False  # No change needed
            self._write_file(target_file, new_content)
            return True
        else:
            # Insert new block
            if insert_before and insert_before in content:
                content = content.replace(insert_before, block + insert_before)
            else:
                content += block
            self._write_file(target_file, content)
            return True

    def _remove_patch(self, target_file, marker_name):
        """Remove a marker-bounded block. Returns True if file changed."""
        content = self._read_file(target_file)
        if content is None:
            return False

        start_marker = f"<!-- AUTO-FIX: {marker_name} -->"
        end_marker = f"<!-- END {marker_name} -->"

        if start_marker not in content:
            return False

        pat = re.compile(
            r"\n?" + re.escape(start_marker) + r".*?" + re.escape(end_marker) + r"\n?",
            re.DOTALL,
        )
        new_content = pat.sub("", content)
        if new_content != content:
            self._write_file(target_file, new_content)
            return True
        return False

    def _log(self, target_file, fix, reason):
        self.applied.append({"file": target_file, "fix": fix, "reason": reason})

    def run_all(self, ctx):
        """Run all patch rules against the analysis context."""
        self._fix_concentration_blockers(ctx)
        self._fix_sector_blockers(ctx)
        self._fix_stop_loss_enforcement(ctx)
        self._fix_sell_check(ctx)
        self._fix_avoid_validation(ctx)
        self._fix_data_citation(ctx)
        self._fix_conviction_calibration(ctx)
        self._fix_repetition_guard(ctx)
        self._fix_benchmark_alert(ctx)
        self._fix_section_checklist(ctx)
        self._fix_stale_references(ctx)
        self._fix_learned_rules_summary(ctx)
        return self.applied

    # ── Rule 1: Concentration blockers (Devil's Gate) ─────────

    def _fix_concentration_blockers(self, ctx):
        conc_high = [i for i in ctx["concentration"] if i["severity"] == "HIGH"]
        tickers = [i["detail"].split(" is ")[0] for i in conc_high if " is " in i["detail"]]

        if tickers:
            text = (
                "**Auto-detected concentration blockers (from self-analyze):**\n"
                "The following tickers are over the 15% single-position limit. "
                "Any BUY or BUY MORE recommendation for these MUST be REJECTED:\n"
            )
            for t in tickers:
                text += f"- {t}\n"
            if self._apply_patch("system/03_devils_gate.md", "CONCENTRATION BLOCKERS",
                                 text, "## The Eight Tests"):
                self._log("system/03_devils_gate.md",
                          f"Concentration blockers: {', '.join(tickers)}",
                          "Positions exceed 15% limit")
        else:
            if self._remove_patch("system/03_devils_gate.md", "CONCENTRATION BLOCKERS"):
                self._log("system/03_devils_gate.md",
                          "Removed concentration blockers — all positions within limits",
                          "No positions over 15%")

    # ── Rule 2: Sector blockers (Devil's Gate) ────────────────

    def _fix_sector_blockers(self, ctx):
        # Calculate sector exposure from holdings
        holdings = ctx.get("holdings", [])
        if not holdings:
            return
        sector_map = {
            # Sector ETFs
            "XLE": "Energy", "XLV": "Healthcare", "XLK": "Technology",
            "XLF": "Financials", "XLY": "Consumer Discretionary",
            "XLP": "Consumer Staples", "XLI": "Industrials", "XLB": "Materials",
            "XLRE": "Real Estate", "XLU": "Utilities", "XLC": "Communications",
            "GLD": "Commodities", "GDX": "Commodities", "SLV": "Commodities",
            # Common individual stocks by sector
            "GOOGL": "Technology", "GOOG": "Technology", "AAPL": "Technology",
            "MSFT": "Technology", "NVDA": "Technology", "META": "Technology",
            "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary",
            "JPM": "Financials", "BAC": "Financials", "GS": "Financials",
            "JNJ": "Healthcare", "UNH": "Healthcare", "PFE": "Healthcare",
            "XOM": "Energy", "CVX": "Energy", "OXY": "Energy",
            "LMT": "Industrials", "RTX": "Industrials", "NOC": "Industrials",
            "KO": "Consumer Staples", "PG": "Consumer Staples",
            "NEE": "Utilities", "DUK": "Utilities",
            "NFLX": "Communications", "DIS": "Communications",
            "CRM": "Technology", "PLTR": "Technology", "MU": "Technology",
        }
        total_cost = 0
        sector_totals = {}
        for h in holdings:
            try:
                val = float(h["shares"]) * float(h["cost"])
                total_cost += val
                sector = sector_map.get(h["ticker"], "Other")
                sector_totals[sector] = sector_totals.get(sector, 0) + val
            except (ValueError, KeyError):
                continue

        if total_cost == 0:
            return

        over_sectors = []
        for sector, val in sector_totals.items():
            pct = val / total_cost * 100
            if pct > 35:
                over_sectors.append(f"{sector} ({pct:.0f}%)")

        if over_sectors:
            text = (
                "**Auto-detected sector concentration (from self-analyze):**\n"
                "The following sectors exceed the 35% limit. No new BUYs in these sectors:\n"
            )
            for s in over_sectors:
                text += f"- {s}\n"
            if self._apply_patch("system/03_devils_gate.md", "SECTOR BLOCKERS",
                                 text, "## The Eight Tests"):
                self._log("system/03_devils_gate.md",
                          f"Sector blockers: {', '.join(over_sectors)}",
                          "Sectors exceed 35% limit")
        else:
            if self._remove_patch("system/03_devils_gate.md", "SECTOR BLOCKERS"):
                self._log("system/03_devils_gate.md",
                          "Removed sector blockers — all sectors within limits",
                          "No sectors over 35%")

    # ── Rule 3: Stop-loss enforcement (Report template) ───────

    def _fix_stop_loss_enforcement(self, ctx):
        stop_issues = [i for i in ctx["quality"] if i["type"] == "Missing Stop-Loss"]
        if stop_issues:
            n = sum(int(re.search(r"(\d+)", i["detail"]).group(1))
                    for i in stop_issues if re.search(r"(\d+)", i["detail"]))
            text = (
                f"**STOP-LOSS RULE (auto-added by self-analyze):**\n"
                f"Every BUY recommendation MUST include a specific stop-loss price. "
                f"\"10% below\" is not acceptable — use a meaningful technical level "
                f"(support, DMA, 52-week low). If you cannot define a stop, do not recommend the BUY.\n"
                f"*Evidence: {n} past picks without defined stop-loss.*\n"
            )
            if self._apply_patch("system/04_report.md", "STOP-LOSS ENFORCEMENT",
                                 text, "### 6. What to Avoid"):
                self._log("system/04_report.md",
                          "Stop-loss enforcement rule",
                          f"{n} past BUY picks without stop-loss")

    # ── Rule 4: Buy bias → SELL/TRIM check (Strategy) ────────

    def _fix_sell_check(self, ctx):
        buy_bias = [p for p in ctx["patterns"] if p["name"] == "Buy Bias"]
        if buy_bias:
            p = buy_bias[0]
            text = (
                f"**SELL/TRIM CHECK (auto-added by self-analyze):**\n"
                f"Buy bias detected — {p['evidence']}. "
                f"For EVERY holding, explicitly evaluate: is there a reason to SELL or TRIM? "
                f"If a stop-loss has been hit, the thesis has broken, or the position is over-concentrated, "
                f"recommend SELL/TRIM before any new BUYs.\n"
            )
            if self._apply_patch("system/02_strategy.md", "SELL CHECK",
                                 text, "### 3. Risk Assessment"):
                self._log("system/02_strategy.md",
                          f"SELL/TRIM check — {p['evidence']}",
                          "Buy bias pattern detected")
        else:
            if self._remove_patch("system/02_strategy.md", "SELL CHECK"):
                self._log("system/02_strategy.md",
                          "Removed SELL/TRIM check — buy bias no longer detected",
                          "Sell activity now present")

    # ── Rule 5: AVOID signal validation (Screener) ───────────

    def _fix_avoid_validation(self, ctx):
        avoid_calls = ctx["predictions"].get("avoid_calls", [])
        if not avoid_calls:
            return
        correct = [c for c in avoid_calls if c.get("correct")]
        total = [c for c in avoid_calls if c.get("correct") is not None]
        if len(total) >= 3 and len(correct) / len(total) >= 0.8:
            screener_path = os.path.join(SCRIPT_DIR, "screener.py")
            if not os.path.exists(screener_path):
                return
            with open(screener_path, "r", encoding="utf-8") as f:
                content = f.read()
            marker = "# AUTO-FIX: AVOID VALIDATION"
            if marker not in content:
                old_line = 'signals.append("Overbought")'
                if old_line in content:
                    new_line = (
                        f'signals.append("Overbought")  '
                        f'{marker} — AVOID calls validated at '
                        f'{len(correct)}/{len(total)} accuracy'
                    )
                    content = content.replace(old_line, new_line, 1)
                    with open(screener_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    self._log("tools/screener.py",
                              f"AVOID signal validated ({len(correct)}/{len(total)} correct)",
                              "AVOID accuracy is high — signal is reliable")

    # ── Rule 6: Data citation reminder (Research) ────────────

    def _fix_data_citation(self, ctx):
        data_issues = [i for i in ctx["quality"] if i["type"] == "Unverified Data"]
        if data_issues:
            text = (
                f"**DATA CITATION RULE (auto-added by self-analyze):**\n"
                f"Every price mentioned in the report must reference its source: "
                f"\"(data_fetcher.py)\" or \"(web search YYYY-MM-DD)\". "
                f"Past reports had {data_issues[0]['detail'].lower()}.\n"
            )
            if self._apply_patch("system/01_research.md", "VERIFICATION REMINDER",
                                 text, "## Rules"):
                self._log("system/01_research.md",
                          "Data citation rule",
                          "Past reports had unverified price mentions")

    # ── Rule 7: Conviction calibration (Strategy) ────────────

    def _fix_conviction_calibration(self, ctx):
        perf_log = ctx.get("perf_log", [])
        high_conv = [e for e in perf_log if e.get("conviction") == "***"]
        if len(high_conv) < 5:
            return  # Not enough data

        returns = []
        for e in high_conv:
            try:
                r = float(e.get("return_pct", "0").replace("+", "").replace("%", ""))
                returns.append(r)
            except ValueError:
                pass

        if not returns:
            return

        avg = sum(returns) / len(returns)
        if avg < 0:
            text = (
                f"**CONVICTION CALIBRATION (auto-added by self-analyze):**\n"
                f"High conviction (***) calls are underperforming: avg return {avg:+.1f}% "
                f"across {len(returns)} calls.\n"
                f"- Consider downgrading borderline *** to ** until track record improves\n"
                f"- Reserve *** for setups with 3+ confirming signals\n"
                f"- Current threshold: 5+ *** calls with negative avg return\n"
            )
            if self._apply_patch("system/02_strategy.md", "CONVICTION CALIBRATION",
                                 text, "### 5. New BUY Recommendations"):
                self._log("system/02_strategy.md",
                          f"Conviction calibration — *** avg return {avg:+.1f}%",
                          "High conviction calls underperforming")
        else:
            if self._remove_patch("system/02_strategy.md", "CONVICTION CALIBRATION"):
                self._log("system/02_strategy.md",
                          "Removed conviction calibration — *** calls now profitable",
                          f"*** avg return improved to {avg:+.1f}%")

    # ── Rule 8: Repetition guard (Strategy) ──────────────────

    def _fix_repetition_guard(self, ctx):
        repeat_patterns = [p for p in ctx["patterns"] if p["name"] == "Repetitive Recommendations"]
        if repeat_patterns:
            p = repeat_patterns[0]
            text = (
                f"**REPETITION GUARD (auto-added by self-analyze):**\n"
                f"Detected repeated recommendations without new evidence: {p['evidence']}.\n"
                f"If a ticker was already recommended AND the investor bought it, switch to HOLD analysis. "
                f"Only recommend again with a NEW catalyst.\n"
            )
            if self._apply_patch("system/02_strategy.md", "REPETITION GUARD",
                                 text, "### 5. New BUY Recommendations"):
                self._log("system/02_strategy.md",
                          f"Repetition guard — {p['evidence']}",
                          "Same tickers recommended across multiple reports")
        else:
            if self._remove_patch("system/02_strategy.md", "REPETITION GUARD"):
                self._log("system/02_strategy.md",
                          "Removed repetition guard — no repeated picks",
                          "Recommendation diversity restored")

    # ── Rule 9: Benchmark alert (Strategy) ───────────────────

    def _fix_benchmark_alert(self, ctx):
        perf_log = ctx.get("perf_log", [])
        reports = ctx.get("reports", [])

        # Check benchmark data from DB
        try:
            with VaultDB() as db:
                benchmarks = db.get_benchmarks(limit=5)
            if not benchmarks:
                return

            trailing = sum(1 for b in benchmarks if float(b["alpha"]) < 0)
            if trailing >= 3:
                latest = benchmarks[0]
                text = (
                    f"**BENCHMARK ALERT (auto-added by self-analyze):**\n"
                    f"Portfolio is trailing VOO for {trailing} consecutive reports "
                    f"(latest alpha: {latest['alpha']}%).\n"
                    f"- Consider whether active picks are adding value vs simple VOO\n"
                    f"- If trailing persists 5+ reports, shift to index-heavy approach\n"
                    f"- This is not a failure — it's data for honest assessment\n"
                )
                if self._apply_patch("system/02_strategy.md", "BENCHMARK ALERT",
                                     text, "### 4. Consensus Challenges"):
                    self._log("system/02_strategy.md",
                              f"Benchmark alert — trailing VOO for {trailing} reports",
                              "Portfolio underperforming index")
            else:
                if self._remove_patch("system/02_strategy.md", "BENCHMARK ALERT"):
                    self._log("system/02_strategy.md",
                              "Removed benchmark alert — outperforming again",
                              "Alpha is positive")
        except Exception:
            pass

    # ── Rule 10: Section checklist (Report template) ─────────

    def _fix_section_checklist(self, ctx):
        section_issues = [i for i in ctx["quality"] if i["type"] == "Missing Section"]
        # Only fire if 2+ reports have missing sections
        reports_with_issues = set(i["date"] for i in section_issues)
        if len(reports_with_issues) >= 2:
            missing = set(i["detail"] for i in section_issues)
            text = (
                f"**SECTION CHECKLIST (auto-added by self-analyze):**\n"
                f"Multiple reports have missing sections. Before finalizing, verify ALL sections exist:\n"
            )
            for section in ["What's Happening", "Your Portfolio", "What to Buy",
                           "What to Avoid", "Biggest Risks", "Gut Check", "Bottom Line"]:
                check = "MISSING" if any(section in m for m in missing) else "OK"
                text += f"- [{check}] {section}\n"
            text += f"*Evidence: {len(reports_with_issues)} reports with missing sections.*\n"

            if self._apply_patch("system/04_report.md", "SECTION CHECKLIST",
                                 text, "## Devil's Gate Integration"):
                self._log("system/04_report.md",
                          f"Section checklist — {len(reports_with_issues)} reports with gaps",
                          "Reports missing required sections")
        else:
            if self._remove_patch("system/04_report.md", "SECTION CHECKLIST"):
                self._log("system/04_report.md",
                          "Removed section checklist — reports are now complete",
                          "All required sections present")

    # ── Rule 11: Stale file references (all system docs) ─────

    def _fix_stale_references(self, ctx):
        stale_refs = {
            "performance_log.csv": "vault.db",
            "watchlist_log.csv": "vault.db",
            "benchmark_log.csv": "vault.db",
            "screener_output.csv": "vault.db",
            "thesis_log.json": "vault.db",
            "active_improvements.md": "vault.db",
        }
        system_dir = os.path.join(self.project_dir, "system")
        for fname in os.listdir(system_dir):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(system_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            changed = False
            for old_ref, new_ref in stale_refs.items():
                if old_ref in content:
                    content = content.replace(old_ref, new_ref)
                    changed = True
                    self._log(f"system/{fname}",
                              f"Stale ref: '{old_ref}' → '{new_ref}'",
                              f"{old_ref} no longer exists")
            if changed:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(content)

    # ── Rule 12: Learned rules summary (CLAUDE.md) ───────────

    def _fix_learned_rules_summary(self, ctx):
        """Update CLAUDE.md with a summary of all active auto-learned rules."""
        today = datetime.now().strftime("%Y-%m-%d")

        # Collect all active AUTO-FIX markers across system files
        active_rules = []
        system_dir = os.path.join(self.project_dir, "system")
        for fname in sorted(os.listdir(system_dir)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(system_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            for match in re.finditer(r'<!-- AUTO-FIX: (.+?) -->', content):
                rule_name = match.group(1)
                # Extract first line of content after marker
                start = match.end()
                rest = content[start:start + 200].strip()
                first_line = rest.split("\n")[0].strip().strip("*").strip()
                if first_line:
                    active_rules.append(f"- **{rule_name}** ({fname}): {first_line}")

        # Also check for PRO-INSIGHT markers
        for fname in sorted(os.listdir(system_dir)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(system_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            for match in re.finditer(r'<!-- PRO-INSIGHT: (.+?) -->', content):
                rule_name = match.group(1)
                active_rules.append(f"- **{rule_name}** ({fname}): learned from pro analysis")

        if not active_rules:
            return

        text = (
            f"## Auto-Learned Rules (updated {today} by self-analyze)\n"
            f"The system has learned these rules from analyzing reports, trades, and pro data.\n"
            f"They are embedded in system files as AUTO-FIX and PRO-INSIGHT patches.\n\n"
        )
        text += "\n".join(active_rules) + "\n"

        if self._apply_patch("CLAUDE.md", "LEARNED RULES", text, "## Don't"):
            self._log("CLAUDE.md",
                      f"Updated learned rules summary ({len(active_rules)} active rules)",
                      "Keeps CLAUDE.md in sync with auto-patched system files")


def main():
    print("=" * 50)
    print("  VAULT RESEARCH DESK — SELF-ANALYSIS")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    print("\nLoading data...")
    reports = load_reports()
    trades = load_trades()
    perf_log = load_performance_log()
    holdings = load_portfolio()

    print(f"  Reports: {len(reports)}")
    print(f"  Trades: {len(trades)}")
    print(f"  Performance entries: {len(perf_log)}")
    print(f"  Holdings: {len(holdings)}")

    print("\nRunning analysis...")
    now = datetime.now()

    # Build analysis context ONCE (avoid redundant recomputation)
    print("  Building analysis context...")
    predictions = analyze_prediction_accuracy(reports, perf_log)
    quality_issues = analyze_report_quality(reports)
    concentration_issues = analyze_portfolio_concentration(holdings)
    patterns = identify_patterns(predictions, quality_issues, perf_log, reports)
    recommendations = generate_recommendations(
        predictions, quality_issues, concentration_issues, perf_log, reports
    )

    ctx = {
        "reports": reports,
        "trades": trades,
        "perf_log": perf_log,
        "holdings": holdings,
        "predictions": predictions,
        "quality": quality_issues,
        "concentration": concentration_issues,
        "patterns": patterns,
        "recommendations": recommendations,
    }

    report_content = generate_report(reports, trades, perf_log, holdings)

    # Print report to console
    print("\n" + report_content)

    # Update active improvements in DB
    print("\nUpdating active improvements in DB...")
    _write_active_improvements(reports, trades, perf_log, holdings)

    # Run the self-improving patch engine
    print("\n" + "=" * 50)
    print("  PATCH ENGINE — Auto-improving system files")
    print("=" * 50)
    engine = PatchEngine(PROJECT_DIR)
    fixes = engine.run_all(ctx)
    if fixes:
        for fix in fixes:
            print(f"  PATCHED: {fix['file']} — {fix['fix']}")
        # Store fixes in DB
        with VaultDB() as db:
            for fix in fixes:
                db.add_improvement(
                    date=now.strftime("%Y-%m-%d"),
                    imp_type='self_analysis',
                    category='auto_fix',
                    priority='HIGH',
                    finding=fix['fix'],
                    action=fix['reason'],
                    target_file=fix['file'],
                    status='applied',
                    source='self_analyze.py (PatchEngine)',
                )
    else:
        print("  No patches needed — system is up to date.")

    # Print summary
    print("\n" + "=" * 50)
    print("  SUMMARY")
    print("=" * 50)

    quality_issues = analyze_report_quality(reports)
    high_issues = [i for i in quality_issues if i["severity"] == "HIGH"]
    print(f"\n  Reports analyzed: {len(reports)}")
    print(f"  Critical issues: {len(high_issues)}")
    print(f"  Total issues: {len(quality_issues)}")

    predictions = analyze_prediction_accuracy(reports, perf_log)
    patterns = identify_patterns(predictions, quality_issues, perf_log, reports)
    print(f"  Patterns found: {len(patterns)}")
    for p in patterns:
        print(f"    - {p['name']}")

    print(f"\n  All data saved to vault.db")
    print("=" * 50)

    # Save metadata to DB
    try:
        with VaultDB() as db:
            for call in predictions.get("avoid_calls", []):
                db.add_avoid(
                    date=call.get("date", ""),
                    ticker=call.get("ticker", ""),
                    price_at_call=call.get("price_at_report"),
                    report=None, reason=None,
                )
            db.add_report(
                filename=f"self_improvement_{now.strftime('%Y-%m-%d_%H%M')}",
                date=now.strftime("%Y-%m-%d"),
                report_type="self-analysis",
                alerts_triggered=len(high_issues),
                positions_count=len(holdings),
                path="vault.db:improvements",
            )
            print("  DB: saved avoid calls and report metadata.")
    except Exception as e:
        print(f"  DB: write skipped ({e})")


if __name__ == "__main__":
    main()
