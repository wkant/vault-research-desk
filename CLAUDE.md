# Vault Research Desk v2

## What This Is
A personal investment research system with 4 analysis phases, adversarial validation, and behavioral coaching.

## How to Run
- `report` or `report pdf` → full pipeline (Research → Strategy → Devil's Gate → Report)
- `flash` → quick market alert (skips Devil's Gate)
- `analyze [TICKER]` → deep dive on one stock
- `score` → performance scorecard
- `screen` → S&P 500 stock screener
- `alerts` → check alert conditions from latest report
- `rebalance` → portfolio drift check
- `sync [file]` → import IBKR CSV export into portfolio.md
- `self-analyze` → system self-review: mistakes, patterns, improvements
- `learn-from-pros` → fetch smart money data from 5 sources, cross-reference portfolio, save learnings to DB
- `morning` → one-command briefing: portfolio, market, theses, watchlist, learnings, issues
- `changes` → what moved since last report (prices, smart money, insider activity)

## Unified CLI
```bash
# Daily
python3 tools/vault.py morning       # Start here every day
python3 tools/vault.py changes       # What changed since last report
python3 tools/vault.py alerts        # Check alert thresholds
python3 tools/vault.py score         # Performance scorecard
python3 tools/vault.py regime        # Market regime detection (risk-on/off)

# Portfolio
python3 tools/vault.py drift         # Allocation drift analysis
python3 tools/vault.py size GOOGL ** # Position sizing calculator
python3 tools/vault.py simulate XOM 1000 LMT 800  # Simulate new positions
python3 tools/vault.py convert TICKER PRICE SHARES # Watchlist → trade
python3 tools/vault.py journal GOOGL "reflection"  # Trade journal

# Report Pipeline
python3 tools/vault.py weekly        # Full weekly pipeline (auto)
python3 tools/vault.py preflight     # Phase 0: all data collection
python3 tools/vault.py skeleton      # Generate pre-filled report draft
python3 tools/vault.py validate      # Pre-report validation gate
python3 tools/vault.py search-log    # Generate Search Log
python3 tools/vault.py audit         # Post-report quality check
python3 tools/vault.py compare D1 D2 # Compare two reports

# Analysis
python3 tools/vault.py peers         # Compare to top investors
python3 tools/vault.py backtest      # Backtest closed trades
python3 tools/vault.py help          # Full command reference
# Shortcuts: m=morning, s=score, a=alerts, n=news, c=changes, h=help
```

## Project Structure
```
vault_research_desk/
├── CLAUDE.md                  ← You are here
├── portfolio.md               ← SINGLE SOURCE OF TRUTH (investor manages)
│
├── system/                    ← Analysis pipeline (do not modify)
│   ├── 00_system.md           ← Master rules, execution flow, commands
│   ├── 01_research.md         ← Phase 1: Macro + sectors + sentiment
│   ├── 02_strategy.md         ← Phase 2: Picks + risk + sizing
│   ├── 03_devils_gate.md      ← Phase 3: Adversarial validation (8 tests)
│   ├── 04_report.md           ← Phase 4: Final report format + Gut Check
│   └── 05_position_mgmt.md    ← Position scaling, stops, profit-taking
│
├── tools/                     ← Scripts and data
│   ├── data_fetcher.py        ← Market data + breadth via yfinance
│   ├── screener.py            ← S&P 500 scanner (RSI, DMA, volume signals)
│   ├── scorer.py              ← Performance scorecard calculator
│   ├── alerts.py              ← Alert condition monitor
│   ├── ibkr_sync.py           ← IBKR CSV → portfolio.md sync
│   ├── self_analyze.py         ← Self-improvement analysis engine
│   ├── learn_from_pros.py     ← Smart money learning engine (5 sources → portfolio learnings)
│   ├── thesis_tracker.py      ← Track investment theses, detect flip-flops
│   ├── correlation.py         ← Portfolio correlation matrix + risk score
│   ├── insider_check.py       ← SEC Form 4 insider buying/selling signals
│   ├── watchlist_extract.py   ← Auto-extract watchlist picks from reports
│   ├── vault.py               ← Unified CLI (single entry point for all tools)
│   ├── db.py                  ← SQLite database module (VaultDB)
│   ├── news.py                ← News fetcher (Finnhub + Marketaux) + sentiment
│   ├── smart_money.py         ← ARK daily trades + Dataroma guru holdings
│   ├── html_report.py         ← Markdown → styled HTML
│   └── templates/             ← HTML/CSS templates
│       ├── base.html
│       └── styles.css
│
├── vault.db                   ← SQLite database (all structured data)
│                                 (improvements, research, 13F, news, etc.)
│
├── reports/                   ← Generated analysis reports (weekly history)
│   ├── report_YYYY-MM-DD.md
│   ├── report_YYYY-MM-DD.html  ← Default output
│   └── report_YYYY-MM-DD.pdf   ← On demand
│
└── trades/                    ← Actual trade actions (created when trades happen)
    └── trade_YYYY-MM-DD.md    ← What was bought/sold, linked to source report
```

## Key Files (read in this order)
1. `system/00_system.md` — Master rules, execution flow, commands
3. `portfolio.md` — **SINGLE SOURCE OF TRUTH** for all investor data
4. `system/01_research.md` → `system/02_strategy.md` → `system/03_devils_gate.md` → `system/04_report.md`
5. `system/05_position_mgmt.md` — Scaling, stops, profit-taking rules
6. `tools/data_fetcher.py` — Run before every report for real market data

## Critical Rules
- **portfolio.md is the ONLY source of truth.** All investor-specific data lives there. No hardcoded values in system files.
- **Never modify portfolio.md** unless the investor explicitly asks.
- **Never fabricate data.** If you can't verify it, say "not available."
- **Run `python3 tools/data_fetcher.py` first.** Verified prices in seconds.
- **Every phase posts output in chat.** If it's not visible, it didn't happen.
- **Devil's Gate is mandatory** on `report` and `analyze`. All 8 tests.
- **Gut Check section is mandatory.** Never skip behavioral coaching.
- **Track performance** in `vault.db`. Compare vs VOO benchmark every report.
- **Screener is a tool, not an oracle.** Screener output provides candidates — every pick still needs a thesis.
- **IBKR sync previews by default.** Use `--write` only when confirmed by investor.

## API Keys (set in ~/.zshrc)
```bash
export FINNHUB_API_KEY="..."       # News headlines (finnhub.io)
export MARKETAUX_API_KEY="..."     # News sentiment scores (marketaux.com)
# StockAnalysis key exists but no public API — web-only
```

## Data Pipeline
```bash
python3 tools/data_fetcher.py                    # Full data fetch + breadth + news
python3 tools/data_fetcher.py NVDA LMT           # Add specific candidates
python3 tools/data_fetcher.py --portfolio-only    # Portfolio only
```

## Screening
```bash
python3 tools/screener.py                        # Full S&P 500 scan (~500 tickers)
python3 tools/screener.py --sample 50            # Quick scan (50 random tickers)
python3 tools/screener.py --top 10               # Show top 10 results
```

## Quality & Audit
```bash
python3 tools/vault.py preflight                 # Phase 0: all data collection before report
python3 tools/vault.py audit                     # Audit latest report for pipeline compliance
python3 tools/vault.py audit reports/report_YYYY-MM-DD.md  # Audit specific report
python3 tools/vault.py search-log                # Generate Search Log from cached prices
python3 tools/vault.py search-log XOM LMT        # Include extra tickers
```

## Monitoring
```bash
python3 tools/scorer.py                          # Performance scorecard
python3 tools/alerts.py                          # Check alert conditions
python3 tools/alerts.py reports/report_2026-03-11.md  # Check specific report
python3 tools/self_analyze.py                    # Self-improvement analysis
python3 tools/learn_from_pros.py                 # Fetch 5 sources, cross-ref portfolio, save learnings
python3 tools/learn_from_pros.py --analyze       # Analyze cached data only (no API calls)
python3 tools/learn_from_pros.py --summary       # Show latest learnings summary
python3 tools/learn_from_pros.py --cleanup       # Clear learnings from DB
python3 tools/thesis_tracker.py                  # Show all active theses
python3 tools/thesis_tracker.py extract reports/report_YYYY-MM-DD.md  # Extract theses from report
python3 tools/thesis_tracker.py check            # Check for stale/flipped theses
python3 tools/correlation.py                     # Portfolio correlation matrix
python3 tools/correlation.py --add NVDA          # Test adding a ticker
python3 tools/insider_check.py GOOGL AAPL        # Check insider activity
python3 tools/insider_check.py --portfolio       # Check all portfolio holdings
python3 tools/news.py GOOGL AAPL                 # Fetch news (Finnhub + Marketaux)
python3 tools/news.py --portfolio                # News for all holdings
python3 tools/news.py --market                   # General market news
python3 tools/news.py --sentiment GOOGL          # Sentiment summary (Marketaux scores)
python3 tools/smart_money.py ark                 # ARK Invest daily trades
python3 tools/smart_money.py ark --days 30       # ARK trades last 30 days
python3 tools/smart_money.py gurus               # Top superinvestor holdings (Dataroma)
python3 tools/smart_money.py gurus BRK psc       # Specific gurus (Buffett, Ackman)
python3 tools/smart_money.py consensus           # Tickers held by 2+ gurus
python3 tools/smart_money.py check GOOGL         # Full smart money check (all sources)
```

## Database
```bash
python3 tools/db.py morning             # Morning briefing (portfolio + theses + watchlist + learnings)
python3 tools/db.py dashboard            # Portfolio overview with live P&L
python3 tools/db.py consensus            # Institutional consensus holdings
python3 tools/db.py smart-money GOOGL    # Full smart money signal for a ticker
python3 tools/db.py export               # Dump all tables to CSV (human-readable)
```

**In code:**
```python
from db import VaultDB
with VaultDB() as db:
    db.portfolio_dashboard()       # Holdings + prices + P&L in one query
    db.risk_dashboard()            # Concentration, drawdown, circuit breaker
    db.smart_money_check("GOOGL")  # Institutional + insider + consensus
    db.get_consensus(min_funds=3)  # Tickers held by 3+ top funds
    db.get_cached_quote("GOOGL")   # Price from cache (avoids API calls)
    db.watchlist_performance()     # How watchlist picks are doing
    db.get_cluster_buys()          # Insider cluster buy signals
    db.get_ark_trades(days=30)     # ARK daily trades
    db.get_ark_conviction("TSLA") # ARK accumulating or distributing?
    db.get_guru_consensus(min_gurus=2)  # Tickers held by 2+ superinvestors
    db.get_cached_news("GOOGL")   # Cached news articles
    db.get_recent_news(days=7)    # All recent news
    db.get_active_improvements()  # Current issues from self-analyze
    db.get_improvements('learn_from_pros')  # Pro learnings history
```

## Portfolio Sync
```bash
python3 tools/ibkr_sync.py export.csv            # Preview IBKR import
python3 tools/ibkr_sync.py export.csv --write    # Write to portfolio.md
```

## Report Generation
```bash
python3 tools/html_report.py reports/report_YYYY-MM-DD.md   # Markdown → HTML (default)
# PDF: generated via ReportLab inline (requires: pip3 install reportlab)
```


<!-- AUTO-FIX: LEARNED RULES -->
## Auto-Learned Rules (updated 2026-03-15 by self-analyze)
The system has learned these rules from analyzing reports, trades, and pro data.
They are embedded in system files as AUTO-FIX and PRO-INSIGHT patches.

- **VERIFICATION REMINDER** (01_research.md): DATA CITATION RULE (auto-added by self-analyze):
- **SELL CHECK** (02_strategy.md): SELL/TRIM CHECK (auto-added by self-analyze):
- **REPETITION GUARD** (02_strategy.md): REPETITION GUARD (auto-added by self-analyze):
- **CONCENTRATION BLOCKERS** (03_devils_gate.md): Auto-detected concentration blockers (from self-analyze):
- **SECTOR BLOCKERS** (03_devils_gate.md): Auto-detected sector concentration (from self-analyze):
- **STOP-LOSS ENFORCEMENT** (04_report.md): STOP-LOSS RULE (auto-added by self-analyze):
- **CONVICTION SIZING** (00_system.md): learned from pro analysis
- **BUSINESS CYCLE MAPPING** (01_research.md): learned from pro analysis
- **SMART MONEY VALIDATION** (02_strategy.md): learned from pro analysis
- **SMART MONEY CHALLENGE** (03_devils_gate.md): learned from pro analysis
- **PORTFOLIO-LEVEL RISK** (05_position_mgmt.md): learned from pro analysis

<!-- END LEARNED RULES -->
## Don't
- Don't hardcode investor data in system files — read from portfolio.md
- Don't fabricate sentiment indicators you can't verify
- Don't claim to see chart patterns — use computed technicals from data_fetcher.py
- Don't skip Devil's Gate to save time
- Don't assume the investor bought something because a previous report recommended it
- Don't modify portfolio.md without being asked
- Don't trust screener output blindly — it flags candidates, not recommendations
