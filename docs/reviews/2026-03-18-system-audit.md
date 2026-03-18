# System Audit — 2026-03-18

## Overall: 6/10

The system works end-to-end and produces usable reports. But under the hood there are crash risks, silent data loss, and documentation contradictions that will bite you as the portfolio grows.

| Area | Score | Verdict |
|------|-------|---------|
| vault.py (CLI) | 5/10 | Missing primary commands, inconsistent error handling |
| db.py (Data Layer) | 7/10 | Solid schema, but silent exceptions and NULL crashes |
| Data Pipeline (fetcher/screener/scorer/alerts) | 5/10 | Multiple crash paths, stale data not detected |
| Smart Money / Thesis Tools | 6/10 | Fragile web scraping, silent failures everywhere |
| HTML Report Generator | 7/10 | Works but nested lists broken, theme docs wrong |
| System Documentation | 6/10 | Rules duplicated across 3 files, sizing contradictions |

**Total issues found: 120+ across all files.**

---

## Critical Issues (fix now) — 14 items

### Crash Bugs (will break on real usage)

1. **data_fetcher.py:498** — `total_value` and `total_cost` undefined if portfolio is empty. NameError crash.

2. **data_fetcher.py:125** — `isalpha()` rejects valid tickers with hyphens (BRK-B, BF-B). Silently drops holdings.

3. **data_fetcher.py:259** — Timezone-aware vs timezone-naive comparison in earnings calendar. Potential crash or wrong dates.

4. **scorer.py:201-202** — `max()`/`min()` on empty list crashes if no trades have return_pct.

5. **correlation.py:143** — KeyError if ticker missing from returns_map. Dimension mismatch in numpy array.

6. **alerts.py:361-364** — Assumes `trades` table has `stop_loss` column. No schema check. Crashes entire alert check.

7. **smart_money.py:128** — `fromisoformat()` on potentially None/malformed `cached_at`. ValueError crash.

8. **insider_check.py:695-696** — `int(shares)` on float without catching NaN/Infinity. Crash on bad SEC data.

### Missing Commands (documented but don't exist)

9. **vault.py** — `report`, `flash`, `analyze [TICKER]` are the 3 primary documented commands (CLAUDE.md lines 7-9). **None of them exist in the COMMANDS dict.** Users get "Unknown command" error. These are handled by Claude directly, not vault.py — but this is undocumented and confusing.

### Silent Data Loss

10. **db.py:1074-1075, 1125-1126, 1172-1173** — `except Exception: pass` in `cache_ark_trades()`, `cache_guru_holdings()`, `cache_news()`. If data insertion fails, caller never knows. Smart money data silently disappears.

11. **data_fetcher.py:186-195** — API failures return `{'error': str(e)}` dict. No logging. Impossible to debug which tickers failed and why.

12. **alerts.py:394** — Price defaults to `0` when not cached. Concentration calculation divides by zero or produces 0% allocation. **Stop-loss alerts silently skipped** (line 368).

### Logic Errors

13. **self_analyze.py:414** — Operator precedence bug: `if X and Y if Z else True` always evaluates True when "stop" not in line. Watchlist picks without stops are counted as having stops. **False positive in quality checks.**

14. **thesis_tracker.py:561** — `conviction_stars_to_level()` calls `.count("*")` but incoming data can be "HIGH"/"MEDIUM"/"LOW" text. All non-star convictions silently default to "LOW".

---

## Major Issues (fix soon) — 15 items

### Error Handling Gaps

15. **vault.py:182-183** — `portfolio update` doesn't catch ValueError on float conversion. `portfolio add` does (line 130). Inconsistent.

16. **vault.py:201** — `portfolio cash` same issue. No try-except on float conversion.

17. **vault.py:834** — `json.loads(e['meta'])` in journal command. No try-except for corrupted JSON. JSONDecodeError crash.

18. **db.py:1667, 1739** — `portfolio_dashboard()` LEFT JOIN returns NULL prices. Arithmetic on NULL → Python gets None → `mv / total_value` crashes. Fix with `COALESCE()`.

19. **screener.py:164-167, 351-361** — No error handling if `fetch_technicals()` fails or DB queries crash during screener report. Silent skips.

### Data Integrity

20. **db.py:942-955** — Race condition in `close_thesis()`. UPDATE then SELECT by date_closed DESC could return wrong row if multiple theses exist for same ticker.

21. **db.py:1489** — Duplicate `conn.commit()` call in `auto_cleanup()`. Harmless but wasteful.

