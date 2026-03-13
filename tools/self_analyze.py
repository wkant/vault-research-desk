#!/usr/bin/env python3
"""
Vault Research Desk — Self-Analysis Engine
Analyzes all past reports, trades, and performance data to identify
patterns, mistakes, and improvement opportunities.

Usage:
    python3 tools/self_analyze.py

Output:
    improvements/self_improvement_YYYY-MM-DD.md
    improvements/self_improvement_YYYY-MM-DD.html
"""

import sys
import os
import csv
import re
import glob
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.join(SCRIPT_DIR, "..")
REPORTS_DIR = os.path.join(PROJECT_DIR, "reports")
TRADES_DIR = os.path.join(PROJECT_DIR, "trades")
IMPROVEMENTS_DIR = os.path.join(PROJECT_DIR, "improvements")
PERF_LOG = os.path.join(SCRIPT_DIR, "performance_log.csv")
PORTFOLIO_PATH = os.path.join(PROJECT_DIR, "portfolio.md")

sys.path.insert(0, SCRIPT_DIR)

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
    """Load performance_log.csv."""
    entries = []
    if not os.path.exists(PERF_LOG):
        return entries
    with open(PERF_LOG, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append(row)
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


# --- Analysis functions ---

def extract_section(content, heading):
    """Extract content under a markdown ## heading."""
    pattern = rf"^## {re.escape(heading)}.*?\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def extract_buy_recommendations(content):
    """Extract tickers recommended as BUY from a report."""
    buys = []
    # Look for BUY in table cells
    for match in re.finditer(r"\|\s*(\w+)\s*\|\s*BUY", content, re.IGNORECASE):
        buys.append(match.group(1).upper())
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
        avoids = extract_avoid_list(content)
        for ticker in avoids:
            q = fetch_quote(ticker)
            if q and "error" not in q:
                current = q["price"]
                historical = fetch_historical_price(ticker, date)
                change_pct = None
                if historical and historical > 0:
                    change_pct = round((current - historical) / historical * 100, 2)
                results["avoid_calls"].append({
                    "date": date,
                    "ticker": ticker,
                    "price_at_report": historical,
                    "current_price": current,
                    "change_pct": change_pct,
                    "correct": change_pct < 0 if change_pct is not None else None,
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
        "Market Snapshot", "Macro Regime", "Active Calls",
        "Biggest Risks", "Gut Check",
    ]

    for report in reports:
        date = report["date"]
        content = report["content"]

        # Check for required sections
        for section in required_sections:
            if f"## {section}" not in content and section.lower() not in content.lower():
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

        # Check for data citations
        if "data_fetcher" not in content.lower() and "verified" not in content.lower():
            # Check if prices look fabricated (no source mention)
            price_count = len(re.findall(r"\$\d+", content))
            if price_count > 5:
                issues.append({
                    "date": date,
                    "type": "Unverified Data",
                    "detail": f"{price_count} price mentions without verification reference",
                    "severity": "MEDIUM",
                })

        # Check for stop-loss on every BUY
        buy_count = len(re.findall(r"BUY", content, re.IGNORECASE))
        stop_count = len(re.findall(r"stop.?loss|stop", content, re.IGNORECASE))
        if buy_count > 0 and stop_count < buy_count:
            issues.append({
                "date": date,
                "type": "Missing Stop-Loss",
                "detail": f"{buy_count} BUY calls but only {stop_count} stop mentions",
                "severity": "HIGH",
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
                else:
                    verdict = "NO (went up)"
            else:
                verdict = "-"
            lines.append(f"| {call['date']} | {call['ticker']} | {then} | {now} | {chg} | {verdict} |")
        if avoid_total > 0:
            lines.append(f"\nAVOID accuracy: {avoid_correct}/{avoid_total} ({avoid_correct/avoid_total*100:.0f}%)")
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

    # Pattern: All BUYs, no SELLs
    buy_count = sum(1 for e in perf_log if e.get("action", "").upper() == "BUY")
    sell_count = sum(1 for e in perf_log if e.get("action", "").upper() in ("SELL", "TRIM"))
    if buy_count > 3 and sell_count == 0:
        patterns.append({
            "name": "Buy Bias",
            "description": "The system recommends buys but never sells.",
            "evidence": f"{buy_count} BUY calls, {sell_count} SELL calls.",
            "fix": "Review stop-loss levels on every report. If a thesis breaks, recommend SELL explicitly. Don't wait for the investor to ask.",
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
            "solution": "Run `report` weekly for at least 4 weeks. Track every call in performance_log.csv. Then re-run `self-analyze` for meaningful insights.",
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
            "solution": "Every report must evaluate each open position against its stop-loss and target. If a stop is hit, log it as CLOSED in performance_log.csv.",
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
    """Generate active_improvements.md — read by the pipeline during Phase 2."""
    predictions = analyze_prediction_accuracy(reports, perf_log)
    quality_issues = analyze_report_quality(reports)
    concentration_issues = analyze_portfolio_concentration(holdings)
    patterns = identify_patterns(predictions, quality_issues, perf_log, reports)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = []
    lines.append("# Active Improvements")
    lines.append(f"Auto-generated by `self-analyze` on {timestamp}. Read by Phase 2 (Strategy) to avoid repeating mistakes.")
    lines.append("")
    lines.append("## Current Issues")
    lines.append("")

    # Concentration
    conc = [i for i in concentration_issues if i["severity"] in ("HIGH", "MEDIUM")]
    if conc:
        lines.append("### Concentration")
        for c in conc:
            lines.append(f"- {c['detail']}")
        lines.append("")

    # Bias
    bias_patterns = [p for p in patterns if p["name"] in ("Buy Bias", "Overconfident Calls", "Repetitive Recommendations")]
    if bias_patterns:
        lines.append("### Bias Corrections")
        for p in bias_patterns:
            lines.append(f"- **{p['name']}:** {p['description']} Fix: {p['fix']}")
        lines.append("")

    # Process gaps
    process_issues = [i for i in quality_issues if i["severity"] in ("HIGH", "MEDIUM")]
    if process_issues:
        lines.append("### Process Gaps")
        for i in process_issues:
            lines.append(f"- {i['type']}: {i['detail']}")
        lines.append("")

    # What worked
    lines.append("### What Worked")
    if predictions["avoid_calls"]:
        correct = sum(1 for c in predictions["avoid_calls"] if c.get("correct"))
        total = sum(1 for c in predictions["avoid_calls"] if c.get("correct") is not None)
        if total > 0:
            lines.append(f"- AVOID calls: {correct}/{total} correct ({correct/total*100:.0f}%)")

    winners = [c for c in predictions["buy_calls"] if c.get("return_pct") is not None and c["return_pct"] > 0]
    for w in sorted(winners, key=lambda x: x["return_pct"], reverse=True)[:3]:
        lines.append(f"- {w['ticker']}: {w['return_pct']:+.1f}%")
    if not winners and not predictions["avoid_calls"]:
        lines.append("- Not enough data yet")
    lines.append("")

    # What didn't work
    lines.append("### What Didn't Work")
    losers = [c for c in predictions["buy_calls"] if c.get("return_pct") is not None and c["return_pct"] < 0]
    for l in sorted(losers, key=lambda x: x["return_pct"])[:3]:
        lines.append(f"- {l['ticker']}: {l['return_pct']:+.1f}%")

    buy_total = sum(1 for c in predictions["buy_calls"] if c.get("return_pct") is not None)
    buy_wins = sum(1 for c in predictions["buy_calls"] if c.get("return_pct") is not None and c["return_pct"] > 0)
    if buy_total > 0:
        lines.append(f"- Win rate: {buy_wins}/{buy_total} ({buy_wins/buy_total*100:.0f}%)")
    if not losers:
        lines.append("- No losing positions yet")
    lines.append("")

    # Write
    path = os.path.join(IMPROVEMENTS_DIR, "active_improvements.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Active improvements: {path}")


# --- Auto-Fix Engine ---

def apply_fixes(reports, trades, perf_log, holdings):
    """Detect fixable issues and patch system files. Returns list of applied fixes."""
    predictions = analyze_prediction_accuracy(reports, perf_log)
    quality_issues = analyze_report_quality(reports)
    concentration_issues = analyze_portfolio_concentration(holdings)
    patterns = identify_patterns(predictions, quality_issues, perf_log, reports)

    applied = []

    # --- Fix 1: Add concentration blockers to Devil's Gate ---
    conc_high = [i for i in concentration_issues if i["severity"] == "HIGH"]
    if conc_high:
        blocked_tickers = [i["detail"].split(" is ")[0] for i in conc_high if " is " in i["detail"]]
        if blocked_tickers:
            dg_path = os.path.join(PROJECT_DIR, "system", "03_devils_gate.md")
            if os.path.exists(dg_path):
                with open(dg_path, "r", encoding="utf-8") as f:
                    dg_content = f.read()

                # Add/update concentration block list
                block_marker = "<!-- AUTO-FIX: CONCENTRATION BLOCKERS -->"
                block_end = "<!-- END CONCENTRATION BLOCKERS -->"
                block_text = (
                    f"\n{block_marker}\n"
                    f"**Auto-detected concentration blockers (from self-analyze):**\n"
                    f"The following tickers are over the 15% single-position limit. "
                    f"Any BUY or BUY MORE recommendation for these MUST be REJECTED:\n"
                )
                for ticker in blocked_tickers:
                    block_text += f"- {ticker}\n"
                block_text += f"\n{block_end}\n"

                if block_marker in dg_content:
                    # Replace existing block
                    pattern = re.compile(
                        re.escape(block_marker) + r".*?" + re.escape(block_end),
                        re.DOTALL,
                    )
                    dg_content = pattern.sub(block_text.strip(), dg_content)
                else:
                    # Insert before "## The Eight Tests"
                    insert_point = "## The Eight Tests"
                    if insert_point in dg_content:
                        dg_content = dg_content.replace(
                            insert_point,
                            block_text + insert_point,
                        )

                with open(dg_path, "w", encoding="utf-8") as f:
                    f.write(dg_content)
                applied.append({
                    "file": "system/03_devils_gate.md",
                    "fix": f"Added concentration blockers: {', '.join(blocked_tickers)}",
                    "reason": "These positions exceed 15% limit — Devil's Gate will auto-reject BUY MORE calls",
                })

    # --- Fix 2: Add stop-loss enforcement to report template ---
    stop_issues = [i for i in quality_issues if i["type"] == "Missing Stop-Loss"]
    if stop_issues:
        report_path = os.path.join(PROJECT_DIR, "system", "04_report.md")
        if os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                report_content = f.read()

            enforce_marker = "<!-- AUTO-FIX: STOP-LOSS ENFORCEMENT -->"
            if enforce_marker not in report_content:
                enforcement = (
                    f"\n{enforce_marker}\n"
                    f"**STOP-LOSS RULE (auto-added by self-analyze):**\n"
                    f"Every BUY recommendation MUST include a specific stop-loss price. "
                    f"\"10% below\" is not acceptable — use a meaningful technical level "
                    f"(support, DMA, 52-week low). If you cannot define a stop, do not recommend the BUY.\n\n"
                )
                # Insert before "### 6. What to Avoid"
                insert_point = "### 6. What to Avoid"
                if insert_point in report_content:
                    report_content = report_content.replace(
                        insert_point,
                        enforcement + insert_point,
                    )
                else:
                    report_content += "\n" + enforcement

                with open(report_path, "w", encoding="utf-8") as f:
                    f.write(report_content)
                applied.append({
                    "file": "system/04_report.md",
                    "fix": "Added mandatory stop-loss enforcement rule",
                    "reason": "Past reports had BUY calls without stop-losses",
                })

    # --- Fix 3: Add SELL/TRIM check to strategy ---
    buy_bias = [p for p in patterns if p["name"] == "Buy Bias"]
    if buy_bias:
        strat_path = os.path.join(PROJECT_DIR, "system", "02_strategy.md")
        if os.path.exists(strat_path):
            with open(strat_path, "r", encoding="utf-8") as f:
                strat_content = f.read()

            bias_marker = "<!-- AUTO-FIX: SELL CHECK -->"
            if bias_marker not in strat_content:
                sell_check = (
                    f"\n{bias_marker}\n"
                    f"**SELL/TRIM CHECK (auto-added by self-analyze):**\n"
                    f"Buy bias detected — system recommends buys but rarely sells. "
                    f"For EVERY holding, explicitly evaluate: is there a reason to SELL or TRIM? "
                    f"If a stop-loss has been hit, the thesis has broken, or the position is over-concentrated, "
                    f"recommend SELL/TRIM before any new BUYs.\n\n"
                )
                # Insert before "### 3. Risk Assessment"
                insert_point = "### 3. Risk Assessment"
                if insert_point in strat_content:
                    strat_content = strat_content.replace(
                        insert_point,
                        sell_check + insert_point,
                    )
                else:
                    strat_content += "\n" + sell_check

                with open(strat_path, "w", encoding="utf-8") as f:
                    f.write(strat_content)
                applied.append({
                    "file": "system/02_strategy.md",
                    "fix": "Added mandatory SELL/TRIM evaluation for every holding",
                    "reason": "Buy bias pattern detected — 4 buys, 0 sells",
                })

    # --- Fix 4: Update screener scoring based on AVOID accuracy ---
    if predictions["avoid_calls"]:
        correct_avoids = [c for c in predictions["avoid_calls"] if c.get("correct")]
        total_avoids = [c for c in predictions["avoid_calls"] if c.get("correct") is not None]
        if len(total_avoids) >= 3 and len(correct_avoids) / len(total_avoids) >= 0.8:
            # AVOID logic is working well — add note to screener
            screener_path = os.path.join(SCRIPT_DIR, "screener.py")
            if os.path.exists(screener_path):
                with open(screener_path, "r", encoding="utf-8") as f:
                    sc_content = f.read()

                avoid_marker = "# AUTO-FIX: AVOID VALIDATION"
                if avoid_marker not in sc_content:
                    # Find the overbought scoring section and boost it
                    old_line = "signals.append(\"Overbought\")"
                    if old_line in sc_content:
                        new_line = (
                            f'signals.append("Overbought")  '
                            f'{avoid_marker} — AVOID calls validated at '
                            f'{len(correct_avoids)}/{len(total_avoids)} accuracy'
                        )
                        sc_content = sc_content.replace(old_line, new_line, 1)
                        with open(screener_path, "w", encoding="utf-8") as f:
                            f.write(sc_content)
                        applied.append({
                            "file": "tools/screener.py",
                            "fix": f"Validated overbought/AVOID signal ({len(correct_avoids)}/{len(total_avoids)} correct)",
                            "reason": "AVOID accuracy is high — this signal is reliable",
                        })

    # --- Fix 5: Add data verification reminder to research phase ---
    data_issues = [i for i in quality_issues if i["type"] == "Unverified Data"]
    if data_issues:
        research_path = os.path.join(PROJECT_DIR, "system", "01_research.md")
        if os.path.exists(research_path):
            with open(research_path, "r", encoding="utf-8") as f:
                research_content = f.read()

            verify_marker = "<!-- AUTO-FIX: VERIFICATION REMINDER -->"
            if verify_marker not in research_content:
                reminder = (
                    f"\n{verify_marker}\n"
                    f"**DATA CITATION RULE (auto-added by self-analyze):**\n"
                    f"Every price mentioned in the report must reference its source: "
                    f"\"(data_fetcher.py)\" or \"(web search YYYY-MM-DD)\". "
                    f"Past reports had {data_issues[0]['detail'].lower()}.\n\n"
                )
                insert_point = "## Rules"
                if insert_point in research_content:
                    research_content = research_content.replace(
                        insert_point,
                        reminder + insert_point,
                    )
                else:
                    research_content += "\n" + reminder

                with open(research_path, "w", encoding="utf-8") as f:
                    f.write(research_content)
                applied.append({
                    "file": "system/01_research.md",
                    "fix": "Added mandatory data citation rule",
                    "reason": "Past reports had unverified price mentions",
                })

    return applied


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
    report_content = generate_report(reports, trades, perf_log, holdings)

    # Save markdown
    now = datetime.now()
    file_stamp = now.strftime("%Y-%m-%d_%H%M")
    md_path = os.path.join(IMPROVEMENTS_DIR, f"self_improvement_{file_stamp}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    print(f"\nReport saved: {md_path}")

    # Generate HTML
    try:
        from html_report import save_html_report
        html_path = md_path.rsplit(".", 1)[0] + ".html"
        save_html_report(report_content, html_path)
    except ImportError:
        print("WARNING: Could not generate HTML (html_report.py not found)")

    # Generate active_improvements.md — feeds back into the pipeline
    print("Updating active improvements...")
    _write_active_improvements(reports, trades, perf_log, holdings)

    # Apply auto-fixes to system files
    print("\nApplying auto-fixes...")
    fixes = apply_fixes(reports, trades, perf_log, holdings)
    if fixes:
        for fix in fixes:
            print(f"  FIXED: {fix['file']} — {fix['fix']}")

        # Append fixes to the improvement report
        fix_section = "\n\n## Auto-Applied Fixes\n\n"
        fix_section += "The following changes were automatically applied to system files:\n\n"
        for fix in fixes:
            fix_section += f"### {fix['file']}\n"
            fix_section += f"**Change:** {fix['fix']}\n"
            fix_section += f"**Reason:** {fix['reason']}\n\n"

        with open(md_path, "a", encoding="utf-8") as f:
            f.write(fix_section)

        # Regenerate HTML with fixes included
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                updated_content = f.read()
            from html_report import save_html_report
            html_path = md_path.rsplit(".", 1)[0] + ".html"
            save_html_report(updated_content, html_path)
        except Exception:
            pass
    else:
        print("  No auto-fixes needed.")

    # Print summary to console
    print("\n" + "=" * 50)
    print("  SUMMARY")
    print("=" * 50)

    quality_issues = analyze_report_quality(reports)
    high_issues = [i for i in quality_issues if i["severity"] == "HIGH"]
    print(f"\n  Reports analyzed: {len(reports)}")
    print(f"  Critical issues: {len(high_issues)}")
    print(f"  Total issues: {len(quality_issues)}")

    patterns = identify_patterns(
        analyze_prediction_accuracy(reports, perf_log),
        quality_issues,
        perf_log,
        reports,
    )
    print(f"  Patterns found: {len(patterns)}")
    for p in patterns:
        print(f"    - {p['name']}")

    print(f"\n  Full report: {md_path}")
    print("=" * 50)


if __name__ == "__main__":
    main()
