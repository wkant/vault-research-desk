# Vault Research Desk — System Rules

## What This Is
A personal investment research system. It produces weekly market reports with BUY/HOLD/SELL calls, risk assessment, and behavioral coaching. The investor's profile, broker, risk tolerance, and monthly investment are defined in `portfolio.md` — the system reads them from there. Nothing is hardcoded.

---

## Commands

| Command | What Runs | Output |
|---------|-----------|--------|
| `report` | Full pipeline: Data → Research → Strategy → Devil's Gate → Report | HTML report |
| `report pdf` | Full pipeline + PDF generation | PDF + Markdown |
| `flash` | Quick update: Research + Strategy (no Devil's Gate) | Short alert |
| `analyze [TICKER]` | Full pipeline focused on one stock | Single-stock analysis |
| `score` | Performance tracking | Scorecard |
| `rebalance` | Portfolio drift check | Rebalance instructions |
| `screen` | Run tools/screener.py — S&P 500 scan | Ranked candidate list |
| `alerts` | Run tools/alerts.py — check alert thresholds | Alert status |
| `sync [file]` | Run tools/ibkr_sync.py — IBKR CSV import | Portfolio preview/update |
| `self-analyze` | Run tools/self_analyze.py — system self-review | Results in vault.db |
| `learn-from-pros` | Run tools/learn_from_pros.py — fetch smart money data, cross-reference portfolio, save learnings | Results in vault.db learnings table |
| `morning` | Run tools/db.py morning — full overview: portfolio, theses, watchlist, learnings, issues | Summary in chat |

---

## Execution Flow

```
PHASE 0: Data Collection (run `vault preflight` to automate mandatory steps)
    tools/data_fetcher.py — prices, technicals, breadth, news, auto-alerts (mandatory)
    tools/screener.py --sample 50 — quick candidate scan (mandatory)
    tools/correlation.py — portfolio correlation check (mandatory)
    tools/thesis_tracker.py check — review active theses (mandatory)
    tools/insider_check.py --portfolio — insider activity for holdings (if new picks in Phase 2, check those too)
    tools/news.py --portfolio — cached news for holdings (auto-run by data_fetcher if FINNHUB_API_KEY set)
    tools/smart_money.py ark — ARK daily trades (what is Cathie Wood buying/selling?)
    tools/smart_money.py gurus — superinvestor holdings from Dataroma
    ↓
PHASE 1: Research (01_research.md — macro + sectors + sentiment)
    ↓
PHASE 2: Strategy (02_strategy.md — picks + risk + sizing)
    ↓
PHASE 3: Devil's Gate (03_devils_gate.md — adversarial validation)
    ↓         ├── APPROVED → Report
    ↓         ├── FLAGS → Report (with caveats)
    ↓         └── REJECTED → fix, re-enter Phase 2
    ↓
PHASE 4: Report (04_report.md — final output + Gut Check)
```

### Visible Output Rule
Every phase posts its output in chat BEFORE the next phase starts. If it's not visible, it didn't happen.

### `flash` Exception
Flash skips Devil's Gate. Speed over perfection in emergencies.

---

## Portfolio — Single Source of Truth

**`portfolio.md` is the ONLY source of truth for the investor's holdings, settings, and profile.**

- All investor-specific data (name, broker, risk tolerance, monthly investment, holdings) lives in portfolio.md
- If portfolio.md has holdings → report includes HOLD/SELL calls, P&L, rebalance checks
- If portfolio.md is empty → ALL recommendations are new BUYs, no "Your Portfolio" section
- NEVER use memory, chat history, or past reports to determine holdings
- NEVER assume the investor bought something because a previous report recommended it
- The system NEVER modifies portfolio.md — only the investor updates it (unless explicitly asked)

**Why:** The system once built an entire report around 6 stocks the investor didn't own. The portfolio file was empty. Every HOLD call was fiction. This rule prevents that from ever happening again.

---

## Price Verification Protocol

Every price in the report must be verified. No exceptions.

### How to Verify
1. Run `tools/data_fetcher.py` first — it returns verified quotes for all tickers
2. If tools/data_fetcher.py fails for a ticker, run a web search: "[TICKER] stock price today [date]"
3. Record every verified price in the Search Log

### Search Log (posted in chat before Devil's Gate)
Generate using: `vault search-log [EXTRA_TICKERS]` or `db.generate_search_log(tickers)`.
```
═══ SEARCH LOG ═══
| # | Ticker | Verified Price | Source | Date |
|---|--------|---------------|--------|------|
```

- Every ticker in the report MUST have a row
- If a ticker is missing from the Search Log, it CANNOT appear in the report
- **Include the Search Log in the final report** (after "Changes Since Last Report", before "Your Portfolio")
- Any entry zone >7% below verified price without justification → REJECT (see Entry Zone Rules below)

---

## Data Honesty Rule

**Only report data you can actually verify.** This means:

CAN verify (use these):
- Stock/ETF prices (yfinance or web search)
- VIX level (yfinance)
- Oil, gold, dollar index (yfinance or web search)
- CPI, NFP, unemployment (web search for latest release)
- Moving averages, RSI (yfinance/tools/data_fetcher.py calculates these)
- Market breadth approximation (tools/data_fetcher.py samples ~55 stocks)
- Screener signals: RSI extremes, DMA crossovers, volume (tools/screener.py)
- News headlines and summaries (tools/news.py via Finnhub + Marketaux, cached in vault.db)
- News sentiment scores per ticker (Marketaux, cached in vault.db)
- ARK Invest daily trades (tools/smart_money.py ark, cached in vault.db)
- Superinvestor holdings (tools/smart_money.py gurus via Dataroma, cached in vault.db)
- Earnings dates (yfinance)

CANNOT verify (don't fabricate):
- Put/call ratios (unless found in a specific source — cite it)
- Fund flows / dark pool data (institutional-only)
- CNN Fear & Greed exact number (web search if available, otherwise skip)
- Chart patterns (LLMs can't see charts)

**If you can't verify it, say "not available" instead of estimating.**

---

## Position Sizing Framework

Based on portfolio.md risk tolerance setting:

| Risk Level | Stocks | Cash | Max Speculative |
|-----------|--------|------|-----------------|
| Conservative | 50% | 25-30% | 3% |
| Moderate | 65-75% | 15-20% | 5% |
| Aggressive | 80%+ | 5-10% | 10% |

### Hard Limits (non-negotiable)
- No single stock >15% of total portfolio (see conviction exception below)

<!-- PRO-INSIGHT: CONVICTION SIZING -->
**Conviction-weighted exception (learned from pro analysis):**
- `***` HIGH conviction picks may go up to 18% (override 15% limit) IF thesis passed all Devil's Gate tests
- This is the Buffett rule: concentrate when conviction is highest

- No single sector >35% of total portfolio
- No two BUY picks with >0.8 correlation without justification
- No buying a stock 1-3 days before earnings (unless flagged as earnings play with reduced size)

### Sizing Rule Priority (when frameworks conflict)
Multiple sizing rules exist across system files. Apply in this order — first applicable rule wins:
1. **Hard limits** (above) — always enforced, never overridden
2. **Circuit breaker** (05_position_mgmt.md) — if portfolio drawdown >15%, raise cash first
3. **Conviction-weighted sizing** (this file) — `***` up to 18%, `**` up to 12%, `*` up to 7%
4. **Risk tolerance allocation** (table above) — sets overall stock/cash mix
5. **Core/Satellite structure** (05_position_mgmt.md) — shapes position roles
6. **Kelly Criterion** (05_position_mgmt.md) — sanity check only, after 20+ trades

### Entry Zone Rules (unified)
- **Target**: Entry within 5% of verified price
- **Flag**: Entry 5-7% below verified price — requires explicit justification (limit order, expected pullback)
- **Reject**: Entry >7% below verified price — auto-reject unless extraordinary circumstances documented

---

## Conviction Levels
- `***` HIGH: 70%+ confident. Multiple signals align. Strong data.
- `**` MEDIUM: 50-70% confident. Good thesis, some uncertainty.
- `*` LOW: Below 50%. Speculative/contrarian. Small position only.

Use asterisks only — never unicode stars (they break in PDF).

---

## Report Output

### HTML (default — `report`)
Generate Markdown report first, then convert to HTML:
```bash
python3 tools/html_report.py reports/report_YYYY-MM-DD.md
```
- Zero dependencies — pure Python, no installs needed
- Dark theme with print-friendly styles (Ctrl+P looks good)
- Auto-highlights BUY/SELL/HOLD actions and P&L colors
- Output: `reports/report_YYYY-MM-DD.html`

### PDF (on demand — `report pdf`)
Generate Markdown report first, then convert to PDF using ReportLab.

Key rules (prevent common layout bugs):
- ALWAYS use Paragraph objects in table cells (never raw strings)
- Column widths must sum to content width (page width minus margins)
- Title: 22pt with leading=26 (prevents subtitle overlap)
- Body: 9pt, leading=12
- Table cells: 8.5pt, leading=11
- Margins: top/bottom 0.5in, left/right 0.7in
- Use `***` `**` `*` for confidence, never unicode stars
- Use `--` for dashes, `&amp;` for ampersands in Paragraph text
- Visually verify first page after generation (pdftoppm or sips)
- Do NOT re-render to hit a page count. Analysis quality > layout polish.
- Requires: `pip3 install reportlab`

---

## Benchmark Tracking

Every report must include a VOO (S&P 500 ETF) comparison:
```
Your portfolio since inception: +X.X%
VOO over same period: +X.X%
```

This is how the investor knows if the system is adding value over simple index investing.
