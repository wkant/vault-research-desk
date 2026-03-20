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
├── portfolio.md               ← Auto-generated export from DB (not the source of truth)
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
├── vault.db                   ← SQLite (21 tables, 21 indices) — SOURCE OF TRUTH for portfolio
├── notes/                     ← Action plans (FOMC plan, trade plans)
├── reports/                   ← Generated reports (MD + HTML)
└── trades/                    ← Trade records
```

## Key Files (read in this order)
1. `system/00_system.md` — Master rules, execution flow, sizing priority hierarchy
2. `vault.db` (via `vault portfolio`) — **SOURCE OF TRUTH** for holdings, settings, cash
3. `system/01_research.md` → `02_strategy.md` → `03_devils_gate.md` → `04_report.md`
4. `system/05_position_mgmt.md` — Scaling, stops, profit-taking rules
5. `tools/data_fetcher.py` — Run before every report for real market data
6. `portfolio.md` — Auto-generated export from DB (`vault portfolio export`)

## Critical Rules
- **vault.db is the source of truth for portfolio.** portfolio.md is an auto-generated export (`vault portfolio export`).
- **Portfolio updates go through DB:** `vault portfolio add/update/remove/cash`. Never edit portfolio.md manually.
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
Pavlo sends screenshots or trade confirmations. Claude updates DB directly:
```bash
vault portfolio add XOM 5 156.12 2026-03-18   # Adds to DB + logs trade
vault portfolio update GOOGL 1.5 305           # Update existing position
vault portfolio remove CFG                      # Remove position
vault portfolio cash 900                        # Update cash available
vault portfolio export                          # Regenerate portfolio.md from DB (if needed)
vault p                                         # Quick view (alias)
```
DB is master. portfolio.md is export only. No manual file editing.

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
21 tables (including settings), 21 performance indices. Auto-cleanup runs on every morning briefing (marks stale learnings consumed, deduplicates improvements). Key methods:
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

<!-- AUTO-FIX: LEARNED RULES -->
## Auto-Learned Rules (updated 2026-03-20, full rewrite after logic audit + blind spot fixes)

### Core Logic Fixes (from logic audit 2026-03-20)
- **CONCENTRATION vs TOTAL CAPITAL** (00_system.md, db.py): Calculate position weights against total capital (holdings + cash), NOT just holdings. Fixed in code: `risk_dashboard()`, `portfolio_drift()`, `calculate_position_size()` all use `holdings_value + cash`.
- **FLASH SELL GUARD** (00_system.md): Flash only checks stop-losses, marks SELLs as "PRELIMINARY — confirm in next full report". No full thesis review in flash mode.
- **SELL/TRIM with CONTEXT GUARD** (02_strategy.md): Mandatory sell evaluation before buys, BUT: new portfolio (<30 days, <6 positions) with 0 sells is normal. Oversold override: no SELL at RSI <25 unless stop hit.
- **BALANCED MIX** (02_strategy.md): Every report considers growth + defensive + hedge + war/macro + broad market ETFs. If S&P RSI <35, VOO/SPLG must be evaluated. If strongest smart money signal is excluded, explain why.
- **BROAD MARKET ETFs** (02_strategy.md): VOO, SPY, SPLG, VTI, QQQ always evaluated as candidates. Don't get focused on individual picks and miss the obvious.
- **HEAD-TO-HEAD** (02_strategy.md): Every BUY must name the top alternative and explain why your pick is better.
- **CASH → SHY/BIL** (02_strategy.md): If cash >20% and yields >4%, recommend ultra-short bond ETFs instead of uninvested cash.
- **SECTOR ROTATION TRIGGER** (02_strategy.md): If held sector ETF in bottom 3 for 2+ reports and thesis weakened, FLAG for rotation.
- **DYNAMIC CONCENTRATION** (03_devils_gate.md): No hardcoded ticker names or percentages. Calculate fresh from DB every time.
- **WORD COUNT** (04_report.md): Target <2000 prose words. Tables (Search Log, Portfolio, Validation) don't count.
- **SECTION CHECKLIST** (04_report.md): 15 mandatory sections. Search Log + Validation Summary are CRITICAL.
- **STOP-LOSS INVERTED** (05_position_mgmt.md, db.py): `*` speculative gets WIDEST stops (12-15%), `***` gets tightest (8-10%). Speculative picks need room to breathe.
- **CIRCUIT BREAKER FROM PEAK** (05_position_mgmt.md, db.py): Drawdown calculated from peak portfolio value (tracked in DB), not cost basis. Circuit breaker overrides "deploy cash in crash" rule.
- **REBALANCE vs CONVICTION** (05_position_mgmt.md): Drift trigger compares against conviction-adjusted targets, not equal-weight.
- **EARLY PORTFOLIO SIZING** (05_position_mgmt.md): Before 20 trades, max position = total_capital / (positions + 2), capped at conviction limit.

### Data & Screener Enhancements (from blind spot audit 2026-03-20)
- **SCREENER SCANS 31 ETFs** (screener.py): CORE_ETFS list always scanned — broad market, international, bonds, REITs, commodities, all sectors. Tagged `[ETF]` in results.
- **YIELD CURVE** (data_fetcher.py): 3M T-bill (`^IRX`) added. Prints `10Y-3M spread: [NORMAL/FLAT/INVERTED]`. Quantitative regime signal.
- **RSP BREADTH** (data_fetcher.py): RSP (equal-weight S&P) added to benchmark. `RSP/SPY spread` catches narrow vs broad market participation.
- **FORWARD P/E** (data_fetcher.py): Holdings show Fwd P/E, Trail P/E, PEG, Div Yield, Earnings Growth from yfinance `.info`.

### From Self-Analysis (pattern detection)
- **VERIFICATION REMINDER** (01_research.md): Every price must cite source
- **SCREENER MANDATE** (01_research.md): Run screener before every report
- **REPETITION GUARD** (02_strategy.md): Check DB for prior recommendations — no repeat BUYs on held positions without new catalyst
- **OPEN POSITION REVIEW** (05_position_mgmt.md): Mandatory health check every report — stop/thesis/concentration/profit-take

### From Pro Analysis (smart money insights)
- **CONVICTION SIZING** (00_system.md): *** up to 18%, ** up to 12%, * up to 7%
- **BUSINESS CYCLE MAPPING** (01_research.md): Map cycle stage → sector recommendations
- **SMART MONEY VALIDATION** (02_strategy.md): Check 13F + guru + ARK + insider for every BUY
- **SMART MONEY CHALLENGE** (03_devils_gate.md): If all 4 sources negative → FLAG
- **PORTFOLIO-LEVEL RISK** (05_position_mgmt.md): Drawdown circuit breaker, turnover check, Kelly criterion

<!-- END LEARNED RULES -->
## Don't
- Don't hardcode investor data in system files — read from DB via `vault portfolio`
- Don't hardcode portfolio values (dollar amounts, percentages, ticker names) in auto-patches — they go stale immediately
- Don't fabricate sentiment indicators you can't verify
- Don't claim to see chart patterns — use computed technicals from data_fetcher.py
- Don't skip Devil's Gate to save time
- Don't assume the investor bought something because a previous report recommended it
- Don't modify portfolio.md manually — use `vault portfolio` commands (DB is master)
- Don't trust screener output blindly — it flags candidates, not recommendations
- Don't generate a report without Search Log section — every ticker needs a verified price row
- Don't generate a report without Validation Summary (Devil's Gate) section
- Don't generate a report without running `vault preflight` first — data must be fresh
- Don't go 100% defensive just because regime is risk-off — evaluate ALL categories, adjust sizing
- Don't sell at RSI <25 unless stop-loss has been hit — that's panic selling
- Don't ignore broad market ETFs (VOO/SPLG) as candidates — especially when S&P is oversold
- Don't leave cash earning 0% when short-term yields are >4% — recommend SHY/BIL
