# Execution Protocol — MANDATORY

## Purpose
This document exists because Claude compressed a 7-agent pipeline into a single pass and delivered a half-baked report. That happened TWICE — once with invisible internal work, once by skipping the Devil's Gate entirely and running it after the fact when called out. These rules FORCE the full pipeline to run on every `report` and `report pdf` command.

**This file overrides any impulse to "save time" or "be efficient." The pipeline exists for a reason. Run it.**

---

## The Non-Negotiable Rule

**When Pavlo types `report` or `report pdf`, Claude MUST execute every agent in sequence, producing each agent's required outputs BEFORE moving to the next agent.** Each agent's output feeds into the next. Skipping an agent means the downstream agents are working with incomplete data, which produces a bad report.

### VISIBLE OUTPUT RULE

**Claude MUST show each agent's output in chat as it runs.** Pavlo sees everything. No "internal work." No "I did it behind the scenes." If it's not visible in the chat, it didn't happen.

Each agent's output must be posted in chat BEFORE the next agent starts. Format:

```
═══ AGENT [N]: [NAME] ═══
[Full output per the agent's "What You Produce" section]
═══ CHECKPOINT: [answer checkpoint question] ═══
```

**If any checkpoint answer is missing or vague, Claude MUST stop and fix it before proceeding.** Pavlo can read along and call out problems in real time.

The ONLY agent whose output is NOT shown raw is the Report Writer (Agent 7) — because the Report Writer's output IS the final report/PDF. Everything before it is visible.

---

## SEARCH LOG RULE

**Before generating the PDF or final report, Claude MUST post a complete Search Log table in chat.**

Format:
```
═══ SEARCH LOG ═══
| # | Search Query | Ticker/Data | Verified Price/Value | Date |
|---|-------------|-------------|---------------------|------|
| 1 | "S&P 500 today" | SPX | 6,796 | 3/10 |
| 2 | "GOOGL stock price today" | GOOGL | $306.36 | 3/10 |
...
```

**Rules:**
- Every ticker that appears in the final report MUST have a row in this table.
- Every row must have a verified price from a web search — not from memory, not estimated.
- If a BUY candidate does NOT have a row in this table, it CANNOT appear in the report.
- The Search Log must be posted AFTER the Technical Analyst (Step 3) and BEFORE the Risk Manager (Step 4).
- If Pavlo spots a missing ticker in the Search Log, Claude must search for it before continuing.

---

## Step-by-Step Execution (No Shortcuts)

### PHASE 1: DATA COLLECTION (before any agent runs)

**Search Phase 1 — Macro Data:**
Run web searches for ALL of the following. Do not start Agent 1 until you have real numbers:
- S&P 500, Nasdaq, Dow current levels and daily change
- VIX level
- WTI crude oil price
- 10Y Treasury yield
- Gold price
- DXY dollar index
- Latest jobs data / inflation data
- Fed funds rate / next meeting expectations
- Top geopolitical headlines affecting markets

**Search Phase 2 — Portfolio + BUY Candidate Prices:**
For EVERY ticker that might appear in the report, run a SEPARATE price search:
- All portfolio holdings (from portfolio.md)
- All sector ETFs being analyzed (XLE, XLV, XLK, etc.)
- All individual stock candidates
- Format: "[TICKER] stock price today [date]"

**Post the raw search results summary in chat before starting Agent 1.** Format:
```
═══ PHASE 1 DATA COLLECTED ═══
S&P 500: [value] | Nasdaq: [value] | Dow: [value]
VIX: [value] | Oil (WTI): [value] | Gold: [value]
10Y Yield: [value] | DXY: [value] | Fed Rate: [value]
Key Headlines: [1-2 sentences]
═══
```

### PHASE 2: AGENT PIPELINE (strict sequence, ALL outputs visible in chat)

---

#### STEP 1: Macro Strategist
Read `01_macro_strategist.md`. Produce ALL required outputs **and post them in chat**:
- [ ] Macro Regime (one sentence)
- [ ] Top 3-5 Drivers with specific data points
- [ ] Key Economic Data (number, expectation, meaning)
- [ ] Geopolitical Risk with transmission channels
- [ ] Central Bank Outlook
- [ ] Three Scenarios with probability estimates
- [ ] Alert Conditions (2-3 specific thresholds)
- [ ] "This Week" macro event calendar

**Checkpoint (post in chat):** "Macro Regime: [one-sentence label]. Top driver: [specific data point]."

---