22. **news.py:95, 121** — Timestamp defaults to Unix epoch (1970-01-01) if API field missing. Wrong publication dates stored in DB.

23. **data_fetcher.py:272-286** — `fetch_market_breadth()` can return None. Line 594 calls `.get()` on None → AttributeError.

### Documentation Contradictions

24. **CLAUDE.md:183 vs styles.css:9** — Docs promise "dark theme." CSS defines light gray (#fafafa) background. Users see light theme.

25. **00_system.md:142-145 vs 05_position_mgmt.md:170-177** — Conviction sizing: 00_system.md says 18% for `***` only "IF thesis passed all Devil's Gate tests." 05_position_mgmt.md presents it as unconditional. Which is truth?

26. **Entry zone rules duplicated in 3 files** — 00_system.md:160-163, 02_strategy.md:97-100, 03_devils_gate.md:67. Same thresholds, different wording. Maintenance nightmare.

27. **CLAUDE.md:199-212 AND 216-234** — Auto-learned rules listed twice with different formatting. Second copy has timestamp that goes stale.

28. **05_position_mgmt.md:31-35 vs sizing rules** — Stop-loss distances and position sizes aren't calibrated to each other. `***` at 18% size with 12% stop = 2.16% portfolio loss per trade. `*` at 7% with 7% stop = 0.49%. Hidden risk asymmetry.

29. **vault.py flow: cmd_flow_post_trade:1412** — Prints "REMINDER: Update portfolio.md" but CLAUDE.md says "auto-syncs portfolio.md". Contradicts DB-first architecture.

---

## Minor Issues (tech debt) — 12 items

30. **vault.py** — `sys.path.insert(0, SCRIPT_DIR)` called in 18+ functions. Should be done once at module level.

31. **vault.py** — Inconsistent error message formatting (`Error:`, `[BLOCK]`, `[!!]`, `[FAIL]`). No convention.

32. **vault.py:1267** — `cmd_flow_start` hardcodes `cmd_news_impact(['3'])`. Should parameterize.

33. **db.py:2348** — `calculate_position_size()` silently falls back to 12% for unknown conviction strings instead of raising error.

34. **db.py:427-429** — No schema versioning or migration strategy. Adding columns to existing tables will break silently.

35. **html_report.py:255,259** — Nested list rendering flattens 3+ levels of indentation. Multi-level lists render incorrectly.

36. **html_report.py:199-202** — Multi-line blockquotes truncated to single line.

37. **html_report.py:316-326** — `_convert_block()` doesn't support nested lists inside callout sections.

38. **news.py:78-91** — API key fallback reads from `api_keys.conf` (not in git). Two different implementations in news.py vs data_fetcher.py.

39. **correlation.py:41-73** — Falls back to parsing portfolio.md when DB read fails. Contradicts DB-first architecture.

40. **alerts.py:340-342** — ETF list hardcoded. Should read from DB `asset_type` field.

41. **02_strategy.md:119-122** — Cash allocation decision tree has no guidance for "VIX 15-25" neutral zone.

---

## What's Actually Good

- **DB schema is solid** — 21 tables, proper indices, WAL mode, foreign keys considered.
- **All documented DB methods exist** — API matches CLAUDE.md 100%.
- **Correlation matrix works well** — LOW risk score (avg 0.07) is accurate.
- **Self-analyze + auto-patching is clever** — System improves itself across reports.
- **Report pipeline produces Grade A output** — 9/9 audit consistently achievable.
- **Alert system design is sound** — Escalation levels, threshold-based, auto-checked.
- **Portfolio alpha tracking works** — +2.3% vs VOO in 8 days is real and verifiable.

---

## Recommendations (priority order)

### Week 1: Fix crash bugs
1. Fix items 1-8 (crash bugs). These will break during normal usage.
2. Fix item 13 (self_analyze logic error) — it's producing wrong quality scores.
3. Fix item 14 (thesis conviction parsing) — wrong conviction levels in DB.

### Week 2: Fix silent failures
4. Replace all `except Exception: pass` with logging (items 10-11).
5. Add COALESCE to portfolio_dashboard query (item 18).
6. Fix alerts price=0 default (item 12).

### Week 3: Documentation cleanup
7. Consolidate entry zone rules to single source (item 26).
8. Fix dark theme claim or implement dark CSS (item 24).
9. Clarify conviction sizing condition (item 25).
10. Remove duplicate auto-learned rules from CLAUDE.md (item 27).

### Later: Tech debt
11. Centralize sys.path.insert (item 30).
12. Add schema migration support (item 34).
13. Fix nested list rendering in HTML (item 35).
