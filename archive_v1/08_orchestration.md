# Agent Orchestration — How the Agents Work Together

## CRITICAL: Read 00_execution_protocol.md FIRST
Before running any agent, read `00_execution_protocol.md`. That file contains the mandatory step-by-step execution checklist that enforces the full pipeline. The orchestration file below describes WHAT passes between agents. The execution protocol describes HOW to run them and the checkpoints that prevent skipping steps.

---

## PORTFOLIO SINGLE SOURCE OF TRUTH (NEW — March 10, 2026)

**This rule overrides EVERYTHING. Every agent must obey it. No exceptions.**

### `portfolio.md` is the ONLY source of truth for Pavlo's financial data.

This means:
- **What Pavlo owns:** ONLY what's listed in portfolio.md with a ticker and shares. If portfolio.md is empty, he owns NOTHING. Do not use memory, chat history, conversation context, or any other source to determine holdings.
- **How much money he has:** ONLY what's in portfolio.md under "Cash available." If it's blank, do not assume any specific amount. Do not pull numbers from memory or past conversations.
- **Monthly investment amount:** ONLY what's in portfolio.md under "Monthly investment." If it says $3,500, use $3,500. If it's blank, do not assume.
- **Risk tolerance:** ONLY what's in portfolio.md under "Risk tolerance." If it's blank, assume moderate.
- **Cost basis / purchase dates:** ONLY what's in portfolio.md. If missing, skip P&L calculations.

### What is NOT a source of truth:
- Claude's memory or userMemories — these may contain outdated, planned, or aspirational info
- Past conversations — Pavlo might have discussed buying something but never did
- Previous reports — a BUY recommendation doesn't mean he bought it
- Assumptions — "he probably bought GOOGL since we recommended it" is NOT valid

### What happens when portfolio.md is empty:
- NO "Your Portfolio" section in the report
- NO HOLD or SELL calls (you can't hold or sell what you don't own)
- NO references to "your holdings" or "your positions"
- ALL recommendations are framed as NEW BUY candidates
- Position sizing is based on monthly investment amount (if provided) or general guidance
- The report should say something like: "No holdings on file. All picks below are new positions to consider."

### What happens when portfolio.md has holdings:
- Every holding gets a HOLD / BUY more / SELL call
- Recommendations consider existing exposure (don't recommend tech if he's already heavy tech)
- P&L is calculated if cost basis is available
- Rebalance checks run against actual positions

### Enforcement:
- Devil's Gate Test 0 (Portfolio Reality Check) catches violations
- If ANY agent references holdings not in portfolio.md → CRITICAL REJECT
- If the report contains a "Your Portfolio" section when portfolio.md is empty → CRITICAL REJECT

**Why this rule exists:** On March 10, 2026, Claude built an entire report around 6 stocks it assumed Pavlo owned based on memory notes. Pavlo owned none of them. The portfolio file was empty. Every HOLD call, every P&L estimate, every portfolio-specific risk assessment was fiction. This rule ensures that never happens again.

---

## Execution Order

The agents run in strict sequence. Each agent's output becomes input for downstream agents. This is NOT optional — skipping an agent or running them out of order produces worse results.

**The pipeline includes backward feedback loops, a QA gate, and the Devil's Gate adversarial validation layer.**

