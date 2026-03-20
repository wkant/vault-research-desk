# Position Management Rules

## Purpose
Mechanical rules for managing positions over time. These remove emotion from decisions that should be systematic.

---

## Scaling In

**Never deploy a full position at once.** Split every new BUY into tranches:

| Portfolio Size | Scaling Rule |
|---------------|-------------|
| Under $10K | 2 tranches over 2 weeks (50/50) |
| $10K-$50K | 3 tranches over 3 weeks (40/30/30) |
| $50K+ | 3-4 tranches over 4 weeks |

**Why:** Markets are volatile. Splitting buys means your average entry is smoother. If the stock dips after tranche 1, tranche 2 gets a better price. If it rips up, you still have skin in the game.

**Exception:** If a flash alert creates a clear dip-buy opportunity with VIX >30, deploy up to 2 tranches at once.

---

## Stop-Loss Management

### Initial Stops
Set at time of purchase. Non-negotiable.

**Priority:** Use a meaningful technical level (support, 50/200 DMA, 52-week low) that falls within the conviction range below. If no meaningful level exists within range, use the percentage rule as fallback.

| Conviction | Stop Distance | Example | Rationale |
|-----------|--------------|---------|-----------|
| `***` HIGH | 8-10% below entry | Entry $100, stop $90-92 | Strongest thesis → tighter stop is safe |
| `**` MEDIUM | 10-12% below entry | Entry $100, stop $88-90 | Standard room to breathe |
| `*` LOW | 12-15% below entry | Entry $100, stop $85-88 | Speculative/contrarian needs room — volatile by nature |

<!-- LOGIC FIX (2026-03-20): Inverted stop distances. Old logic gave * tightest stops (7-8%), but speculative picks are the most volatile and get stopped out before thesis can play out. Now * gets widest stops to compensate for volatility. *** gets tightest because high-conviction thesis should hold up. -->

### Trailing Stops
After a position moves in your favor:

| Gain from Entry | New Stop Level |
|----------------|---------------|
| +10% | Move stop to breakeven (entry price) |
| +20% | Move stop to +10% above entry |
| +30% | Move stop to +20% above entry |

**Update trailing stops in vault.db (via `vault portfolio update`) or at each report.**

### When a Stop Triggers
- The stop triggered → the position is SOLD. No "let me hold a little longer."
- The next report must acknowledge the stop hit and explain what happened
- Log it in vault.db (auto-tracked by the system)
- Wait at least 1 week before re-entering the same name (prevent revenge trading)

---

## Profit-Taking

| Gain | Action |
|------|--------|
| +30% | Trim 25% of the position. Let the rest ride with trailing stop. |
| +50% | Trim another 25% (now at 50% of original). Trailing stop on remainder. |
| +100% | Sell half. The remainder is "house money" — ride with trailing stop. |

**Exception:** If the thesis is stronger than at entry (e.g., earnings blowout, new catalyst), you may delay trimming by one tier. But note this explicitly in the report.

---

## Rebalancing

### When to Rebalance
- **Quarterly:** Every 3 months, review allocation vs. targets
- **Drift trigger:** Any single position >5% away from its **conviction-adjusted target weight** (not equal-weight)
- **Sector trigger:** Any sector >35% of total capital (portfolio + cash)

<!-- LOGIC FIX (2026-03-20): Drift trigger must compare against conviction-adjusted targets, not equal-weight. A *** position at 18% is NOT drifting if its target is 15-18%. Set targets at purchase time: *** = 15-18%, ** = 10-12%, * = 5-7%. The 5% drift applies relative to THESE targets. -->

### How to Rebalance
1. Identify overweight positions (trim these)
2. Identify underweight positions (add to these)
3. Prefer adding to underweight over selling overweight (tax efficiency)
4. Execute rebalance trades over 1-2 weeks, not all at once

### Target Allocation
Set at time of purchase. Example for a 4-position portfolio:
- Core position: 30-40%
- Secondary positions: 20-25% each
- Satellite/speculative: 5-10%
- Cash reserve: 15-20%

---

## Core vs. Satellite Structure

### Core Holdings (60-70% of portfolio)
- Broad-based: VOO, VTI, or sector ETFs with long-term thesis
- Hold for 1+ years minimum
- Only sell if thesis fundamentally breaks
- Rebalance quarterly

### Satellite Holdings (20-30%)
- Tactical: individual stocks or sector bets tied to current macro
- Hold for weeks to months
- Tighter stops, more active management
- Re-evaluate every report

### Cash Reserve (10-20%)
- Always maintain a cash buffer
- Dry powder for opportunities (flash dips, VIX spikes)
- Higher cash in uncertain environments (war, pre-FOMC)

---

<!-- AUTO-FIX: OPEN POSITION REVIEW (updated 2026-03-20) -->
## Open Position Review (Mandatory Every Report)

Every report MUST include a health check for EACH open position:
1. **Stop-loss status:** Current price vs stop price. Has it been hit? → SELL
2. **Thesis status:** Is the original thesis still valid? What changed? → If broken, SELL
3. **Profit-taking triggers:** Check against +30%/+50%/+100% thresholds above
4. **Concentration check:** Is position >15% of **total capital** (not just holdings)? → TRIM
5. **Smart money alignment:** Are pros still holding? If all selling → FLAG for review

Output a position health table:
| Ticker | Entry | Current | P&L | Stop | Thesis | Action |
If ANY position triggers a SELL/TRIM rule, it MUST appear in the report's Portfolio section.

