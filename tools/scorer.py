#!/usr/bin/env python3
"""
Performance scoring script for the Vault Research Desk.
Reads trades from vault.db and produces a scorecard with live P&L,
conviction breakdown, holding periods, and benchmark comparison vs VOO.
"""

import os
import sys
from datetime import datetime, date

try:
    import yfinance as yf
except ImportError:
    print("Error: yfinance is required. Install with: pip install yfinance")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from db import VaultDB


def parse_date(date_str):
    """Parse a YYYY-MM-DD string into a date object."""
    if not date_str or not date_str.strip():
        return None
    return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()


def fetch_current_price(ticker):
    """Fetch the most recent closing price for a ticker via yfinance.
    Checks DB cache first (15 min freshness) to avoid redundant API calls."""
    # Check DB cache first
    try:
        with VaultDB() as db:
            cached = db.get_cached_quote(ticker, max_age_minutes=15)
            if cached and cached.get('price'):
                return cached['price']
    except Exception as e:
        print(f"  Warning: DB cache read failed for {ticker}: {e}", file=sys.stderr)

    # Fall back to yfinance
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="5d")
        if hist.empty:
            return None
        price = float(hist["Close"].iloc[-1])

        # Cache the fetched price in DB for other tools
        if price is not None:
            try:
                with VaultDB() as db:
                    db.cache_quote(ticker, {'price': price})
            except Exception as e:
                print(f"  Warning: could not cache price for {ticker}: {e}", file=sys.stderr)

        return price
    except Exception:
        return None


def fetch_price_on_date(ticker, target_date):
    """Fetch closing price for a ticker on or near a specific date."""
    try:
        tk = yf.Ticker(ticker)
        start = target_date
        # Fetch a window around the target date to handle weekends/holidays
        from datetime import timedelta
        end = target_date + timedelta(days=5)
        hist = tk.history(start=start.isoformat(), end=end.isoformat())
        if hist.empty:
            return None
        return float(hist["Close"].iloc[0])
    except Exception:
        return None


def compute_trade_metrics(trades):
    """Compute return_pct and current prices for each trade."""
    results = []
    for t in trades:
        entry_price = float(t["entry"]) if t.get("entry") else None
        status = (t.get("status") or "").strip().upper()
        ticker = t["ticker"].strip()
        entry_date = parse_date(t.get("date"))

        rec = {
            "ticker": ticker,
            "action": (t.get("action") or "").strip(),
            "entry": entry_price,
            "conviction": (t.get("conviction") or "").strip(),
            "status": status,
            "entry_date": entry_date,
            "exit_date": parse_date(t.get("exit_date")),
            "notes": (t.get("notes") or "").strip(),
        }

        if status == "CLOSED":
            # Use CSV values for closed trades
            exit_price_str = (t.get("exit_price") or "").strip()
            return_pct_str = (t.get("return_pct") or "").strip()

            rec["exit_price"] = float(exit_price_str) if exit_price_str else None
            rec["return_pct"] = parse_return_pct(return_pct_str)
            rec["current_price"] = rec["exit_price"]
        else:
            # OPEN trade: fetch live price
            current = fetch_current_price(ticker)
            rec["current_price"] = current
            if current is not None and entry_price:
                rec["return_pct"] = ((current - entry_price) / entry_price) * 100
            else:
                # Fall back to CSV return_pct if live fetch fails
                return_pct_str = (t.get("return_pct") or "").strip()
                rec["return_pct"] = parse_return_pct(return_pct_str)
            rec["exit_price"] = None

        results.append(rec)
    return results


def parse_return_pct(s):
    """Parse a return percentage string like '+1.8' or '-0.2' into a float."""
    if not s:
        return None
    s = s.strip().replace("%", "")
    try:
        return float(s)
    except ValueError:
        return None


def compute_benchmark(trades):
    """For each trade, compute VOO return over the same holding period."""
    voo_returns = []
    for t in trades:
        entry_date = t.get("entry_date")
        if not entry_date:
            continue

        end_date = t.get("exit_date") if t["status"] == "CLOSED" else date.today()

        voo_entry = fetch_price_on_date("VOO", entry_date)
        if end_date == date.today():
            voo_exit = fetch_current_price("VOO")
        else:
            voo_exit = fetch_price_on_date("VOO", end_date)

        if voo_entry and voo_exit:
            voo_ret = ((voo_exit - voo_entry) / voo_entry) * 100
            voo_returns.append(voo_ret)
        else:
            voo_returns.append(None)

    return voo_returns