#### STEP 2: Sector Analyst + Sentiment Analyst (parallel)
Read `02_sector_analyst.md` and `03_sentiment_analyst.md`. Both use Macro output as input. **Post both outputs in chat.**

**Sector Analyst outputs:**
- [ ] Sector Heatmap (rank all 11 GICS sectors)
- [ ] Rotation Thesis tied to macro regime
- [ ] Top 2-3 winner sectors with specific stocks
- [ ] Bottom 2-3 loser sectors with vulnerable names
- [ ] Contrarian Watch
- [ ] Upcoming Catalysts (earnings within 7 days)
- [ ] Portfolio Relevance (how macro helps/hurts each holding)
- [ ] Correlation flags for recommended stocks

**Sentiment Analyst outputs:**
- [ ] Sentiment Regime (one sentence)
- [ ] Fear/Greed Dashboard with SPECIFIC values (VIX number, put/call ratio, etc.)
- [ ] Smart Money vs. Dumb Money divergence
- [ ] Consensus Position + where crowd may be wrong
- [ ] Sentiment Signal (contrarian BUY/SELL/neutral)
- [ ] Behavioral Warning for Gut Check section
- [ ] Crowd Positioning per holding

**Checkpoint (post in chat):** "Sector #1: [sector]. Sector #11: [sector]. VIX used: [specific number]."

---

#### STEP 3: Technical Analyst
Read `04_technical_analyst.md`. Uses Sector + Sentiment output as input. **Post all outputs in chat.**

**Required outputs:**
- [ ] Market Structure (one sentence)
- [ ] Key Levels Table (support/resistance for indices and key stocks)
- [ ] Trend Assessment (uptrend/downtrend/range + strength)
- [ ] Breadth Analysis
- [ ] Technical Signal (BUY/SELL/WAIT)
- [ ] Portfolio Stock Levels (support, resistance, breakdown for each holding)
- [ ] BUY Candidate Levels (entry range, stop-loss, profit target for each candidate)
- [ ] Rejection Flags (any recommended stock with a broken chart)
- [ ] Price Verification Checklist (verified price, entry, gap % for EVERY ticker)

**MANDATORY: Run a separate web search for the current price of EVERY stock/ETF that will appear in the report.** General market searches are NOT enough.

**Checkpoint (post in chat):** Price Verification Checklist table with every ticker, verified price, entry zone, and gap %.

**Post the SEARCH LOG table here** (see Search Log Rule above). Every ticker in the report must have a verified row.

---

#### STEP 4: Risk Manager
Read `05_risk_manager.md`. Receives ALL previous outputs. **Post all outputs in chat.**

**Required outputs:**
- [ ] Risk Regime (one sentence)
- [ ] Top 5 Risks ranked by probability x impact, each with trigger + transmission channel + portfolio impact
- [ ] Stress Tests (bull/base/bear for proposed positions)
- [ ] Consensus Challenges (specific disagreements with other agents)
- [ ] Correlation Warnings (hidden links between positions)
- [ ] Risk Recommendations (hedges, position sizes, stop-losses, cash %)
- [ ] Behavioral Risk Assessment (Stay the Course / Watch Out: Fear / Watch Out: Greed)
- [ ] Rebalance Check (if portfolio has holdings)

**Hard Veto Check:**
- [ ] Any two BUY picks with >0.8 correlation? → One must be dropped
- [ ] Any position >15% of portfolio? → Must be flagged
- [ ] Any BUY candidate reporting earnings within 3 days? → Flag or block
- [ ] Any entry zone >7% below verified price? → REJECT

**Checkpoint (post in chat):** "Risk Manager challenges: [list at least one specific disagreement]."

---

#### STEP 5: Chief Strategist
Read `06_chief_strategist.md`. Receives ALL previous outputs. **Post all outputs in chat.**

**Required outputs:**
- [ ] Executive Summary (4-5 sentences)
- [ ] Market Regime label
- [ ] Performance Review (if past reports exist)
- [ ] Key Thesis (1-2 main ideas)
- [ ] Agent Agreement (where all agents align)
- [ ] Agent Disagreement (tensions + your tiebreak decision)
- [ ] Portfolio Calls (if holdings exist)
- [ ] New BUY Recommendations (3-5 picks with ticker, conviction, entry, timeframe, reasoning, exit trigger)
- [ ] SELL / AVOID list
- [ ] HEDGE Recommendations
- [ ] Cash Target %
- [ ] Thesis Change Triggers
- [ ] Alert Conditions
- [ ] Price Verification Sign-Off block