```
STEP 1:  [Macro Strategist]
              |
              | passes: macro regime, key drivers, scenarios,
              |         geopolitical assessment, central bank outlook,
              |         ALERT CONDITIONS
              |
         ┌────┴────┐
         v         v
STEP 2:  [Sector   [Sentiment
         Analyst]   Analyst]
              |         |
              | passes:  | passes:
              | sector   | sentiment regime,
              | heatmap, | fear/greed data,
              | winners/ | contrarian signals,
              | losers,  | flow data,
              | key      | BEHAVIORAL WARNING
              | stocks   |
              |         |
         └────┬────┘
              v
STEP 3:  [Technical Analyst]
              |
              | passes: key levels, trend assessment,
              |         breadth analysis, technical signals,
              |         REJECTION FLAGS ──→ feedback to Sector/Chief
              v
STEP 4:  [Risk Manager]
              |
              | receives: ALL above
              | passes: top risks, stress tests,
              |         consensus challenges, HARD VETOES,
              |         hedge recommendations,
              |         BEHAVIORAL RISK ASSESSMENT,
              |         REBALANCE CHECK
              v
STEP 5:  [Chief Strategist]
              |
              | receives: ALL above
              | produces: synthesized analysis with
              |           BUY/HOLD/SELL calls, portfolio
              |           recommendations, thesis triggers,
              |           PERFORMANCE REVIEW,
              |           PRICE VERIFICATION SIGN-OFF,
              |           ALERT CONDITIONS
              v
STEP 5.5: [QA GATE] — runs between Chief and Devil's Gate
              |
              | Final price verification on every ticker
              | Rejects any entry zone >5% below verified price
              | Confirms all Risk Manager vetoes were addressed
              v
STEP 5.75: [DEVIL'S GATE] — adversarial validation layer
              |
              | Test 0: Portfolio Reality Check (is portfolio.md empty?)
              | Tests 1-7: Stress-tests thesis, logic, consistency
              |
              ├── APPROVED → proceeds to Step 6
              ├── APPROVED WITH FLAGS → proceeds to Step 6 (flags become caveats in report)
              └── REJECTED → routes back to responsible agent(s) → re-enters at Step 5.5
              v
STEP 6:  [Report Writer]
              |
              | receives: Chief Strategist output (QA-verified, Devil's Gate cleared)
              | receives: Devil's Gate FLAGS (must appear as caveats)
              | receives: Devil's Gate Uncomfortable Questions (for Chief's Corner / Biggest Risks)
              | produces: the final user-facing report
              |           including GUT CHECK section
              v
         [USER SEES THIS]

STEP 7:  [Report Summary] — auto-generated after every report
              |
              | produces: lightweight markdown with just the calls
              |           for performance tracking in future reports
```

---

## Agent Feedback Loops

The pipeline is not purely one-directional. These feedback loops make it smarter:

### Technical → Sector/Chief Feedback
If the Technical Analyst discovers that a stock recommended by the Sector Analyst has a broken chart (below 200 DMA, breakdown confirmed, no support), the Technical Analyst issues a **REJECTION FLAG**. The Chief Strategist MUST either:
- Drop the pick entirely, or
- Override with explicit justification

### Risk Manager → Everyone Feedback (Hard Veto Rules)
These are NON-NEGOTIABLE. The Chief Strategist CANNOT override without explicit written justification:

- **Correlation veto:** If two BUY picks have >0.8 correlation, one MUST be dropped or replaced.
- **Concentration veto:** No single position >15% of portfolio, no single sector >35%.
- **Earnings veto:** Do not recommend buying a stock 1-3 days before earnings unless explicitly marked as an earnings play with reduced position size.
- **Price gap veto:** If any entry zone is >7% below verified current price with no justification, the pick is REJECTED.

### Sentiment → Risk Manager → Report Writer Behavioral Chain
Sentiment Analyst flags crowd behavior → Risk Manager assesses behavioral risk → Report Writer includes Gut Check section.

### Devil's Gate → Responsible Agent Feedback (Rejection Routing)
When Devil's Gate rejects a section, the rejection is routed to the specific agent responsible:

| Issue Type | Routes Back To |
|---|---|
| **Phantom holdings / portfolio.md violation** | **Chief Strategist (rewrite all portfolio sections)** |
| Weak thesis / bad logic | Chief Strategist |
| Bad entry zone / levels | Technical Analyst |
| Missing from Search Log | Technical Analyst |
| Missing risk / missing hedge | Risk Manager |
| Missed sector / missed stock | Sector Analyst |
| Contradicts macro regime | Macro Strategist |
| Unclear for Pavlo / execution issue | Report Writer |
| Unresolved agent disagreement | Chief Strategist |
| Missing earnings flag | Sector Analyst |

---

## What Gets Passed Between Agents

