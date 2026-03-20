# Phase 2: Strategy

## Purpose
Take the Research output and produce actionable calls: what to hold, what to buy, what to avoid, and how much. This phase answers: **What should the investor do?**

## Inputs
- Phase 1 Research output
- `tools/data_fetcher.py` output (verified prices, moving averages, RSI, breadth for all relevant tickers)
- `tools/screener.py` output (ranked candidates with RSI, DMA crossovers, volume signals)
- Active improvements from vault.db (self-analysis feedback — concentration limits, bias corrections, past mistakes)
- `vault.db` (current holdings, cash, risk tolerance, monthly investment — via `vault portfolio`)
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
- A past BUY recommendation does NOT mean the investor bought it. Check DB holdings (`vault portfolio`).

Include benchmark comparison:
```
Portfolio since inception: +X.X%
VOO over same period: +X.X%
```

### 2. Portfolio Calls (only if DB has holdings)
For each holding:
| Stock | Shares | Cost | Current | P&L | Action | Reasoning |
- Actions: HOLD / BUY MORE / TRIM / SELL
- Every SELL must have urgency: NOW vs. "when convenient"
- Check position drift (per 05_position_mgmt.md rebalance rules)
- **Sector rotation check:** If a held sector ETF has dropped to bottom 3 in the sector ranking for 2+ consecutive reports AND the thesis has weakened, FLAG for rotation to a top-3 sector ETF


<!-- AUTO-FIX: SELL CHECK (updated 2026-03-20) -->
**MANDATORY SELL/TRIM EVALUATION:**
**BEFORE writing any new BUY recommendations, you MUST:**
1. Evaluate EVERY holding against its stop-loss — has it been hit? If yes → SELL, no exceptions
2. Evaluate EVERY holding against its original thesis — has the thesis broken? If yes → SELL
3. Evaluate EVERY holding for concentration — is it >15% of TOTAL capital (see 00_system.md)? If yes → TRIM
4. Evaluate EVERY holding for profit-taking triggers per 05_position_mgmt.md (+30%, +50%, +100%)
5. Output a SELL/TRIM table BEFORE the BUY table. If no sells needed, state "All holdings reviewed — no triggers" with 1-line justification per position

**Context guard:** A new portfolio (<30 days old, <6 positions, <50% capital deployed) with 0 SELLs is NORMAL — it's in deployment phase, not exhibiting buy bias. The sell evaluation still runs, but "no sells needed" is the expected outcome early on. Do NOT force a SELL just to balance statistics. Only SELL when a stop is hit, a thesis breaks, or concentration demands it.

**Oversold override:** If a holding has RSI <25 (deeply oversold), do NOT recommend SELL unless the stop-loss has been hit. Selling at extreme oversold levels is panic selling — the opposite of disciplined investing.

**If you skip this evaluation entirely, Devil's Gate Test 7 (Omission Audit) MUST reject the report.**

<!-- END SELL CHECK -->

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


<!-- AUTO-FIX: REPETITION GUARD (updated 2026-03-19) -->
**REPETITION GUARD (auto-added by self-analyze):**
Before recommending any BUY, check vault.db watchlist for prior recommendations of the same ticker:
```python
from db import VaultDB
with VaultDB() as db:
    # Check if ticker was already recommended
    prior = db.conn.execute("SELECT date, ticker FROM watchlist_picks WHERE ticker=? ORDER BY date DESC", (ticker,)).fetchall()
```
Rules:
- If ticker was recommended 2+ times AND investor already holds it → switch to HOLD/TRIM analysis. No more BUY calls.
- If ticker was recommended but NOT bought → it can be recommended again ONLY with a new catalyst (cite the new evidence explicitly)
- If repeating a recommendation, state: "Previously recommended on [date]. New catalyst: [what changed]."

Known repeat offenders (as of 2026-03-19): GOOGL (3x — already held, over-concentrated), GLD (3x — already held, bearish smart money)

<!-- END REPETITION GUARD -->

### 5. New BUY Recommendations (3-5 picks max)

<!-- AUTO-FIX: BALANCED MIX MANDATE (added 2026-03-20) -->
**BALANCED RECOMMENDATIONS (auto-added after investor correction):**
Do NOT default to 100% defensive or 100% growth. Every report's BUY list must consider candidates from ALL categories:
- **Growth** — check vault.db learnings for `[STRONG]` smart money signals (e.g., AMZN had 10 funds + ARK + 3 gurus and was excluded)
- **Defensive** — staples, utilities, healthcare in contraction
- **War/macro plays** — energy, defense if geopolitical thesis active
- **Hedge** — gold, bonds, inverse if risk-off
- **Broad market** — VOO, SPY, SPLG, VTI, QQQ. If S&P RSI <35, a broad index ETF MUST be in the recommendation list or explicitly excluded. Buying the oversold market is often the simplest, highest-conviction play — instant diversification, no thesis to break. Don't get so focused on individual picks that you miss the obvious.

If a candidate has the strongest smart money signal in the database, it MUST appear in recommendations or have an explicit exclusion reason. Regime labels (risk-off) adjust SIZING and CASH reserves, not which categories to consider. The investor should never have to ask "why not [obvious strong candidate]?"
<!-- END BALANCED MIX MANDATE -->

**Head-to-head rule:** For every BUY, name the top alternative in the same sector/theme and state in one sentence why your pick is better. E.g., "XOM over CVX: stronger free cash flow yield." "VOO over SPY: lower expense ratio." This prevents lazy recommendations where the first name that comes to mind wins.

**Candidate sourcing:** Use ALL available data — screener output (individual stocks + ETFs), smart money learnings ([STRONG] signals), sector rankings, and forward P/E comparisons. Screener flags provide quantitative support but are not sufficient alone — every pick still requires a fundamental thesis.

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

**Entry zone rules:** Apply entry zone rules from 00_system.md.
- Stop < entry < target (always)
- Risk/reward minimum 2:1 for all picks (`***` and `**`), 1.5:1 acceptable for `*` speculative only
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

**Decision framework (based on DB risk tolerance setting + current conditions):**
- Read target cash range from 00_system.md Position Sizing table (Conservative: 25-30%, Moderate: 15-20%, Aggressive: 5-10%)
- **Increase cash** toward the high end if: VIX > 25, major event within 7 days (FOMC, earnings), market down >5% in 2 weeks
- **Decrease cash** toward the low end if: VIX < 15, strong breadth (>70% above 200 DMA), no major events
- Always maintain at least 10% cash reserve per 05_position_mgmt.md
- Justify the specific % chosen in the report

<!-- BLIND SPOT FIX (2026-03-20): Cash earning 0% when short-term yields are 4%+ is wealth destruction -->
**Cash alternative consideration:** If cash allocation is >20% AND short-term Treasury yields are >4%, recommend parking cash in ultra-short bond ETFs instead of uninvested cash:
- **SHY** (iShares 1-3 Year Treasury, ~4.5% yield, minimal price risk)
- **BIL** (SPDR 1-3 Month T-Bills, ~4.8% yield, near-zero price risk)
This keeps the cash "dry powder" function (can sell in 1 day to deploy) while earning yield. Note in the report: "Cash reserve of $X could earn ~$Y/year in SHY/BIL vs $0 uninvested."

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