**Mandatory checks:**
- [ ] Every Risk Manager veto is addressed (not ignored)
- [ ] Every Technical Analyst rejection flag is addressed
- [ ] Every BUY has: thesis + timeframe + conviction + "what changes my mind"
- [ ] Past calls reviewed (if report history exists)

**Checkpoint (post in chat):** Price Verification Sign-Off block showing PASS for every ticker. If any fails — fix before proceeding.

---

#### STEP 5.5: QA Gate
Per `08_orchestration.md` QA Gate section. **Post results in chat.**

- [ ] Every ticker had a dedicated price search (cross-reference Search Log)
- [ ] Every entry zone is within 5% of verified price (or has explicit justification)
- [ ] Levels are internally consistent (stop < entry < target)
- [ ] All Risk Manager vetoes were addressed with a decision
- [ ] Performance review included (if past reports exist)
- [ ] Portfolio section matches portfolio.md

**If any check fails:** Fix the price or drop the pick. Do NOT proceed to Devil's Gate.

**Checkpoint (post in chat):** "QA Gate: [PASS/FAIL]. Issues: [list any]."

---

#### STEP 5.75: Devil's Gate
Read `09_devils_gate.md`. Run ALL EIGHT TESTS (Test 0 through Test 7). **Post the full formal validation report in chat.** Not a summary. Not "3 questions." All eight tests with PASS/FLAG/REJECT for each.

**Test 0 — Portfolio Reality Check:** Verify portfolio.md status. If empty, report must not have HOLD/SELL calls. If has holdings, verify no phantom holdings.

**Test 1 — Thesis Flip Test:** For EACH BUY, argue the exact opposite. Rate counter-argument 1-5. If 4-5: REJECT. If 3: FLAG.

**Test 2 — Contradiction Scan:** Find every place two agents disagree and verify the Chief resolved it explicitly.

**Test 3 — Doomsday Scenario:** Find ONE scenario that kills 3+ picks simultaneously. Mandatory — every report must have this.

**Test 4 — Entry Zone Reality Check:** Verify every entry zone makes sense (not just the price, but the LOGIC). Cross-reference Search Log.

**Test 5 — Pavlo Test:** Can he execute with his capital on IBKR from Ukraine? Is position sizing realistic? Is the emotional load manageable?

**Test 6 — Consistency Check:** Compare against previous reports (skip if first report).

**Test 7 — Omission Audit:** What's MISSING? Sectors, risks, hedges, exit plans?

**Produce the formal output IN CHAT:**
```
═══════════════════════════════════════════════
       DEVIL'S GATE — VALIDATION REPORT
═══════════════════════════════════════════════

STATUS: [APPROVED / APPROVED WITH FLAGS / REJECTED]

TEST RESULTS:
0. Portfolio Reality Check:  [PASS / REJECT]
1. Thesis Flip Test:         [PASS / FLAG / REJECT]
2. Contradiction Scan:       [PASS / FLAG / REJECT]
3. Doomsday Scenario:        [PASS / FLAG / REJECT]
4. Entry Zone Reality:       [PASS / FLAG / REJECT]
5. Pavlo Test:               [PASS / FLAG / REJECT]
6. Consistency Check:        [PASS / FLAG / REJECT / SKIP]
7. Omission Audit:           [PASS / FLAG / REJECT]

CRITICAL ISSUES: [if any]
FLAGS: [if any]
UNCOMFORTABLE QUESTIONS: [2-4 real ones]
═══════════════════════════════════════════════
```

**If REJECTED:** Route back to responsible agent, fix, re-run from Step 5.5. Max 2 cycles, then drop the pick.

**Checkpoint (post in chat):** "Devil's Gate Status: [status]. Doomsday: [one-sentence scenario]. Questions: [list 2-4]."

---

#### STEP 6: Report Writer
Read `07_report_writer.md`. Receives Chief output + Devil's Gate FLAGS + Uncomfortable Questions.

