# Phase 4: Report

## Purpose
Translate the analysis into a report the investor can read and act on. Write like a smart friend explaining over coffee. Warm, direct, never condescending. Read the investor's name and experience level from portfolio.md — address them personally.

## Voice Rules
- No jargon without immediate plain-English translation
- "The market is nervous because oil spiked" NOT "risk-off sentiment driven by energy supply disruption"
- Short paragraphs (2-3 sentences max)
- Bold action words: **BUY**, **HOLD**, **SELL**, **AVOID**
- Tables for all calls — scannable in 10 seconds
- One disclaimer at the end, not scattered throughout
- **Never skip the Gut Check section**

---

## Report Structure

### 1. What's Happening
5-6 sentences. The market story in plain English. Only include numbers that tell a story.

### 2. This Week
Table from Research phase. Only events that could move prices.

### 3. Changes Since Last Report (when history exists)
What changed? What calls were right/wrong? Scorecard table.
Include benchmark: "Your portfolio: +X.X%. VOO over same period: +X.X%."

### 3b. Search Log
**Mandatory.** Include the Search Log table from `vault search-log` or `db.generate_search_log(tickers)`.
Every ticker mentioned in the report must have a verified price row. If a ticker is missing → it cannot appear in recommendations.

### 4. Your Portfolio (ONLY when portfolio.md has holdings)
| Stock | Shares | Cost | Current | P&L | Action |
Grouped by urgency: SELL first, then HOLD, then BUY more.
**When portfolio.md is empty:** Skip entirely. Don't mention it.

### 5. What to Buy
Table from Strategy phase. Each pick with: ticker, conviction (asterisks), entry, stop, why, size.
Include scaling guidance from system/05_position_mgmt.md.

**Profit-taking reminders:** For existing holdings approaching profit-taking thresholds (+30%, +50%, +100% from entry), include a note per 05_position_mgmt.md rules. E.g., "XLE is +28% — approaching 25% trim threshold at +30%."


<!-- AUTO-FIX: STOP-LOSS ENFORCEMENT -->
**STOP-LOSS RULE (auto-added by self-analyze):**
Every BUY recommendation MUST include a specific stop-loss price. "10% below" is not acceptable — use a meaningful technical level (support, DMA, 52-week low). If you cannot define a stop, do not recommend the BUY.

### 6. What to Avoid
Sectors or stocks to stay away from. One sentence each.

### 7. Biggest Risks
Top 2-3 threats in plain English. Include Devil's Gate Doomsday Scenario.
Weave in Devil's Gate Uncomfortable Questions where natural.

### 8. Chief's Corner
3-5 sentences covering:
- Overall strategy (offensive, defensive, balanced?)
- Biggest opportunity and biggest threat
- Any "if this then that" guidance
- Devil's Gate Uncomfortable Questions as food for thought

### 9. Gut Check (MANDATORY — never skip)
This is the most important section. Based on current conditions:

- **STAY THE COURSE** — normal conditions. Brief reassurance.
- **WATCH OUT: FEAR** — market is scary. "A 10% dip that gets sold is worse than a 20% dip that gets held."
- **WATCH OUT: GREED** — market is euphoric. "The best time to be careful is when everything feels easy."

When to use which:
- VIX >25 or scary headlines → FEAR
- Portfolio down >8% from peak → FEAR
- Market up >15% in short period → GREED
- None of the above → STAY THE COURSE

### 10. Alert Conditions
2-3 specific thresholds. If triggered → type `flash`.

### 11. Bottom Line
2-3 sentences. THE takeaway. THE action.

### 12. Disclaimer
One short paragraph. Educational purposes only. Not financial advice.

---

## Devil's Gate Integration
**The Devil's Gate summary MUST appear in the report.** Include it as a collapsed section or summary table after "What to Avoid":

```
### Validation Summary (Devil's Gate)
| Test | Result |
|------|--------|
| 0. Portfolio Reality | PASS |
| 1. Thesis Flip | PASS/FLAG |
| ... | ... |
| 7. Omission Audit | PASS |

**Status:** APPROVED / APPROVED WITH FLAGS
**Doomsday:** [1 sentence]
**Flags:** [list any flags with caveats]
```

Additionally:
- All FLAGS visible as caveats or risk notes in the report body
- Uncomfortable Questions woven into Biggest Risks or Chief's Corner
- Doomsday Scenario mentioned in Biggest Risks
- Conviction adjusted per Devil's Gate recommendations

**Why:** Devil's Gate is the investor's assurance that adversarial validation happened. If the summary isn't in the report, the investor has no way to verify analysis was stress-tested.

## After Every Report (MANDATORY)
1. Save as `reports/report_YYYY-MM-DD.md`
2. Run `python3 tools/html_report.py reports/report_YYYY-MM-DD.md` — **always generate HTML**
3. Run `python3 tools/thesis_tracker.py extract reports/report_YYYY-MM-DD.md` — **track theses**
4. Run `python3 tools/watchlist_extract.py reports/report_YYYY-MM-DD.md` — **track watchlist picks**
5. Run `python3 tools/scorer.py` — **performance scorecard**
6. Run `python3 tools/self_analyze.py` — **auto self-improve after every report** (saves to vault.db, auto-patches system files if issues found)
7. Open the HTML file so the investor can review it immediately

## After Every Trade
When the investor confirms they executed trades based on a report:
1. Create `trades/trade_YYYY-MM-DD.md` with:
   - Link to the source report
   - Exact executions (ticker, shares, price, total)
   - Capital deployed and remaining cash
   - Status: ACTIVE / CLOSED
2. Run `python3 tools/html_report.py trades/trade_YYYY-MM-DD.md` — **always generate HTML**
3. Update `portfolio.md` (only when the investor explicitly asks)
4. Performance data is auto-tracked in vault.db

**Reports are analysis. Trades are actions.** Not every report leads to a trade.

---

## Report Formats

### HTML (default — `report`)
After generating the Markdown report:
```bash
python3 tools/html_report.py reports/report_YYYY-MM-DD.md
```
Zero dependencies. Dark theme with print styles. Auto-colors BUY/SELL/HOLD and P&L.

### PDF (on demand — `report pdf`)
Follow the PDF rules in `system/00_system.md`. Key points:
- Generate Markdown first, then PDF via ReportLab
- Use Paragraph objects in all table cells
- Verify first page visually
- Don't iterate on layout. One render, one check, ship it.
- Analysis quality > layout polish > page count
- Requires `pip3 install reportlab`
