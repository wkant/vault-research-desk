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

| Conviction | Stop Distance | Example |
|-----------|--------------|---------|
| `***` HIGH | 10-12% below entry | Entry $100, stop $88-90 |
| `**` MEDIUM | 8-10% below entry | Entry $100, stop $90-92 |
| `*` LOW | 7-8% below entry | Entry $100, stop $92-93 |

Stops should align with meaningful levels when possible (prior lows, moving averages). But if no meaningful level exists within the range, use the percentage rule.

### Trailing Stops
After a position moves in your favor:

| Gain from Entry | New Stop Level |
|----------------|---------------|
| +10% | Move stop to breakeven (entry price) |
| +20% | Move stop to +10% above entry |
| +30% | Move stop to +20% above entry |

**Update trailing stops in portfolio.md notes or at each report.**

### When a Stop Triggers
- The stop triggered → the position is SOLD. No "let me hold a little longer."
- The next report must acknowledge the stop hit and explain what happened
- Log it in performance_log.csv
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
- **Drift trigger:** Any single position >5% away from target weight
- **Sector trigger:** Any sector >35% of portfolio

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

## Performance Tracking

### After Every Report
Log every call in `performance_log.csv`:
```csv
date,ticker,action,entry,stop,target,conviction,status,exit_price,exit_date,return,notes
```

Status values: OPEN / HIT_TARGET / STOPPED_OUT / CLOSED_EARLY / EXPIRED

### Quarterly Review
- Win rate by conviction level (*** should win more than *)
- Average return per trade
- Average holding period
- Biggest winner and biggest loser — what can you learn?
- Portfolio vs. VOO — is the system adding value?

---

## Tax Awareness

Tax rules depend on the investor's location (read from portfolio.md Profile section).
- Research the investor's local tax treatment of foreign investment income
- Tax-loss harvesting: if a position is down and thesis is broken, selling crystallizes a loss that may offset gains
- Keep records of all trades for annual declaration
- Most brokers provide tax reports — download annually

---



<!-- PRO-INSIGHT: PORTFOLIO-LEVEL RISK -->
## Portfolio-Level Risk Controls (learned from pro analysis)

### Drawdown Circuit Breaker
If portfolio drops **15% from peak value**:
1. Raise cash to 30%+ (trim weakest positions first)
2. Tighten all trailing stops by one tier
3. No new BUY recommendations until drawdown recovers to -10%
4. Type `flash` for emergency assessment

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

### Simplified Kelly Criterion (after 20+ trades)
Once performance_log.csv has 20+ closed trades, calculate:
```
kelly_pct = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
```
Use half-Kelly (kelly_pct / 2) as a sanity check on position sizing.
If your actual position sizes consistently exceed Kelly, you're over-betting.

*Source: Renaissance Technologies uses Kelly Criterion for optimal position sizing.*

## Emergency Rules

### Market Crash (S&P -10% in a week)
1. Do NOT panic sell
2. Review all stop-losses — let them do their job
3. If stops haven't triggered, positions are still within plan
4. Deploy cash reserve into highest-conviction positions if VIX >35
5. Type `flash` for immediate guidance

### Flash Crash / Black Swan
1. Do nothing for 24 hours
2. Check if stops triggered (if so, they worked as designed)
3. Assess if the event is temporary (flash crash) or structural (paradigm shift)
4. Type `flash` after 24 hours for assessment

### Personal Emergency (Need Cash)
1. Sell satellite positions first (they're tactical anyway)
2. Sell core positions last
3. Never sell everything — even in an emergency, keep some invested if possible
