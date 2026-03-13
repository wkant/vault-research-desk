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
- `learn-from-pros` → fetch hedge fund 13F data, analyze patterns, improve system files

## Project Structure
```
vault_research_desk/
├── CLAUDE.md                  ← You are here
├── project_instructions.md    ← Overview and quick start
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
│   ├── learn_from_pros.py     ← 13F hedge fund analysis → system improvements
│   ├── thesis_tracker.py      ← Track investment theses, detect flip-flops
│   ├── correlation.py         ← Portfolio correlation matrix + risk score
│   ├── insider_check.py       ← SEC Form 4 insider buying/selling signals
│   ├── html_report.py         ← Markdown → styled HTML
│   ├── templates/             ← HTML/CSS templates
│   │   ├── base.html
│   │   └── styles.css
│   ├── performance_log.csv    ← Track every call for scoring
│   └── screener_output.csv    ← Latest screener results (auto-generated)
│
├── improvements/              ← Self-analysis reports
│   └── self_improvement_YYYY-MM-DD.md
│
├── reports/                   ← Generated analysis reports (weekly history)
│   ├── report_YYYY-MM-DD.md
│   ├── report_YYYY-MM-DD.html  ← Default output
│   └── report_YYYY-MM-DD.pdf   ← On demand
│
├── trades/                    ← Actual trade actions taken
│   └── trade_YYYY-MM-DD.md    ← What was bought/sold, linked to source report
│
└── archive_v1/                ← Previous 7-agent system (reference only)
```

## Key Files (read in this order)
1. `project_instructions.md` — Overview and quick start
2. `system/00_system.md` — Master rules, execution flow, commands
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
- **Track performance** in `tools/performance_log.csv`. Compare vs VOO benchmark every report.
- **Screener is a tool, not an oracle.** Screener output provides candidates — every pick still needs a thesis.
- **IBKR sync previews by default.** Use `--write` only when confirmed by investor.

## Data Pipeline
```bash
python3 tools/data_fetcher.py                    # Full data fetch + breadth
python3 tools/data_fetcher.py NVDA LMT           # Add specific candidates
python3 tools/data_fetcher.py --portfolio-only    # Portfolio only
```

## Screening
```bash
python3 tools/screener.py                        # Full S&P 500 scan (~500 tickers)
python3 tools/screener.py --sample 50            # Quick scan (50 random tickers)
python3 tools/screener.py --top 10               # Show top 10 results
```

## Monitoring
```bash
python3 tools/scorer.py                          # Performance scorecard
python3 tools/alerts.py                          # Check alert conditions
python3 tools/alerts.py reports/report_2026-03-11.md  # Check specific report
python3 tools/self_analyze.py                    # Self-improvement analysis
python3 tools/learn_from_pros.py                 # Fetch 13F data, learn, improve system
python3 tools/learn_from_pros.py --cleanup       # Delete fetched data after learning
python3 tools/thesis_tracker.py                  # Show all active theses
python3 tools/thesis_tracker.py extract reports/report_YYYY-MM-DD.md  # Extract theses from report
python3 tools/thesis_tracker.py check            # Check for stale/flipped theses
python3 tools/correlation.py                     # Portfolio correlation matrix
python3 tools/correlation.py --add NVDA          # Test adding a ticker
python3 tools/insider_check.py GOOGL AAPL        # Check insider activity
python3 tools/insider_check.py --portfolio       # Check all portfolio holdings
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

## Don't
- Don't hardcode investor data in system files — read from portfolio.md
- Don't fabricate sentiment indicators you can't verify
- Don't claim to see chart patterns — use computed technicals from data_fetcher.py
- Don't skip Devil's Gate to save time
- Don't assume the investor bought something because a previous report recommended it
- Don't modify portfolio.md without being asked
- Don't trust screener output blindly — it flags candidates, not recommendations
