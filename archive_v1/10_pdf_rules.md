# PDF Report Generation Rules

## Execution Requirement
This file is referenced by the execution protocol (`00_execution_protocol.md`) at Step 6b. When the `report pdf` command is used, these rules are MANDATORY. The visual verification step (render → pdftoppm → view ONE page) must be completed before presenting the PDF to Pavlo. A broken PDF is never acceptable — but a well-formatted 3-page PDF is always better than wasting 10 minutes fighting to squeeze into 2 pages.

## Overview
When generating PDF reports with `report pdf`, follow these rules to prevent broken layouts. These rules were learned from real failures and must be followed every time.

**PRIORITY ORDER:** Analysis quality > Readability > Information density > Layout polish > Page count. Never sacrifice the first three for the last two.

---

## Table Rules (Most Common Failure Point)

### 1. ALWAYS use Paragraph objects inside table cells
Never put raw strings in table cells. Raw strings don't wrap and will overflow/overlap.

```python
# WRONG — text overflows and overlaps neighboring columns
['XLE', '***', '$53-57', 'Oil crisis = energy profits. Hormuz disrupted.', '15-20%\n~$120']

# RIGHT — text wraps cleanly within the cell
[Paragraph('<b>XLE</b><br/>Energy ETF', tc_bold), Paragraph('***', tc), 
 Paragraph('$53-57', tc), Paragraph('Oil crisis = energy profits. Hormuz disrupted.', tc), 
 Paragraph('15-20%<br/>~$120', tc)]
```

### 2. Column widths must account for content
- The "Why" column needs the most space (3.0-3.5 inches minimum)
- Ticker column: ~0.85 inch
- Rating/Confidence column: ~0.55 inch (NOT 0.45 — "Rating" wraps at 0.45)
- Entry column: ~0.7 inch
- Stop column: ~0.55 inch
- Size column: ~0.85 inch
- All column widths must sum to CONTENT_W (page width minus margins)
- **TEST HEADER FIT:** After choosing widths, mentally check that every header label fits on one line. Short words like "Rating", "Entry", "Stop", "Size" need at least 0.55 inch. If a header wraps to two lines, widen that column.

### 3. Use KeepTogether for critical tables
Wrap important tables in `KeepTogether()` so they don't split across pages mid-row.

```python
from reportlab.platypus import KeepTogether
story.append(KeepTogether([table_object]))
```

**CAUTION with KeepTogether on the last section:** If the last block (e.g., Bottom Line + Disclaimer) is wrapped in KeepTogether but can't fit on the current page, it pushes the ENTIRE block to a new page, creating a mostly-empty page before it. For end-of-report content, let it flow naturally instead.

### 4. Use line breaks, not newlines in table cells
In Paragraph objects inside cells, use `<br/>` not `\n` for multi-line content.

---

## Page Length Rules

### 5. Let content dictate length — minimum pages, not maximum
- **Do NOT target a specific page count.** Let the analysis fill however many pages it needs.
- Use readable font sizes and comfortable spacing. The report should be pleasant to read, not cramped.
- If the report is 2 pages, great. If it's 4 pages during a crisis, that's also fine.
- **NEVER spend more than ONE layout iteration.** If the first render is readable and tables aren't broken, ship it. Don't re-render to save half a page.
- The only layout failure is: unreadable text, broken tables, or missing sections. Page count is NOT a failure mode.

### 6. Use comfortable, readable spacing
These are the TESTED values that produce natural-looking reports. Use them as-is.

| Element | Font Size | Leading | Space Before | Space After |
|---------|-----------|---------|-------------|-------------|
| Title | 22pt | 26 | 0 | 4 |
| Subtitle | 10pt | default | 0 | 10 |
| H1 (first on page, after subtitle) | 13pt | default | 2 | 5 |
| H1 (standard) | 13pt | default | 14 | 5 |
| H1 (compact, for last 2 sections) | 13pt | default | 10 | 4 |
| H2 | 10.5pt | default | 8 | 4 |
| Body | 9pt | 12 | 0 | 4 |
| Alert text | 9pt | 12 | 0 | 4 |
| Table cells | 8.5pt | 11 | - | - |
| Small/disclaimer | 7.5pt | 9 | 0 | 3 |

**KEY SPACING RULES:**
- **Title MUST have explicit `leading=26`.** Without it, the subtitle text overlaps the title at 22pt font size. The default leading for 22pt is too tight.
- **The first H1 after the subtitle uses `spaceBefore=2`**, not the standard 14. The subtitle's `spaceAfter=10` already provides the gap. Using the standard 14 creates a double-gap that looks wrong.
- **The last 2 sections (Alert Conditions, Bottom Line) use `spaceBefore=10`** to save vertical space at the end and avoid pushing the disclaimer onto a nearly-empty final page.
- **H1 spaceBefore=14 is the "breathing room" value.** This is what creates the visual separation between sections. Do NOT reduce below 12 — it makes sections feel cramped and run together.
- **H1 spaceAfter=5 is the "header-to-body" gap.** This is the space between a section title and its first paragraph. Do NOT reduce below 4 — the header looks glued to the text.
- **Body spaceAfter=4 is the "paragraph gap."** This separates consecutive paragraphs within a section. Do NOT reduce below 3 — prose becomes a wall of text.

### 7. Margins
- Top/bottom: 0.5 inch
- Left/right: 0.7 inch
- Content width = page width - left margin - right margin

---

## Visual Verification (MANDATORY but FAST)

