# Phase 2: Strategy

## Purpose
Take the Research output and produce actionable calls: what to hold, what to buy, what to avoid, and how much. This phase answers: **What should the investor do?**

## Inputs
- Phase 1 Research output
- `tools/data_fetcher.py` output (verified prices, moving averages, RSI, breadth for all relevant tickers)
- `tools/screener.py` output (ranked candidates with RSI, DMA crossovers, volume signals)
- Active improvements from vault.db (self-analysis feedback — concentration limits, bias corrections, past mistakes)
- `portfolio.md` (current holdings, cash, risk tolerance, monthly investment)
- Previous report (for performance review and consistency)
- `system/05_position_mgmt.md` (rules for sizing, scaling, stops)
- Smart money signals from vault.db (ARK trades, guru consensus, 13F, insider buys)

**Before making any recommendation, check active improvements in vault.db for:**
```python
from db import VaultDB
with VaultDB() as db:
    print(db.get_active_improvements_summary())
```
- Positions that are already over-concentrated (do NOT add more)
- Bias patterns to correct (e.g., if buy bias detected, actively look for SELL/TRIM candidates)
- Process gaps to fix (e.g., missing stop-losses on prior reports)
- What worked and what didn't — double down on proven logic, question failed approaches

---

## What You Produce

### 1. Performance Review (if previous report exists)
For every active call from the last report:
| Pick | Rec. Price | Current | P&L | Thesis Intact? |
- Be honest. If a call was wrong, say why.
- A past BUY recommendation does NOT mean the investor bought it. Check portfolio.md.

Include benchmark comparison:
```
Portfolio since inception: +X.X%
VOO over same period: +X.X%
```

### 2. Portfolio Calls (only if portfolio.md has holdings)
For each holding:
| Stock | Shares | Cost | Current | P&L | Action | Reasoning |
- Actions: HOLD / BUY MORE / TRIM / SELL
- Every SELL must have urgency: NOW vs. "when convenient"
- Check position drift (per 05_position_mgmt.md rebalance rules)


<!-- AUTO-FIX: SELL CHECK -->
**SELL/TRIM CHECK (auto-added by self-analyze):**
Buy bias detected — system recommends buys but rarely sells. For EVERY holding, explicitly evaluate: is there a reason to SELL or TRIM? If a stop-loss has been hit, the thesis has broken, or the position is over-concentrated, recommend SELL/TRIM before any new BUYs.

### 3. Risk Assessment
Run `python3 tools/correlation.py` to check portfolio correlation before writing this section.

One paragraph. Answer:
- What's the single biggest risk right now?
- How does it affect the portfolio specifically?
- Is the portfolio positioned to survive the worst case?
- Are holdings too correlated? (flag any pairs >0.7)

Then a stress test table:
| Scenario | Probability | Portfolio Impact |
Three scenarios: bull, base, bear. With specific trigger for each.

### 4. Consensus Challenges
**You MUST find at least one thing to challenge.** If everything looks perfect, you're not looking hard enough.
- Challenge your own Research phase: where might the macro read be wrong?
- Challenge your own picks: what's the strongest counter-argument?
- Flag any correlation risk between positions


<!-- AUTO-FIX: REPETITION GUARD -->
**REPETITION GUARD (auto-added by self-analyze):**
Detected repeated recommendations without new evidence: GOOGL (2x), GLD (2x).
If a ticker was already recommended AND the investor bought it, switch to HOLD analysis. Only recommend again with a NEW catalyst.

<!-- END REPETITION GUARD -->
### 5. New BUY Recommendations (3-5 picks max)
**Candidate sourcing:** If screener output is available, use it as a starting point. Screener flags (RSI extremes, golden crosses, volume spikes) provide quantitative support but are not sufficient alone — every pick still requires a fundamental thesis.

For each pick:

| Field | Required |
|-------|----------|
| Ticker + name | What it is (explain if not obvious) |
| Conviction | `***` / `**` / `*` |
| Entry range | Specific price range based on verified current price |
| Stop-loss | Below meaningful level, not just "10% below" |
| Target | Above meaningful level with timeframe |
| Why (1-2 sentences) | The thesis |
| Size | Dollar amount and % of available capital |
| What changes this call | Specific trigger to exit |

**Entry zone rules:**
- Must be within 5% of verified price (unless you're setting a limit order with explicit justification)
- Stop < entry < target (always)
- Risk/reward minimum 2:1 for `**` picks, 1.5:1 for `***` picks
- Use tools/data_fetcher.py technicals (50/200 DMA, RSI) for level-setting
- Do NOT claim to see "chart patterns" — you can't see charts

**Position sizing rules (from system/05_position_mgmt.md):**
- Follow scaling rules: don't deploy full position at once
- Respect sector caps (no sector >35%)
- Respect single-stock caps (no position >15%)

### 6. AVOID List
Sectors or stocks to stay away from. One sentence each with specific reason.

### 7. Cash Allocation
How much to keep in cash from available capital, and why.

### 8. Thesis Change Triggers
3-5 specific, measurable conditions that would flip your calls. Format:
- "If [specific condition] → [specific action]"

### 9. Alert Conditions
2-3 thresholds to watch between reports. If triggered, type `flash`.

### 10. Price Verification Sign-Off
```
PRICE VERIFICATION:
[TICKER] — Verified: $XXX | Entry: $XXX-$XXX | Gap: X% | PASS
...
ALL PRICES VERIFIED
```

---



<!-- PRO-INSIGHT: SMART MONEY VALIDATION -->
**SMART MONEY VALIDATION (learned from pro analysis):**
For every BUY recommendation, run `smart_money.py check TICKER` and consider:
- **13F consensus**: If 3+ top institutional funds hold it -> thesis support (note it)
- **Guru holdings**: If held by Buffett/Ackman/Klarman/etc -> thesis support. If they're reducing -> red flag
- **ARK trades**: If ARK is accumulating -> growth/innovation signal. If distributing -> caution
- **Insider buying**: If company insiders are buying their own stock -> strong bullish signal
- If institutions, gurus, AND insiders are all selling -> FLAG (must explain why you disagree)
- This is a VALIDATOR, not a GENERATOR — never buy just because a fund holds it

*Sources: Harvard (2022) — insider buying outperforms by 4-8% annually. 13F + guru + ARK consensus provides multi-source thesis validation.*

## Rules
- Every pick needs: thesis + entry + stop + target + "what changes my mind"
- Address every risk flag from your own assessment
- Never recommend more than 5 new positions per report
- For portfolios under $25K: prefer ETFs over individual stocks (diversification per dollar)
- Check earnings calendar for every ticker. Flag anything within 7 days.
- Be honest about uncertainty. "I think" is fine. False precision isn't.
- If the best action is "do nothing and wait," say that. Not every report needs new BUYs.

## Checkpoint
Post in chat: "Price Verification: ALL PASS. Challenges: [list]. Cash target: X%."