### Macro Strategist → Everyone
| Data Point | Example | Who Needs It |
|---|---|---|
| Macro regime label | "Stagflationary shock" | All agents (sets the frame) |
| Top drivers with data | "Oil at $93, NFP -92K" | Sector (rotation), Sentiment (fear justified?), Risk (scenarios) |
| Geopolitical assessment | "Hormuz blocked, war ongoing" | Sector (who benefits), Risk (tail risks) |
| Central bank outlook | "Fed on hold, no cut before Sep" | Sector (rate-sensitive sectors), Technical (rate impact on levels) |
| Scenarios with probabilities | "Bull 20%, Base 50%, Bear 30%" | Risk (stress tests), Chief (conviction calibration) |
| Alert conditions | "If oil >$100, regime shifts to bear" | Chief (inherits for report), Report Writer (includes at end of report) |

### Sector Analyst → Downstream
| Data Point | Example | Who Needs It |
|---|---|---|
| Sector heatmap (ranked) | "Energy #1, Financials #10" | Technical (where to focus), Chief (recommendations) |
| Winner sectors + key stocks | "Energy: XOM, CVX, OXY" | Technical (chart these stocks), Chief (BUY candidates) |
| Loser sectors + vulnerable stocks | "Travel: CCL, UAL, DAL" | Risk (short candidates), Chief (AVOID list) |
| Rotation thesis | "Money flowing from growth to value" | Sentiment (cross-check with flows), Chief (narrative) |
| Contrarian watch | "Small caps cheapest in decade" | Risk (evaluate), Chief (speculative BUY?) |
| Portfolio relevance | Per portfolio.md holdings ONLY | Chief (personalized portfolio calls) |
| Correlation flag | "This pick correlates with existing holding" | Risk (veto check), Chief (diversification) |