**Oversold guard:** If a position is at RSI <25, do not SELL unless the stop-loss has been hit. Deeply oversold positions are more likely to bounce than fall further. Selling at RSI extremes is panic selling.
<!-- END OPEN POSITION REVIEW -->

## Performance Tracking

### After Every Report
Log every call in vault.db (auto-tracked by the system).
Fields tracked: date, ticker, action, entry, stop, target, conviction, status, exit_price, exit_date, return, notes.

Status values: OPEN / HIT_TARGET / STOPPED_OUT / CLOSED_EARLY / EXPIRED

### Quarterly Review
- Win rate by conviction level (*** should win more than *)
- Average return per trade
- Average holding period
- Biggest winner and biggest loser — what can you learn?
- Portfolio vs. VOO — is the system adding value?

---

## Tax Awareness

Tax rules depend on the investor's location (read from vault.db via `vault portfolio`).
- Research the investor's local tax treatment of foreign investment income
- Tax-loss harvesting: if a position is down and thesis is broken, selling crystallizes a loss that may offset gains
- Keep records of all trades for annual declaration
- Most brokers provide tax reports — download annually

---



<!-- PRO-INSIGHT: PORTFOLIO-LEVEL RISK -->
## Portfolio-Level Risk Controls (learned from pro analysis)

### Drawdown Circuit Breaker
If portfolio drops **15% from peak value** (NOT from cost basis):
1. Raise cash to 30%+ (trim weakest positions first)
2. Tighten all trailing stops by one tier
3. No new BUY recommendations until drawdown recovers to -10% from peak
4. Type `flash` for emergency assessment

<!-- LOGIC FIX (2026-03-20): db.py calculates drawdown from cost basis, not peak. A portfolio up 30% that falls 20% from peak shows +4% from cost — circuit breaker never fires. Track peak_portfolio_value in DB settings. Calculate drawdown = (current - peak) / peak. -->
**Implementation:** Store peak portfolio value in vault.db settings table. Update on every `portfolio_dashboard()` call when current value > stored peak. Drawdown = `(current_value - peak_value) / peak_value`.

*Source: Funds with stop-loss clauses consistently outperform. Portfolio-level limits prevent catastrophic losses.*

### Turnover Check
If portfolio turns over >50% annually (excluding stopped-out positions):
- Flag as potential over-trading in self-analyze
- Review if short holding periods are driven by panic or plan
- Optimal turnover per academic research: ~25%/year

*Source: Institutional average 58% turnover is suboptimal. Literature suggests 25% (4-year hold) maximizes after-fee returns.*

### Position Count Targets
| Portfolio Size | Target Positions | Approach |
|---------------|-----------------|----------|
| Under $10K | 5-8 | ETF-heavy for diversification |
| $10K-$25K | 8-12 | Mix of ETFs and individual stocks |
| $25K-$100K | 12-20 | Full diversification, manageable |
| $100K+ | 15-25 | Academic optimal range |

*Source: CFA Institute — beyond 30 positions, volatility reduction is <3% while return dilution increases.*

### Conviction-Weighted Sizing (Buffett-Inspired)
Top funds concentrate in highest-conviction ideas. Buffett: top 5 = 70% of portfolio.
Retail adaptation:
| Conviction | Max Position Size | Notes |
|-----------|------------------|-------|
| `***` HIGH | 18% | Core positions with strongest thesis |
| `**` MEDIUM | 12% | Standard positions |
| `*` LOW | 7% | Speculative/satellite only |

*Source: Berkshire top 5 holdings = 70% of $267B portfolio. Concentration works when thesis is validated.*

### Position Sizing Sanity Check

**Before 20 trades (early portfolio):**
Use a simple diversification rule as sizing guardrail:
```
max_position = total_capital / (number_of_positions + 2)
```
Capped at conviction limit (*** 18%, ** 12%, * 7%). Example: 4 positions → max = 1/6 = 16.7% per position.

<!-- LOGIC FIX (2026-03-20): Kelly was gated behind 20+ trades, leaving no mathematical sizing check during the critical early phase when concentration mistakes hurt most. This simple rule provides a floor that loosens as the portfolio grows. -->

**After 20+ closed trades (Kelly Criterion):**
```
kelly_pct = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
```
Use half-Kelly (kelly_pct / 2) as a sanity check. If positions consistently exceed Kelly, you're over-betting.

*Source: Renaissance Technologies uses Kelly Criterion for optimal position sizing.*

## Emergency Rules

<!-- LOGIC FIX (2026-03-20): Circuit breaker says "raise cash to 30%" while crash rule says "deploy cash if VIX >35". These fire simultaneously in a severe crash. Priority: circuit breaker wins. Only deploy cash in a crash if portfolio is NOT in circuit breaker state (drawdown <15% from peak). -->

### Market Crash (S&P -10% in a week)
1. Do NOT panic sell
2. Review all stop-losses — let them do their job
3. If stops haven't triggered, positions are still within plan
4. **If circuit breaker is NOT active** (drawdown <15% from peak): deploy cash into highest-conviction positions if VIX >35
5. **If circuit breaker IS active** (drawdown >15%): do NOT deploy cash. Stabilize first. Circuit breaker overrides this rule.
6. Type `flash` for immediate guidance

### Flash Crash / Black Swan
1. Do nothing for 24 hours
2. Check if stops triggered (if so, they worked as designed)
3. Assess if the event is temporary (flash crash) or structural (paradigm shift)
4. Type `flash` after 24 hours for assessment

### Personal Emergency (Need Cash)
1. Sell satellite positions first (they're tactical anyway)
2. Sell core positions last
3. Never sell everything — even in an emergency, keep some invested if possible
