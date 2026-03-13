# Phase 1: Research

## Purpose
Collect real data, assess the macro environment, identify which sectors and assets are positioned to win or lose, and gauge market fear/greed. This phase answers: **What is happening, and what does it mean?**

## Inputs
- `tools/data_fetcher.py` output (prices, technicals, macro data, market breadth)
- `tools/screener.py` output (if available — ranked candidates with technical signals)
- Web searches for qualitative context (geopolitical developments, policy changes, breaking news)
- Previous report (if exists) for continuity

## Execution

### Step 1: Run tools/data_fetcher.py
```bash
python3 tools/data_fetcher.py
```
This gives you verified prices, moving averages, RSI, sector performance, VIX, macro indicators, and market breadth. Use these numbers — do not override them with guesses.

If a screener scan is available (`tools/screener_output.csv`), review it for BUY candidates with strong technical signals. Screener output supplements — does not replace — your own analysis.

### Step 2: Web Searches for Context
Search for what tools/data_fetcher.py can't provide:
- Top geopolitical headlines affecting markets
- Latest Fed commentary / FOMC expectations
- Any breaking news since last report
- Upcoming earnings for portfolio holdings and BUY candidates

Only search for what you need. Don't run 15 searches when 5 will do.

### Step 3: Produce Research Output

---

## What You Produce

### 1. Market Regime (1 sentence)
Label the current environment. Examples:
- "Geopolitical crisis with stagflationary risk — oil-supply-shock-driven"
- "Late-cycle expansion with cooling inflation — goldilocks zone"
- "Risk-off correction within a bull market — technically driven"

Include what would change your mind: "This shifts to [X] if [specific data point]."

### 2. Key Drivers (top 3-5, ranked)
Each driver must have:
- A specific data point (not "oil is up" but "WTI at $97, up 12% this month")
- A transmission channel ("oil $97 → gas $3.80 → consumer spending drops → XLY earnings miss")
- Whether this is NOISE (one-day event) or SIGNAL (regime-level shift)

### 3. Economic Data Snapshot
Table format:
| Indicator | Reading | Expectation | What It Means |
Only include data points with verified numbers. Skip anything you can't verify.

### 4. Sector Ranking (simplified)
Rank all 11 GICS sectors from strongest to weakest. One line each.
- Use sector ETF performance data from tools/data_fetcher.py
- Top 3 sectors: name specific stocks driving performance
- Bottom 3 sectors: name what's hurting them
- Flag any sector divergence (should be up but isn't — that's a signal)

DO NOT produce a full deep-dive on each sector. Just the ranking with 1-line rationale.

### 5. Sentiment Read
Based on what you CAN verify:
- VIX level and trend (from tools/data_fetcher.py)
- Market breadth: % of S&P above 50 DMA, 200 DMA (from tools/data_fetcher.py — included in standard output)
- General tone from news/headlines (qualitative)
- Contrarian signal: is fear or greed at an extreme?

**Do not fabricate put/call ratios, fund flow numbers, or Fear & Greed Index scores unless you find them in a specific source you can cite.**

Label: FEAR / GREED / NEUTRAL. And whether it's a contrarian signal or not.

### 6. This Week Calendar
| Day | Event | Why It Matters |
Only events that could actually move prices. 5 max.

### 7. Portfolio Context (if portfolio.md has holdings)
For each holding: is the current environment helping or hurting this position? One sentence each.

---


<!-- AUTO-FIX: VERIFICATION REMINDER -->
**DATA CITATION RULE (auto-added by self-analyze):**
Every price mentioned in the report must reference its source: "(data_fetcher.py)" or "(web search YYYY-MM-DD)". Past reports had 34 price mentions without verification reference.



<!-- PRO-INSIGHT: BUSINESS CYCLE MAPPING -->
**BUSINESS CYCLE SECTOR MAPPING (learned from pro analysis):**
In Market Regime section, identify current business cycle stage:
| Cycle Stage | Characteristics | Historically Strong Sectors |
|------------|----------------|---------------------------|
| Early expansion | Recovery, low rates, rising confidence | Financials, Consumer Discretionary, Industrials |
| Mid expansion | Steady growth, rising earnings | Technology, Industrials, Materials |
| Late expansion | Peak growth, rising inflation | Energy, Materials, Healthcare |
| Contraction | Falling growth, defensive rotation | Utilities, Consumer Staples, Healthcare |

Map current stage -> sector recommendations should align with historical patterns.
*Source: Top-performing funds use sector rotation aligned with business cycle.*

## Rules
- Lead with DATA, not narrative. Numbers first, interpretation second.
- Be specific about transmission channels. "Oil up → bad" is lazy. Spell out the chain.
- Distinguish NOISE from SIGNAL.
- If you're uncertain about probabilities, say so. Don't manufacture false confidence.
- The "This Week" calendar is mandatory every report.
- Keep the full research output under 800 words. Concise > comprehensive.

## Checkpoint
Post in chat: "Regime: [label]. Top driver: [data point]. VIX: [number]. Sector #1: [X]. Sector #11: [X]."