### Sentiment Analyst → Downstream
| Data Point | Example | Who Needs It |
|---|---|---|
| Sentiment regime | "Extreme fear, nearing capitulation" | Technical (interpret chart signals), Chief (timing) |
| VIX + key indicators | "VIX 31, put/call 0.92" | Risk (hedging cost), Chief (is it cheap to hedge?) |
| Flow data | "Record $49M into XLE" | Risk (crowding risk), Chief (confirmation or warning) |
| Contrarian signal | "Fear is elevated but not extreme" | Chief (too early to buy the dip?) |
| Smart vs dumb money | "Institutions hedging, retail buying" | Risk (who's right?), Chief (conviction) |
| Behavioral warning | "Conditions likely to trigger panic selling" | Risk (behavioral assessment), Report Writer (Gut Check) |
| Crowd positioning per holding | Per portfolio.md holdings ONLY | Chief (calibrate dip vs. real move) |

### Technical Analyst → Downstream
| Data Point | Example | Who Needs It |
|---|---|---|
| Key support/resistance levels | "S&P support 6,600, resist 6,800" | Risk (stop-loss levels), Chief (entry zones) |
| Trend direction | "Downtrend, below 50 DMA" | Chief (don't fight the trend) |
| Breadth analysis | "Only 45% above 50 DMA" | Risk (fragility signal), Chief (confidence adjustment) |
| Technical signal | "WAIT — no clear entry" | Chief (timing recommendation) |
| Portfolio stock levels | Per portfolio.md holdings ONLY | Chief (stop-loss + target for each holding) |
| BUY candidate levels | "XLV: entry [range], stop [level], target [level]" | Chief (execution guidance for new buys) |
| Rejection flags | "REJECT CCL — chart broken" | Chief (drop pick or justify override) |
| Price verification checklist | "GOOGL: $305 verified, entry $290-305, gap 0-5%" | Chief (sign-off block), QA Gate (final check) |

### Risk Manager → Chief Strategist
| Data Point | Example | Who Needs It |
|---|---|---|
| Top 5 risks ranked | "1. Oil $150, 2. Stagflation trap" | Chief (calibrate conviction, add caveats) |
| VETOES on other agents | "Disagree with tech BUY — too stretched" | Chief (MUST address this directly) |
| Hedge recommendations | "Buy SPY puts, VIX at 14 = cheap" | Chief (include in final recommendations) |
| Cash allocation target | "20-30% cash" | Chief (include in final calls) |
| Correlation warnings | "Energy + ag are both Hormuz plays" | Chief (don't double up on same risk) |
| Stress test results | "Bear case: portfolio -18%" | Chief (position sizing) |
| Behavioral risk assessment | "Watch Out: Fear" | Report Writer (Gut Check section) |
| Rebalance check | Per portfolio.md holdings ONLY | Report Writer (Rebalance alert) |

### Chief Strategist → QA Gate → Devil's Gate → Report Writer
| Data Point | Example | Who Needs It |
|---|---|---|
| Executive summary | Full 4-5 sentence synthesis | Writer (translate to plain English) |
| Performance review | Per previous reports ONLY | Writer (scorecard table) |
| Portfolio calls | Per portfolio.md holdings ONLY | Writer (present in table) |
| BUY recommendations | "XLV: HIGH conviction, [entry range]" | Writer (translate conviction to stars) |
| SELL/AVOID list | "Avoid XLY, VNQ" | Writer (present with plain reasons) |
| Top risks | "Earnings miss, inflation, breadth" | Writer (explain in simple terms) |
| Bottom line | Key takeaway + key action | Writer (make it memorable) |
| Price verification sign-off | "ALL PRICES VERIFIED" | Writer (trust the prices) |
| Alert conditions | "Flash if oil >$100 or VIX >35" | Writer (include at end of report) |

### Devil's Gate → Downstream
| Data Point | Example | Who Needs It |
|---|---|---|
| Gate Status | "APPROVED WITH FLAGS" | Report Writer (knows report is cleared) |
| **Portfolio Reality Check** | "portfolio.md is EMPTY — no holdings" | **All agents (reframe as new investor)** |
| Critical rejections | "BUY XLY thesis failed Flip Test" | Chief Strategist (must fix or drop) |
| Routed rejections | "Missing earnings flag for GOOGL" | Sector Analyst (must add) |
| Flags (moderate) | "Conviction on XLV may be too high" | Report Writer (include as caveat) |
| Uncomfortable Questions | "What if AI spending was front-loaded?" | Report Writer (Chief's Corner) |
| Doomsday scenario | "AI bust kills 3 of 4 picks" | Report Writer (Biggest Risks) |

---

## QA Gate — Between Chief Strategist and Devil's Gate

This gate runs AFTER the Chief Strategist finalizes but BEFORE the Devil's Gate validates.

### What It Checks
For every ticker that will appear in the report:
1. **Was a dedicated price search performed?** (not a general sector search — a specific "[TICKER] price today" search)
2. **Is the entry zone within 5% of verified price?** If not, is there explicit justification?
3. **Are levels internally consistent?** (stop below entry, target above entry)
4. **Were all Risk Manager vetoes addressed?** (not just acknowledged — addressed with a decision)
5. **Is the performance review included?** (if past reports exist)
6. **NEW: Does the report's portfolio section match portfolio.md?** If portfolio.md is empty and the report has HOLD/SELL calls, that's a FAIL.

### What Happens If It Fails
- Failed price check → fix the price or drop the pick. Do NOT pass to Devil's Gate.
- Unaddressed veto → send back to Chief Strategist to address.
- Missing performance review → add it. Past calls must be graded.
- **Portfolio mismatch → send back to Chief Strategist. Rewrite portfolio sections using portfolio.md ONLY.**

---

## Conflict Resolution Rules

Agents WILL disagree. That's by design. Here's how conflicts get resolved:

1. **Risk Manager vetoes a BUY signal:**
   - Chief Strategist MUST acknowledge the veto
   - Chief can override but must explain why
   - If overriding, conviction gets downgraded one level (HIGH → MEDIUM)

2. **Sentiment says BUY but Technical says WAIT:**
   - Technical wins on timing. Sentiment sets direction, technicals set entry.
   - Chief says: "We like it but waiting for a better entry at [level]"

3. **Macro is bearish but Sector finds winners:**
   - Both can be right. Bad macro doesn't mean everything goes down.
   - Chief should recommend the winners but with smaller position sizes.

4. **Two agents directly contradict:**
   - Chief Strategist states both views clearly
   - Takes a side and explains reasoning
   - Notes what data would resolve the disagreement

5. **Technical Analyst rejects a Sector Analyst pick:**
   - Chief Strategist REJECTS the entry zone or drops the pick
   - Never pass a broken-chart stock to the Report Writer without explicit justification

6. **Devil's Gate rejects a Chief Strategist call:**
   - Chief must revise the specific section and resubmit
   - Revised section passes through QA Gate + Devil's Gate again
   - If rejected twice, the pick is DROPPED (Three-Strike Rule)

---

## Quality Checks

Before the Chief Strategist finalizes:
- [ ] Every BUY has: ticker, conviction, entry zone, timeframe, reasoning, exit trigger
- [ ] Every SELL has: urgency level, reasoning
- [ ] Risk Manager's vetoes are addressed (not ignored)
- [ ] Scenarios from Macro are reflected in position sizing
- [ ] No recommendation contradicts the macro regime without explicit justification
- [ ] Hedge recommendations are included if Risk Manager flagged elevated risk
- [ ] **PRICE GATE: All entries verified with sign-off block**
- [ ] **PERFORMANCE: Past calls reviewed and graded (if report history exists)**
- [ ] **CORRELATION: No two BUY picks >0.8 correlated without justification**
- [ ] **CONCENTRATION: No position >15%, no sector >35%**
- [ ] **PORTFOLIO: All holdings referenced come from portfolio.md ONLY**

Before the Report Writer publishes:
- [ ] Devil's Gate status is APPROVED or APPROVED WITH FLAGS
- [ ] **Devil's Gate Test 0 (Portfolio Reality Check) is PASS**
- [ ] All Devil's Gate FLAGS are reflected in the report
- [ ] Devil's Gate Uncomfortable Questions appear in Chief's Corner or Biggest Risks
- [ ] If Devil's Gate ran a Doomsday Scenario, it's mentioned in Biggest Risks
- [ ] No REJECTED sections were passed through without revision
- [ ] No jargon remains unexplained
- [ ] Every recommendation is in a table
- [ ] Bottom Line section exists and is actionable
- [ ] **Gut Check section included (MANDATORY — never skip)**
- [ ] **Alert conditions included (2-3 specific thresholds)**
- [ ] **Rebalance check included (if portfolio.md has holdings — NOT if memory says so)**
- [ ] Disclaimer at the end (not scattered throughout)
- [ ] Diversification rules are respected
- [ ] Earnings calendar checked for portfolio holdings (per portfolio.md ONLY)
- [ ] "This Week" macro events included
- [ ] **FINAL PRICE SANITY CHECK: Read every entry zone. Does it make sense?**

---

## Earnings Calendar Awareness

The Sector Analyst MUST check for upcoming earnings reports each time:

1. **Portfolio holdings (per portfolio.md ONLY)** — if any stock Pavlo owns reports within 7 days, flag it
2. **BUY candidates** — don't recommend buying a stock 1-3 days before earnings unless explicitly noted
3. **Sector-moving earnings** — major companies that affect entire sectors

---

## Portfolio.md Reference

**portfolio.md is the SINGLE SOURCE OF TRUTH for all financial data about Pavlo.** All agents reference this file for personalized analysis. This file is managed exclusively by Pavlo. 

### What portfolio.md contains:
```
## Holdings
| Ticker | Shares | Avg Cost | Date Bought |
|--------|--------|----------|-------------|
| GOOGL  | 0.82   | $305     | 2026-03-10  |

## Settings
Risk tolerance: moderate
Monthly investment: $3,500
Cash available: $100
```

### Rules for reading portfolio.md:
- **If Holdings table is empty or has no ticker rows:** Pavlo owns NOTHING. Report gives general recommendations for a new investor.
- **If Monthly investment is blank:** Do not assume any specific amount. Give general position sizing guidance.
- **If Cash available is blank:** Skip cash-related advice.
- **If Risk tolerance is blank:** Assume moderate.
- **NEVER use Claude's memory, chat history, or past conversations as a substitute for portfolio.md data.**
- **NEVER assume Pavlo bought something just because a previous report recommended it.**
- **Agents NEVER modify portfolio.md.** Only Pavlo updates it.

### Why this matters:
On March 10, 2026, Claude used memory notes to fabricate a portfolio of 6 stocks (GOOGL, NVDA, XLE, LMT, XLV, GLD) that Pavlo did not actually own. The entire report — HOLD calls, P&L estimates, rebalance suggestions, risk analysis — was built on phantom holdings. The portfolio file was empty the whole time. This rule exists to prevent that from ever happening again.

---

## Mandatory Web Search Protocol

### Search Phase 1: Macro Data (before Agent 1)
- S&P 500, Nasdaq, Dow current levels
- VIX level
- WTI oil price
- 10Y Treasury yield
- Gold price, DXY dollar index
- Fed funds rate / next meeting expectations

### Search Phase 2: Individual Stock Prices (before Agent 4)
**For EVERY stock that will appear in the report** — run a SEPARATE web search:
```
"[TICKER] stock price today [current date]"
```
Minimum: 1 search per portfolio holding (from portfolio.md) + 1 search per BUY candidate + 1 per sector ETF referenced.

### Search Phase 3: QA Gate Verification (after Agent 6)
Spot-check 2-3 prices. If any moved >3% since Phase 2, update entry zones.

### Search Log (NEW — posted in chat before PDF)
Complete table of every search with ticker, verified price, and date. Any ticker missing from this log cannot appear in the report.

---

## Performance Tracking

### Before Every Report
The Chief Strategist reviews all active calls from previous reports (stored in report_YYYY-MM-DD.md files in project knowledge):
- Calls that worked → note what went right
- Calls that failed → own the mistake, explain what changed
- This scorecard appears in every report under "Changes Since Last Report"

**NOTE: A previous BUY recommendation does NOT mean Pavlo bought it. Check portfolio.md to see if he actually holds the position before calculating P&L.**

### After Every Report
Auto-generate a lightweight report summary for Pavlo to save.

### Conviction Tracker (`score` command)
When report history files exist: scorecard table, win rate, average return, lessons learned.

---

## Rebalance Protocol

**Only runs when portfolio.md contains actual holdings.** If portfolio.md is empty, skip entirely.

When portfolio.md contains holdings, the Risk Manager checks position drift every report:
1. Calculate current weight of each position based on current prices
2. Compare to target allocation
3. If any position drifted >5% from target: flag for rebalance
4. Report Writer includes specific rebalance instructions

---

## Portfolio Diversification Rules

### Single Stock Limits
- No single stock >15% of total portfolio (regardless of risk tolerance)
- Flag at 12%: "Getting concentrated — keep an eye on this"
- Flag at 15%+: "Too much in one stock. Trim back to 8-10%."

### Sector Limits
- No single sector >35% of total portfolio
- Aim for exposure to at least 3-4 different sectors

### Correlation Limits
- Avoid more than 2 positions that depend on the same catalyst

### Asset Mix Guidelines (from portfolio.md risk tolerance setting)

**Conservative:** 50% stocks, 25-30% cash, max 3% speculative
**Moderate:** 65% stocks, 15-20% cash, max 5% speculative
**Aggressive:** 80% stocks, 5-10% cash, max 10% speculative

---

## Alert Conditions System

Every report ends with 2-3 alert conditions. These are specific, measurable thresholds.

Pavlo checks these between reports. If a condition triggers, he types `flash` and gets immediate guidance.

---

## Emergency Flash Alert (`flash` command)

Pipeline: ONLY runs Macro Strategist + Risk Manager + Chief Strategist.
**Also skips QA Gate and Devil's Gate.** Speed > perfection in emergencies.

Output format:
1. **What happened** (2 sentences)
2. **What it means for your portfolio** (2 sentences — reference portfolio.md, or say "no holdings on file" if empty)
3. **What to do RIGHT NOW** (1-2 specific actions)

---

## Quick / Watchlist Exception

The `quick` and `watchlist` commands also skip Devil's Gate.
These are lightweight outputs that don't carry BUY/SELL recommendations with entry zones.

---

## Macro Event Calendar ("This Week")

Every report MUST include a "This Week" mini-table from the Macro Strategist.
Only events that could actually move markets. Skip noise.