def format_pct(val):
    """Format a percentage value with sign."""
    if val is None:
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}%"


def print_scorecard(trades, voo_returns):
    """Print the formatted scorecard."""
    if not trades:
        print("\n══════ PERFORMANCE SCORECARD ══════")
        print("  No trades found in vault.db")
        print("══════════════════════════════════\n")
        return

    # --- Period ---
    dates = [t["entry_date"] for t in trades if t["entry_date"]]
    exit_dates = [t["exit_date"] for t in trades if t["exit_date"]]
    all_dates = dates + exit_dates
    period_start = min(all_dates) if all_dates else "N/A"
    period_end = max(all_dates) if all_dates else date.today()
    if not exit_dates:
        period_end = date.today()

    # --- Overview ---
    total = len(trades)
    open_count = sum(1 for t in trades if t["status"] == "OPEN")
    closed_count = sum(1 for t in trades if t["status"] == "CLOSED")

    # Win rate: only on closed trades with known return
    closed_with_return = [t for t in trades if t["status"] == "CLOSED" and t["return_pct"] is not None]
    if closed_with_return:
        wins = sum(1 for t in closed_with_return if t["return_pct"] > 0)
        win_rate = f"{(wins / len(closed_with_return)) * 100:.0f}%"
    else:
        win_rate = "N/A"

    # --- Returns (including unrealized) ---
    returns = [t["return_pct"] for t in trades if t["return_pct"] is not None]
    avg_return = sum(returns) / len(returns) if returns else None

    best_trade = max(trades, key=lambda t: t["return_pct"] if t["return_pct"] is not None else float("-inf"))
    worst_trade = min(trades, key=lambda t: t["return_pct"] if t["return_pct"] is not None else float("inf"))

    # --- By conviction ---
    conviction_buckets = {}
    for t in trades:
        c = t["conviction"]
        if c not in conviction_buckets:
            conviction_buckets[c] = []
        if t["return_pct"] is not None:
            conviction_buckets[c].append(t["return_pct"])

    # Sort conviction levels by star count descending
    conviction_order = sorted(conviction_buckets.keys(), key=lambda x: -len(x))

    # --- Holding period ---
    holding_days = []
    for t in trades:
        start = t["entry_date"]
        if not start:
            continue
        if t["status"] == "CLOSED" and t["exit_date"]:
            end = t["exit_date"]
        else:
            end = date.today()
        holding_days.append((end - start).days)

    avg_holding = sum(holding_days) / len(holding_days) if holding_days else None

    # --- Benchmark ---
    valid_voo = [v for v in voo_returns if v is not None]
    avg_voo = sum(valid_voo) / len(valid_voo) if valid_voo else None

    if avg_return is not None and avg_voo is not None:
        alpha = avg_return - avg_voo
    else:
        alpha = None

    # --- Verdict ---
    if alpha is not None:
        if alpha > 1.0:
            verdict = "Outperforming"
        elif alpha < -1.0:
            verdict = "Underperforming"
        else:
            verdict = "Too early to tell"
    elif closed_count == 0:
        verdict = "Too early to tell"
    else:
        verdict = "Too early to tell"

    # --- Print ---
    print()
    from datetime import datetime as dt
    print(f"═══ PERFORMANCE SCORECARD ({dt.now().strftime('%Y-%m-%d %H:%M')}) ═══")
    print(f"Period: {period_start} to {period_end}")
    print()
    print("OVERVIEW")
    print(f"  Total calls: {total}")
    print(f"  Open: {open_count} | Closed: {closed_count}")
    print(f"  Win rate: {win_rate}")
    print()
    print("RETURNS (including unrealized)")
    print(f"  Average: {format_pct(avg_return)}")
    if best_trade["return_pct"] is not None:
        print(f"  Best: {best_trade['ticker']} ({format_pct(best_trade['return_pct'])})")
    else:
        print("  Best: N/A")
    if worst_trade["return_pct"] is not None:
        print(f"  Worst: {worst_trade['ticker']} ({format_pct(worst_trade['return_pct'])})")
    else:
        print("  Worst: N/A")
    print()
    print("BY CONVICTION")
    for c in conviction_order:
        rets = conviction_buckets[c]
        count = sum(1 for t in trades if t["conviction"] == c)
        if rets:
            avg_c = sum(rets) / len(rets)
            print(f"  {c}: {count} trades, avg {format_pct(avg_c)}")
        else:
            print(f"  {c}: {count} trades, avg N/A")
    print()
    print("HOLDING PERIOD")
    if avg_holding is not None:
        print(f"  Average: {avg_holding:.0f} days")
    else:
        print("  Average: N/A")
    print()
    print("VS BENCHMARK (VOO)")
    print(f"  Portfolio avg: {format_pct(avg_return)}")
    print(f"  VOO same periods: {format_pct(avg_voo)}")
    print(f"  Alpha: {format_pct(alpha)}")
    print()
    print(f"VERDICT: {verdict}")
    print()


