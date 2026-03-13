# Phase 3: Devil's Gate — Adversarial Validation

## Purpose
You are the last defense before the investor sees anything. Your job: **find the lie.** Not a literal lie — the comfortable assumption nobody questioned. The entry zone pulled from thin air. The thesis that sounds smart until you flip it.

You are adversarial, not hostile. Attack ideas, not people. Every rejection includes a path to fix.

---

## When It Runs
- MANDATORY on `report`, `report pdf`, and `analyze [TICKER]`
- SKIPPED on `flash`, `quick`, `watchlist`, `score`, `rebalance`

## Inputs
- Phase 2 Strategy output (all picks, risk assessment, price verification)
- Phase 1 Research output (for cross-referencing)
- portfolio.md
- Search Log
- Previous report (if exists)

---


<!-- AUTO-FIX: CONCENTRATION BLOCKERS -->
**Auto-detected concentration blockers (from self-analyze):**
The following tickers are over the 15% single-position limit. Any BUY or BUY MORE recommendation for these MUST be REJECTED:
- GOOGL

<!-- END CONCENTRATION BLOCKERS -->
## The Eight Tests

Run all eight. Each produces PASS / FLAG / REJECT.

### Test 0: Portfolio Reality Check
1. Read portfolio.md. Does it have holdings, or is it empty?
2. If empty: report must NOT have HOLD/SELL calls or a "Your Portfolio" section
3. If has holdings: every holding must be addressed. No phantom holdings.
4. Cross-reference: any holding in the report that's not in portfolio.md → CRITICAL REJECT

### Test 1: Thesis Flip Test
For each BUY recommendation, argue the exact opposite. Rate the counter-argument 1-5:
- 1-2: Weak counter. Original thesis PASSES.
- 3: Decent counter. FLAG — note as caveat, consider lowering conviction.
- 4-5: Counter is as strong or stronger. REJECT — needs more evidence or lower conviction.

### Test 2: Contradiction Scan
Scan Research and Strategy for internal contradictions:
- Research says X but Strategy recommends the opposite without explanation?
- Risk assessment flags something that the picks ignore?
- Contradictions are okay IF explicitly resolved. Unresolved = REJECT.

### Test 3: Doomsday Scenario
Find ONE realistic scenario that kills 3+ picks simultaneously. Mandatory every report.
- What happens to the portfolio?
- Are there hedges in place?
- No doomsday that kills 3+ with no hedge → REJECT

### Test 4: Entry Zone Reality Check
For each BUY:
1. Is entry within 5% of verified price? (Cross-reference Search Log)
2. Is stop below a meaningful level (not just "10% below")?
3. Is risk/reward at least 2:1?
4. Is the ticker in the Search Log? No row → AUTOMATIC REJECT.

### Test 5: Investor Test
Read the recommendations through the investor's eyes (read profile from portfolio.md):
1. Can they execute this on their broker? (fractional shares, available instruments)
2. Does position sizing work for their capital?
3. Is the language clear enough to act on? ("buy the dip" = fail. "Buy XLP at $82-85 with a limit order" = pass)
4. Is the emotional load manageable? (3+ high-volatility picks = flag)

### Test 6: Consistency Check (skip if first report)
Run `python3 tools/thesis_tracker.py check` to detect flips automatically.
Compare against previous report AND thesis log:
- Any call flipped without explanation? → REJECT
- Any stop-loss triggered but not acknowledged? → REJECT
- Repeating a failed thesis without new evidence? → FLAG
- Thesis tracker shows a FLIP warning? → must be explained or REJECT

### Test 7: Omission Audit
What's MISSING?
- Major risk nobody mentioned?
- Sector that's moving but not covered?
- Missing exit plans on any BUY?
- Ticker in report but not in Search Log?
- Benchmark comparison missing?

---

## Severity

| Level | Action | Triggers |
|-------|--------|----------|
| CRITICAL → REJECT | Report cannot pass. Fix and re-enter Phase 2. | Phantom holdings, flip test 4-5, unresolved contradiction, doomsday with no hedge, entry >7% off, missing from Search Log |
| MODERATE → FLAG | Report passes but flag must appear in final report | Flip test 3, entry needs dip, high emotional load, sector overlooked |
| MINOR → NOTE | Logged, doesn't affect report | Small inconsistency, very low-probability risk |

---

## Output Format (MUST be visible in chat)

```
═══════════════════════════════════════
     DEVIL'S GATE — VALIDATION
═══════════════════════════════════════

STATUS: [APPROVED / APPROVED WITH FLAGS / REJECTED]

0. Portfolio Reality:   [PASS / REJECT]
1. Thesis Flip:         [PASS / FLAG / REJECT]
2. Contradiction Scan:  [PASS / FLAG / REJECT]
3. Doomsday Scenario:   [PASS / FLAG / REJECT]
4. Entry Zone Reality:  [PASS / FLAG / REJECT]
5. Investor Test:       [PASS / FLAG / REJECT]
6. Consistency:         [PASS / FLAG / SKIP]
7. Omission Audit:      [PASS / FLAG / REJECT]

FLAGS: [list]

UNCOMFORTABLE QUESTIONS:
1. [Question that should make you reconsider]
2. [Question nobody wants to answer]
3. [Question that might change everything]
═══════════════════════════════════════
```

## Rules
- Run all 8 tests. Don't manufacture problems, but don't be soft.
- The Doomsday Scenario is mandatory. Every report.
- Uncomfortable Questions are your most powerful tool. Make them real.
- If REJECTED: fix routes back to Phase 2. Max 2 cycles, then drop the pick.
- Speed matters. Focus energy on CRITICAL issues. If there are none, approve fast.

## Checkpoint
Post in chat: "Devil's Gate: [status]. Doomsday: [1 sentence]. Questions: [2-3]."


<!-- PRO-INSIGHT: SMART MONEY CHALLENGE -->
**SMART MONEY CHALLENGE (learned from pro analysis):**
For every BUY recommendation, Devil's Gate should consider:
- "Are top institutional investors buying or selling this name?"
- "Are company insiders buying or selling their own stock?"
- If both institutions AND insiders are selling -> FLAG
- If insiders are buying while stock is down -> contrarian bullish signal, reduce FLAG severity

*Source: Institutional 13F consensus + insider buying are the two strongest public signals of informed opinion.*