**Produce the final report with ALL sections:**
1. What's Happening
2. This Week (table)
3. Changes Since Last Report (if history exists)
4. Your Portfolio (if holdings exist)
5. What to Buy (table with stop-losses included)
6. What to Avoid
7. Biggest Risks (include Devil's Gate Doomsday + Uncomfortable Questions)
8. Chief's Corner (include Devil's Gate Uncomfortable Questions)
9. Gut Check (NEVER skip — use Risk Manager's behavioral assessment)
10. Alert Conditions
11. Bottom Line
12. Disclaimer

**Devil's Gate Integration:**
- [ ] All FLAGS visible as caveats or risk notes
- [ ] Uncomfortable Questions woven into Biggest Risks or Chief's Corner
- [ ] Doomsday Scenario mentioned in Biggest Risks
- [ ] Conviction levels adjusted per Devil's Gate recommendations

---

#### STEP 6b: PDF Generation (if `report pdf`)
Read `10_pdf_rules.md`. Follow all PDF rules. Generate the PDF, spot-check ONE page for broken tables, and present. **Do NOT iterate on layout to hit a page count target.** Analysis quality >>> layout polish. One render attempt, one visual check, done.

---

#### STEP 7: Report Summary
Auto-generate the Active Calls table for Pavlo to save.

---

## What "Running an Agent" Actually Means

It does NOT mean: "I thought about macro briefly and wrote a paragraph."

It DOES mean: "I produced every required output listed in that agent's 'What You Produce' section, using data from web searches, referencing the upstream agent's output, and flagging disagreements or problems — AND I posted it all in chat for Pavlo to see."

Each agent has a specific list of outputs in their .md file. Every item on that list must be produced. If an agent file says "produce 8 outputs," then 8 outputs must exist in the chat before moving to the next step.

---

## Enforcement: The "Show Your Work" Rule

Before delivering the report, the following must ALL be visible in the chat history (Pavlo can scroll up and verify):

1. ═══ PHASE 1 DATA COLLECTED ═══ block with all macro data
2. ═══ AGENT 1: MACRO STRATEGIST ═══ with regime label and all outputs
3. ═══ AGENT 2: SECTOR ANALYST ═══ with full 11-sector heatmap
4. ═══ AGENT 3: SENTIMENT ANALYST ═══ with specific VIX number
5. ═══ AGENT 4: TECHNICAL ANALYST ═══ with price verification checklist
6. ═══ SEARCH LOG ═══ with every ticker verified
7. ═══ AGENT 5: RISK MANAGER ═══ with at least one challenge
8. ═══ AGENT 6: CHIEF STRATEGIST ═══ with price sign-off block
9. ═══ QA GATE ═══ with PASS/FAIL
10. ═══ DEVIL'S GATE ═══ full 8-test validation report
11. The final report or PDF

**If ANY of items 1-10 are missing from the chat, the report is invalid.**

---

## Anti-Compression Rules

1. **No agent can start until the previous agent's output is posted in chat.** The checkpoint for Agent N must appear before Agent N+1 begins.
2. **No "I ran this internally" claims.** If it's not in the chat, it didn't happen.
3. **No combining agents.** Agent 2 (Sector) and Agent 3 (Sentiment) run in parallel but must each have their own visible output block.
4. **No skipping Devil's Gate.** If the Devil's Gate validation report is not visible in chat before the PDF is generated, the PDF is invalid.
5. **No retroactive compliance.** Running Devil's Gate "after being called out" does not count. It must run in sequence BEFORE the Report Writer.

---

## Time Expectations

A full `report` run takes significant effort. That is the point. The quality of the report IS the product.

**With visible outputs, the report will span multiple chat messages.** That is expected and correct. A full report run might produce 8-12 messages before the final PDF.

**Where to spend the time:** 80%+ of effort goes into data collection, agent analysis, and Devil's Gate. PDF formatting is the LEAST important step.

---

## Commands That Skip Steps (Exceptions)

| Command | What Runs | What's Skipped | Visible Output Required? |
|---------|-----------|----------------|--------------------------|
| `report` / `report pdf` | FULL pipeline, all agents, all tests | Nothing | YES — all agents visible |
| `analyze [TICKER]` | Full pipeline focused on one stock + Devil's Gate | Sector heatmap | YES — all agents visible |
| `flash` | Macro + Risk + Chief only | Sector, Sentiment, Technical, QA, Devil's Gate | NO — speed mode |
| `quick` | Abbreviated all agents | Devil's Gate, QA Gate | NO — abbreviated |
| `watchlist` | Price lookup only | All agents, Devil's Gate | NO — just prices |
| `risks` | Macro + Risk only | Others | Partial |
| `score` | Performance tracking only | All agents | NO |
| `rebalance` | Risk Manager rebalance check only | Others | Partial |

**Only `report`, `report pdf`, and `analyze` require full visible output. Everything else is lightweight by design.**