def main():
    with VaultDB() as db:
        db_rows = db.get_all_trades()
        trades_raw = []
        for r in db_rows:
            trades_raw.append({
                "date": r["date"],
                "ticker": r["ticker"],
                "action": r["action"],
                "entry": str(r["entry_price"]) if r["entry_price"] else "",
                "stop": str(r["stop_loss"]) if r["stop_loss"] else "",
                "target": r["target"] or "",
                "conviction": r["conviction"] or "",
                "status": r["status"] or "",
                "exit_price": str(r["exit_price"]) if r["exit_price"] else "",
                "exit_date": r["exit_date"] or "",
                "return_pct": str(r["return_pct"]) if r["return_pct"] is not None else "",
                "notes": r["notes"] or "",
            })
    if not trades_raw:
        print_scorecard([], [])
        return

    print("Fetching live prices...")
    trades = compute_trade_metrics(trades_raw)

    print("Fetching VOO benchmark data...")
    voo_returns = compute_benchmark(trades)

    print_scorecard(trades, voo_returns)

    # Write trade stats snapshot to DB
    try:
        with VaultDB() as db:
            # Update return_pct for open trades in DB based on live prices
            for t in trades:
                if t["status"] == "OPEN" and t["return_pct"] is not None:
                    try:
                        db.conn.execute("""
                            UPDATE trades SET return_pct=?
                            WHERE ticker=? AND status='OPEN'
                        """, (round(t["return_pct"], 2), t["ticker"]))
                    except Exception:
                        pass
            db.conn.commit()

            # Save scorecard snapshot for performance trending
            returns = [t["return_pct"] for t in trades if t["return_pct"] is not None]
            avg_return = sum(returns) / len(returns) if returns else None
            valid_voo = [v for v in voo_returns if v is not None]
            avg_voo = sum(valid_voo) / len(valid_voo) if valid_voo else None

            total = len(trades)
            open_count = sum(1 for t in trades if t["status"] == "OPEN")
            closed_count = sum(1 for t in trades if t["status"] == "CLOSED")
            closed_with_return = [t for t in trades if t["status"] == "CLOSED" and t["return_pct"] is not None]
            win_rate = None
            if closed_with_return:
                wins = sum(1 for t in closed_with_return if t["return_pct"] > 0)
                win_rate = (wins / len(closed_with_return)) * 100

            best = max(trades, key=lambda t: t["return_pct"] if t["return_pct"] is not None else float("-inf"))
            worst = min(trades, key=lambda t: t["return_pct"] if t["return_pct"] is not None else float("inf"))

            holding_days = []
            for t in trades:
                if t["entry_date"]:
                    end = t["exit_date"] if t["status"] == "CLOSED" and t["exit_date"] else date.today()
                    holding_days.append((end - t["entry_date"]).days)
            avg_holding = sum(holding_days) / len(holding_days) if holding_days else None

            alpha = (avg_return - avg_voo) if avg_return is not None and avg_voo is not None else None
            if alpha is not None:
                verdict = "Outperforming" if alpha > 1.0 else "Underperforming" if alpha < -1.0 else "Too early to tell"
            else:
                verdict = "Too early to tell"

            db.save_scorecard(
                total_trades=total,
                open_trades=open_count,
                closed_trades=closed_count,
                win_rate=win_rate,
                avg_return=round(avg_return, 2) if avg_return is not None else None,
                best_ticker=best["ticker"] if best["return_pct"] is not None else None,
                best_return=round(best["return_pct"], 2) if best["return_pct"] is not None else None,
                worst_ticker=worst["ticker"] if worst["return_pct"] is not None else None,
                worst_return=round(worst["return_pct"], 2) if worst["return_pct"] is not None else None,
                avg_holding_days=round(avg_holding, 1) if avg_holding is not None else None,
                voo_avg=round(avg_voo, 2) if avg_voo is not None else None,
                alpha=round(alpha, 2) if alpha is not None else None,
                verdict=verdict,
            )
    except Exception as e:
        print(f"Warning: could not save scorecard snapshot: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
