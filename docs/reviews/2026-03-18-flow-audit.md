# Flow & Architecture Audit — 2026-03-18

## Overall: 6.5/10

Core report pipeline works and produces Grade A output. But the plumbing between components has real gaps — stale data paths, broken automation promises, and documentation that contradicts itself.

---

## Critical Flow Gaps

### 1. `data_fetcher.py` reads portfolio.md, not DB
- **data_fetcher.py:104-160** — `read_portfolio()` parses portfolio.md for tickers
- Every preflight run may operate on wrong ticker list if DB was updated but portfolio.md wasn't exported
- This is the #1 architecture violation — the primary data tool ignores the "DB is master" rule

### 2. `post-trade` flow doesn't update holdings DB
- **vault.py:1370-1416** — Logs trade but never calls `upsert_holding`
- User runs `vault post-trade XOM 156 5`, trade is logged, but XOM is NOT added to portfolio
- Must separately run `vault portfolio add` — defeats the purpose of the flow

### 3. Portfolio mutations don't auto-export portfolio.md
- **vault.py:168, 176, 196, 204** — `add/update/remove/cash` never call `export_portfolio_md()`
- CLAUDE.md claims "auto-synced from DB" but it's not
- Creates drift between DB (truth) and portfolio.md (what data_fetcher reads)

### 4. `portfolio_dashboard()` has zero TTL on price cache
- **db.py:1665** — Joins on `max(date)` with no age check
- Will silently show week-old prices after a holiday
- COALESCE fallback to cost_basis masks missing data (shows 0% P&L)

### 5. No sell flow
- Buying has a 4-step guided flow (`buy-flow`)
- Selling has nothing — no `sell-flow` or `exit-flow`
- User must manually: remove from DB, close trade record, capture P&L, run drift check

---

## Documentation Contradictions

### 6. "Read from portfolio.md" vs "DB is master"
- **00_system.md:4** says profile "defined in portfolio.md"
- **02_strategy.md:12** lists "portfolio.md" as input
- **03_devils_gate.md:18,73** says "read profile from portfolio.md"
- **04_report.md:4** says "read name and experience from portfolio.md"
- All contradict the DB-first rule stated in 00_system.md:62

### 7. Entry zone rules duplicated in 3 files
- 00_system.md:160-163, 02_strategy.md:97-100, 03_devils_gate.md:67
- Same thresholds, different wording — maintenance nightmare

### 8. Sizing rules scattered across 3 files
- 00_system.md:129-158, 02_strategy.md:106-109, 05_position_mgmt.md:170-178
- Conviction sizing condition unclear: 00_system.md says "IF DG passed," 05_position_mgmt.md says unconditional

### 9. Cash minimum ambiguous
- 02_strategy.md:121 says "at least 10%"
- 00_system.md:136 says "Moderate: 15-20%"
- Both true but confusing — need explicit "hard floor vs target range"

---

## Automation Gaps

### 10. `report`/`flash`/`analyze` are invisible Claude commands
- Documented as primary commands in CLAUDE.md:7-11
- Don't exist in vault.py — user gets "Unknown command"
- No indication these are conversational, not CLI

### 11. `help` output missing 7+ commands
- `status`, `portfolio`, `news-impact`, `plan`, `project`, all aliases missing
- User can't discover what's available

### 12. Silent fallthrough on malformed arguments
- `vault portfolio add XOM 5` (missing cost) silently shows portfolio table
- No error message — user thinks command worked

### 13. Concentration blockers are stale static text
- 03_devils_gate.md hardcodes "GOOGL" as blocked
- After $4,500 deployment, GOOGL drops to 6.7% — blocker is wrong
- Should be runtime check via `db.risk_dashboard()`, not static patch

---

## Data Pipeline Issues

### 14. Price fetch never checks cache
- `fetch_quote()` and `fetch_technicals()` always hit yfinance
- Causes 100+ redundant API calls per preflight
- Same sector ETFs fetched twice (main loop + breadth check)

### 15. Cache TTL inconsistencies
- alerts.py: 15-minute max_age
- vault.py size: 1440-minute (24h) max_age
- portfolio_dashboard: no max_age at all
- Same price_cache table, wildly different freshness expectations

### 16. News cache returns stale data after failed fetch
- news.py:290 reads with max_age=9999 minutes after a failed API call
- Returns week-old articles without any staleness indicator

---

## Missing Flows & Guidance

### 17. No all-picks-rejected escape hatch
- Devil's Gate can reject all picks. No guidance on what happens next.
- Suggestion: "Produce HOLD-only report explaining why no BUYs met the bar"

### 18. No earnings-week protocol
- System says "no buying 1-3 days before earnings" but no guidance for existing holdings reporting earnings

### 19. No post-event re-evaluation protocol
- Reports build deployment plans around events (FOMC, ceasefire)
- No system command for "event happened, re-evaluate"

### 20. No cumulative accuracy in reports
- scorer.py tracks accuracy but it's not included in the report template
- Suggestion: "BUY accuracy since inception: X/Y (Z%)" one-liner

### 21. Stress test table produced in Phase 2 but dropped from Phase 4
- Bull/base/bear scenarios calculated but have no slot in report template
- Analysis done then discarded

### 22. buy-flow missing correlation and insider checks
- research-flow has both, buy-flow has neither
- User could buy XOM while holding CVX with no correlation warning

### 23. review flow missing alerts, backtest, report comparison
- End-of-week review doesn't surface triggered alerts
- Doesn't compare against prior week's report

---

## Recommended Fix Priority

### Week 1: Architecture fixes
1. Make `data_fetcher.py` read from DB instead of portfolio.md
2. Auto-export portfolio.md after every DB mutation
3. Add TTL check to `portfolio_dashboard()` price join
4. Make `post-trade` auto-update holdings

### Week 2: Documentation cleanup
5. Replace all "read from portfolio.md" with "read from DB" in system files
6. Consolidate entry zone rules to single source
7. Consolidate sizing rules to single source
8. Make concentration blockers runtime checks

### Week 3: Missing flows
9. Add sell-flow
10. Add post-report automation command
11. Add alerts to start and review flows
12. Add correlation check to buy-flow

### Week 4: Data pipeline
13. Add cache-check to fetch_quote/fetch_technicals
14. Standardize TTLs across tools
15. Fix help output completeness
