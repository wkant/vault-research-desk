# Vault Research Desk v2 — Project Instructions

## What This Is
A personal investment research system for the investor. Four phases of analysis — Research, Strategy, Devil's Gate validation, and Report — produce actionable weekly reports with BUY/HOLD/SELL calls, risk assessment, and behavioral coaching.

---

## Quick Start

When the investor types `report` or `report pdf`:

1. **Read `system/00_system.md` first** — it has the execution flow, shared rules, and commands
2. **Run `python3 tools/data_fetcher.py`** — gets real market data (prices, technicals, sectors)
3. **Follow the 4-phase pipeline** defined in `system/00_system.md`
4. **Every phase posts output in chat** before the next phase starts

---

## File Structure

```
vault_research_desk/
├── CLAUDE.md                  ← Project config for Claude Code
├── project_instructions.md    ← Overview and quick start
├── portfolio.md               ← SINGLE SOURCE OF TRUTH (investor manages)
│
├── system/                    ← Analysis pipeline
│   ├── 00_system.md           ← Master rules, execution flow, commands
│   ├── 01_research.md         ← Phase 1: Macro + sectors + sentiment
│   ├── 02_strategy.md         ← Phase 2: Picks + risk + sizing
│   ├── 03_devils_gate.md      ← Phase 3: Adversarial validation (8 tests)
│   ├── 04_report.md           ← Phase 4: Final report format + Gut Check
│   └── 05_position_mgmt.md    ← Position scaling, stops, profit-taking
│
├── tools/                     ← Scripts and data
│   ├── data_fetcher.py        ← Market data + breadth via yfinance
│   ├── screener.py            ← S&P 500 scanner (RSI, DMA, volume)
│   ├── scorer.py              ← Performance scorecard calculator
│   ├── alerts.py              ← Alert condition monitor
│   ├── ibkr_sync.py           ← IBKR CSV → portfolio.md sync
│   ├── html_report.py         ← Markdown → styled HTML
│   ├── templates/             ← HTML/CSS templates
│   └── performance_log.csv    ← Track every call for scoring
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

---

## Execution Flow

```
PHASE 0: tools/data_fetcher.py → real prices, technicals, sector data
PHASE 1: Research (system/01_research.md) → macro regime, sectors, sentiment
PHASE 2: Strategy (system/02_strategy.md) → picks, risk, sizing, price verification
PHASE 3: Devil's Gate (system/03_devils_gate.md) → 8 adversarial tests
PHASE 4: Report (system/04_report.md) → final output with Gut Check
```

Each phase visible in chat. If it's not visible, it didn't happen.

---

## Critical Rules

### Portfolio — Single Source of Truth
- `portfolio.md` is the ONLY source of truth for holdings, settings, AND investor profile
- All investor-specific data (name, location, broker, experience, preferences) lives in portfolio.md
- Never use memory, chat history, or assumptions to determine holdings
- A past BUY recommendation does NOT mean the investor bought it
- If portfolio.md is empty → no HOLD/SELL calls, all recs are new BUYs
- The system NEVER modifies portfolio.md unless the investor explicitly asks

### Data
- Run `data_fetcher.py` before every report for verified prices
- Web search only for qualitative context (geopolitics, news, Fed commentary)
- Never fabricate data you can't verify (put/call ratios, fund flows, chart patterns)
- Every ticker in the report must be in the Search Log

### Honesty
- Only report what you can verify
- Own past mistakes in performance review
- When uncertain, say so
- Track portfolio vs. VOO benchmark

---

## Commands

| Command | Pipeline | Devil's Gate? | Output |
|---------|----------|---------------|--------|
| `report` | Full 4-phase pipeline | YES | HTML |
| `report pdf` | Full 4-phase pipeline | YES | PDF |
| `analyze [TICKER]` | Full pipeline, single stock | YES | HTML |
| `flash` | Research + Strategy (quick) | NO | Chat |
| `score` | Performance scoring | NO | Scorecard |
| `screen` | S&P 500 stock screener | NO | Candidates |
| `alerts` | Check alert conditions | NO | Alert status |
| `rebalance` | Portfolio drift check | NO | Chat |
| `sync [file]` | IBKR CSV import | NO | Portfolio update |

---

## Investor Profile

**Read from `portfolio.md` Profile section.** No hardcoded values in system files.
The investor's name, location, broker, experience level, risk tolerance, and preferences are all defined in portfolio.md and read dynamically at runtime.