### 8. Render and spot-check the PDF before presenting
After generating the PDF:
1. Convert to images: `pdftoppm -jpeg -r 150 report.pdf page`
2. View the FIRST page image with the `view` tool to confirm tables render correctly
3. Quick check for:
   - Text overflow/overlap in tables
   - Tables split across pages mid-row (ugly splits)
   - Missing content or cut-off text
   - **Title/subtitle overlap** (most common — check that subtitle sits clearly below the title)
   - **Column headers wrapping** (check that short words like "Rating" fit on one line)
   - **Orphan disclaimer** (disclaimer alone on a final page = bad; fix by using compact H1 on last 2 sections)
4. If tables are broken, fix and re-render ONCE. If they're fine, ship it.

**Do NOT re-render just because:**
- The last page has some whitespace
- A section ended up on a different page than expected
- The report is "one page too long"

### 9. The "3-second scan" test
Every table should be readable in 3 seconds. If you squint at the page image and can't distinguish columns, the table is broken. That's the ONLY visual test that matters.

---

## Typography Rules

### 10. Asterisks for confidence, not unicode stars
Use `***`, `**`, `*` — never unicode star characters (★, ☆). They render as black boxes in reportlab's built-in fonts.

### 11. No unicode subscripts/superscripts
Use `<sub>` and `<super>` tags in Paragraph objects. Unicode versions render as black boxes.

### 12. Use `--` for dashes, not em-dash unicode
The `—` character may not render in all fonts. Use `--` which is safe.

### 12b. Escape ampersands in Paragraph text
ReportLab Paragraph objects use XML. The `&` character must be escaped as `&amp;` — otherwise "S&P 500" renders as "S&P; 500" or breaks entirely. Always write `S&amp;P 500` in Paragraph strings.

---

## Table Styling Standard

### 13. Consistent table style across all reports
```python
std_table_style = [
    ('BACKGROUND', (0,0), (-1,0), HexColor('#e0e0e8')),   # Light gray header (visible in all viewers)
    ('TEXTCOLOR', (0,0), (-1,0), HexColor('#1a1a2e')),     # Dark header text
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),          # Bold header text
    ('LINEBELOW', (0,0), (-1,0), 1.5, HexColor('#1a1a2e')),# Dark underline below header
    ('GRID', (0,0), (-1,-1), 0.5, HexColor('#cccccc')),    # Light gray grid
    ('ROWBACKGROUNDS', (0,1), (-1,-1), [white, HexColor('#f8f8f8')]),  # Alternating rows
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('TOPPADDING', (0,0), (-1,-1), 5),
    ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ('LEFTPADDING', (0,0), (-1,-1), 6),
    ('RIGHTPADDING', (0,0), (-1,-1), 6),
]
```

**WHY NOT dark background + white text:** The previous style (`#1a1a2e` background + white text) rendered as invisible headers in many PDF viewers. The light header with dark text + bold underline is universally readable.

---

## Content Order in PDF

### 14. Follow the exact report structure from 07_report_writer.md
1. Title + date
2. What's Happening (prose)
3. This Week (table)
4. Changes Since Last Report
5. Your Portfolio (table, if holdings exist)
6. What to Buy (table)
7. What to Avoid (prose)
8. Biggest Risks (prose + Devil's Gate questions)
9. Chief's Corner (prose)
10. Gut Check (behavioral coaching — NEVER skip)
11. Alert Conditions (red text for emphasis)
12. Bottom Line (bold)
13. Disclaimer (small gray text at bottom)

---

## Known Layout Pitfalls (learned from real failures)

### 15. Title/subtitle overlap
The title at 22pt MUST have `leading=26` explicitly set. Without it, reportlab's default leading is too tight and the subtitle renders on top of the title text. This was the #1 visual bug in the March 10 report.

### 16. Column header wrapping
Short column headers like "Conf.", "Rating", "Stop" can wrap to two lines if the column is too narrow. Always use at least 0.55 inch for any column with a 5+ character header. The "Conf." → "Conf" + "." bug happened at 0.45 inch.

### 17. Orphan disclaimer on empty final page
When the Bottom Line paragraph ends near the bottom of a page, the disclaimer (3-4 lines) can spill onto a new page that's 95% empty. Fixes in order of preference:
1. Use compact H1 (`spaceBefore=10`) for Alert Conditions and Bottom Line sections
2. Shorten the Bottom Line text slightly
3. Accept the 3rd page — per rule 5, page count is not a failure mode

**Do NOT use KeepTogether on the Bottom Line + Disclaimer block** — if it can't fit, KeepTogether pushes the ENTIRE block to a new page, making the problem worse.

### 18. First H1 double-gap
When the subtitle has `spaceAfter=10` and the first H1 has `spaceBefore=14`, the combined 24pt gap is too large. Use a special first-H1 style with `spaceBefore=2` for the first section heading after the subtitle.

---

## Pre-Delivery Checklist

Before presenting the PDF to Pavlo:

- [ ] Every table uses Paragraph objects in cells (no raw strings)
- [ ] Column widths sum to content width
- [ ] Column headers fit on one line (check visually)
- [ ] Title and subtitle are clearly separated (no overlap)
- [ ] Tables don't split awkwardly mid-row across pages
- [ ] PDF was visually spot-checked (view first page via pdftoppm)
- [ ] All confidence levels use asterisks `***` not unicode
- [ ] Gut Check section is present
- [ ] Alert Conditions are present
- [ ] Disclaimer is at the bottom, not scattered
- [ ] All prices come from today's web search, not memory
- [ ] No orphan disclaimer on a nearly-empty final page

**NOT on the checklist (do NOT waste time on):**
- Exact page count
- Whitespace on the last page (some is fine)
- Re-rendering to tighten spacing beyond the values in this file
- Pixel-perfect layout alignment
