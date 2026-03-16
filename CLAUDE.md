# Vault Research Desk v2

## What This Is
A personal investment research system with 4 analysis phases, adversarial validation, and behavioral coaching.

## How to Run
- `report` or `report pdf` → full pipeline (Research → Strategy → Devil's Gate → Report)
- `flash` → quick market alert (skips Devil's Gate)
- `analyze [TICKER]` → deep dive on one stock
- `morning` → daily briefing with market status, regime, smart money divergence
- `changes` → what moved since last report

## Unified CLI — Flows (Pavlo's primary commands)
```bash
# Daily startup — everything in one view
python3 tools/vault.py start              # Morning briefing + plan + news impact + regime

# Before buying
python3 tools/vault.py buy-flow XOM 600   # Size + simulate + smart money + news (auto-reads conviction from report)

# After buying
python3 tools/vault.py post-trade XOM 156 5  # Log trade + score + drift check

# Research a stock
python3 tools/vault.py research-flow NVDA    # Data + smart money + insider + news + sizing

# End of week
python3 tools/vault.py review             # Score + drift + regime + peers + projection
```

## Unified CLI — All Commands
```bash
# Quick checks
python3 tools/vault.py status            # One-line: $791 (-0.1%) | 4 positions | RISK-OFF | PRE-MARKET
python3 tools/vault.py morning           # Full daily briefing (alias: m)
python3 tools/vault.py plan              # Show current action plan from notes/
python3 tools/vault.py regime            # Market regime (risk-on/off) with signals
python3 tools/vault.py alerts            # Check alert conditions (alias: a)

# Portfolio management (DB-first, auto-syncs portfolio.md)
python3 tools/vault.py portfolio         # Show holdings + P&L + market status (alias: p)
python3 tools/vault.py portfolio add XOM 5 156.12 2026-03-18  # Add position
python3 tools/vault.py portfolio update GOOGL 1.5 305         # Update position
python3 tools/vault.py portfolio remove CFG                    # Remove position
python3 tools/vault.py portfolio cash 4500                     # Update cash available
python3 tools/vault.py drift             # Allocation drift analysis
python3 tools/vault.py size GOOGL ***    # Position sizing calculator
python3 tools/vault.py simulate XOM 1000 LMT 800  # Simulate new positions
python3 tools/vault.py convert TICKER P S # Watchlist → trade conversion
python3 tools/vault.py journal GOOGL "reflection"  # Trade journal

# Research
python3 tools/vault.py score            # Performance scorecard + Kelly + turnover (alias: s)
python3 tools/vault.py news GOOGL       # News for ticker (alias: n)
python3 tools/vault.py news-impact      # News contradicting active theses
python3 tools/vault.py insider GOOGL    # Insider activity
python3 tools/vault.py insider --portfolio  # All holdings
python3 tools/vault.py correlation      # Portfolio correlation matrix
python3 tools/vault.py smart-money GOOGL # Full smart money check
python3 tools/vault.py learn            # Fetch + analyze smart money signals
python3 tools/vault.py theses           # Show active investment theses
python3 tools/vault.py peers            # Compare to Buffett/ARK/gurus
python3 tools/vault.py backtest         # Backtest closed trades by conviction
python3 tools/vault.py project          # 5-year investment projector
python3 tools/vault.py project 6000 10  # Custom: $6K/mo, 10 years
python3 tools/vault.py changes          # What moved since last report (alias: c)
python3 tools/vault.py compare D1 D2    # Compare two reports side-by-side

# Report pipeline (mostly system-internal)
python3 tools/vault.py weekly           # Full weekly pipeline (auto)
python3 tools/vault.py preflight        # Phase 0: all data collection
python3 tools/vault.py skeleton         # Generate pre-filled report draft
python3 tools/vault.py validate         # Pre-report validation gate
python3 tools/vault.py search-log       # Generate Search Log
python3 tools/vault.py audit            # Post-report quality check
python3 tools/vault.py fetch            # Raw data fetch (prices + technicals)
python3 tools/vault.py screen           # S&P 500 screener

# System
python3 tools/vault.py health           # System health check
python3 tools/vault.py self-analyze     # Self-review + auto-patch refresh
python3 tools/vault.py dashboard        # Portfolio P&L (quick)
python3 tools/vault.py help             # Full command reference

# Shortcuts: m=morning, s=score, a=alerts, n=news, c=changes, h=help, p=portfolio
```

## Project Structure
```
vault_research_desk/
├── CLAUDE.md                  ← You are here
├── portfolio.md               ← SINGLE SOURCE OF TRUTH (auto-synced from DB)
│
├── system/                    ← Analysis pipeline
│   ├── 00_system.md           ← Master rules, execution flow, sizing priority
│   ├── 01_research.md         ← Phase 1: Macro + sectors + sentiment
│   ├── 02_strategy.md         ← Phase 2: Picks + risk + sizing
│   ├── 03_devils_gate.md      ← Phase 3: Adversarial validation (8 tests)
│   ├── 04_report.md           ← Phase 4: Report format + Gut Check + DG summary
│   └── 05_position_mgmt.md    ← Position scaling, stops, profit-taking
│
├── tools/                     ← Scripts and data
│   ├── vault.py               ← Unified CLI (40+ commands, 5 flows)
│   ├── db.py                  ← SQLite database (30+ methods)
│   ├── data_fetcher.py        ← Market data + breadth via yfinance
│   ├── screener.py            ← S&P 500 scanner (RSI, DMA, volume)
│   ├── scorer.py              ← Scorecard + Kelly Criterion + turnover
│   ├── alerts.py              ← Alerts + stop-loss + sector concentration + escalation
│   ├── self_analyze.py        ← Self-improvement + auto-patching
│   ├── learn_from_pros.py     ← Smart money (5 sources → learnings)
│   ├── thesis_tracker.py      ← Thesis tracking + flip detection
│   ├── correlation.py         ← Correlation matrix + risk score
│   ├── insider_check.py       ← SEC Form 4 insider signals
│   ├── watchlist_extract.py   ← Auto-extract picks from reports
│   ├── news.py                ← Finnhub + Marketaux news + sentiment
│   ├── smart_money.py         ← ARK daily trades + Dataroma guru holdings
│   ├── ibkr_sync.py           ← IBKR CSV import
│   ├── html_report.py         ← Markdown → styled HTML (nested lists, links, accessibility)
│   └── templates/
│       ├── base.html
│       └── styles.css
│
├── vault.db                   ← SQLite (20 tables, 19 indices)
├── notes/                     ← Action plans (FOMC plan, trade plans)
├── reports/                   ← Generated reports (MD + HTML)
└── trades/                    ← Trade records
```

## Key Files (read in this order)
1. `system/00_system.md` — Master rules, execution flow, sizing priority hierarchy
2. `portfolio.md` — **SINGLE SOURCE OF TRUTH** for all investor data
3. `system/01_research.md` → `02_strategy.md` → `03_devils_gate.md` → `04_report.md`
4. `system/05_position_mgmt.md` — Scaling, stops, profit-taking rules
5. `tools/data_fetcher.py` — Run before every report for real market data

## Critical Rules
- **portfolio.md is the ONLY source of truth.** DB syncs from it. No hardcoded values.
- **Portfolio updates go through DB first:** `vault portfolio add/update/remove/cash` auto-syncs portfolio.md.
- **Never fabricate data.** If you can't verify it, say "not available."
- **Run `vault preflight` before reports.** Collects all data + refreshes auto-patches.
- **Every phase posts output in chat.** If it's not visible, it didn't happen.
- **Devil's Gate is mandatory** on `report` and `analyze`. All 8 tests.
- **Devil's Gate summary MUST appear in final report.** (Validation Summary section)
- **Search Log MUST appear in final report.** Every ticker needs a verified price row.
- **Gut Check section is mandatory.** Never skip behavioral coaching.
- **Report audit target: Grade A (9/9).** Run `vault audit` after every report.
- **Risk/reward: 2:1 minimum** for all picks. 1.5:1 only for `*` speculative.
- **Entry zones:** ≤5% = PASS, 5-7% = FLAG, >7% = REJECT.
- **Sizing priority:** Hard limits → Circuit breaker → Conviction → Risk tolerance → Core/Satellite → Kelly.

## Portfolio Update Workflow
Pavlo sends screenshots or trade confirmations. Claude updates:
```bash
vault portfolio add XOM 5 156.12 2026-03-18   # Adds to DB + portfolio.md + logs trade
vault portfolio cash 900                        # Updates cash in both places
```
No manual file editing needed.

## API Keys (set in ~/.zshrc)
```bash
export FINNHUB_API_KEY="..."       # News headlines (finnhub.io)
export MARKETAUX_API_KEY="..."     # News sentiment scores (marketaux.com)
```

## Market Hours Awareness
All portfolio/morning/buy-flow commands show market status:
- **OPEN** — Live prices (ET 9:30-16:00 weekdays)
- **PRE-MARKET** — Futures only (ET 4:00-9:30)
- **AFTER-HOURS** — Limited trading (ET 16:00-20:00)
- **CLOSED** — Weekend/overnight. Prices are last session's close.

Weekend staleness threshold: 72h (Friday close → Monday morning is OK).

## Database (vault.db)
20 tables, 19 performance indices. Key methods:
```python
from db import VaultDB
with VaultDB() as db:
    db.portfolio_dashboard()           # Holdings + prices + P&L
    db.risk_dashboard()                # Concentration, drawdown, circuit breaker
    db.portfolio_drift()               # Allocation vs target
    db.calculate_position_size(t, c)   # Sizing with tranches
    db.simulate_additions([...])       # Test new positions
    db.detect_regime()                 # Risk-on/off classification
    db.detect_smart_money_divergence() # Contested theses
    db.get_thesis_relevant_news()      # News vs active theses
    db.compare_reports(d1, d2)         # Report diff
    db.backtest_recommendations()      # Trade history analysis
    db.peer_comparison()               # vs Buffett/ARK/gurus
    db.generate_search_log(tickers)    # Auto Search Log
    db.generate_report_skeleton()      # Pre-filled report draft
```

## Auto-Learned Rules (updated by self-analyze)
Embedded in system files as AUTO-FIX and PRO-INSIGHT patches:
- **VERIFICATION REMINDER** (01_research.md): Data citation required
- **SELL CHECK** (02_strategy.md): Buy bias correction
- **REPETITION GUARD** (02_strategy.md): No re-recommending bought stocks
- **CONCENTRATION BLOCKERS** (03_devils_gate.md): Auto-detected position limits
- **SECTOR BLOCKERS** (03_devils_gate.md): Auto-detected sector limits
- **STOP-LOSS ENFORCEMENT** (04_report.md): Meaningful levels required
- **CONVICTION SIZING** (00_system.md): *** up to 18%, ** 12%, * 7%
- **BUSINESS CYCLE MAPPING** (01_research.md): Sector rotation by cycle
- **SMART MONEY VALIDATION** (02_strategy.md): 13F + guru + ARK + insider check
- **SMART MONEY CHALLENGE** (03_devils_gate.md): Devil's Gate smart money test
- **PORTFOLIO-LEVEL RISK** (05_position_mgmt.md): Drawdown circuit breaker

Patches auto-refresh during `vault preflight` (runs self_analyze.py).

## Don't
- Don't hardcode investor data in system files — read from portfolio.md
- Don't fabricate sentiment indicators you can't verify
- Don't claim to see chart patterns — use computed technicals from data_fetcher.py
- Don't skip Devil's Gate to save time
- Don't assume the investor bought something because a previous report recommended it
- Don't modify portfolio.md manually — use `vault portfolio` commands
- Don't trust screener output blindly — it flags candidates, not recommendations
