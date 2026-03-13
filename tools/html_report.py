#!/usr/bin/env python3
"""
Vault Research Desk — HTML Report Generator
Converts a markdown report to a styled HTML file using external templates.

Usage:
    python3 tools/html_report.py reports/report_2026-03-11.md
    python3 tools/html_report.py trades/trade_2026-03-10.md
"""

import sys
import os
import re
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(SCRIPT_DIR, "templates")


def _load_template(name):
    path = os.path.join(TEMPLATES_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# --- Semantic section detection ---

# Sections that get callout treatment
CALLOUT_SECTIONS = {
    "gut check": "callout callout-warning",
    "doomsday": "callout callout-danger",
    "alert conditions": "callout callout-info",
    "uncomfortable questions": "callout callout-danger",
}

CALLOUT_LABELS = {
    "gut check": "Behavioral Check",
    "doomsday": "Stress Test",
    "alert conditions": "Watch List",
    "uncomfortable questions": "Devil's Advocate",
}

MARKET_SECTIONS = {"market snapshot"}


def markdown_to_html(md_text):
    """Convert markdown report to styled HTML."""

    lines = md_text.split("\n")
    html_parts = []
    i = 0

    # --- Extract header (first h1 + optional h2 subtitle) ---
    title = "Vault Research Desk"
    subtitle = ""
    header_consumed = False

    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("# ") and not stripped.startswith("## "):
            title = stripped[2:]
            i += 1
            # Check for subtitle (next non-empty line starting with ##)
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and lines[i].strip().startswith("## "):
                subtitle = lines[i].strip()[3:]
                i += 1
            header_consumed = True
            break
        else:
            break

    # Build header block
    brand = "Vault Research Desk"
    report_title = title.replace("Vault Research Desk — ", "").replace("Vault Research Desk —", "").strip()
    if not report_title:
        report_title = title

    html_parts.append('<div class="report-header">')
    html_parts.append(f'<h1>{_escape(brand)}</h1>')
    html_parts.append(f'<div class="title">{_escape(report_title)}</div>')
    if subtitle:
        html_parts.append(f'<div class="subtitle">{_escape(subtitle)}</div>')
    html_parts.append("</div>")

    # --- Process remaining lines ---
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip bare ---
        if re.match(r"^---+\s*$", stripped):
            i += 1
            continue

        # Heading
        if stripped.startswith("#"):
            level, heading_text = _parse_heading(stripped)
            section_key = heading_text.lower()

            # Check if this is a market data section
            if any(k in section_key for k in MARKET_SECTIONS):
                i += 1
                block, i = _collect_section_content(lines, i)
                html_parts.append(f'<h{level}>{_inline(heading_text)}</h{level}>')
                html_parts.append('<div class="market-data">')
                html_parts.append(_convert_block(block))
                html_parts.append("</div>")
                continue

            # Check if this is a callout section
            callout_class = None
            callout_label = None
            for key, cls in CALLOUT_SECTIONS.items():
                if key in section_key:
                    callout_class = cls
                    callout_label = CALLOUT_LABELS.get(key, "")
                    break

            if callout_class:
                i += 1
                block, i = _collect_section_content(lines, i)
                html_parts.append(f'<h{level}>{_inline(heading_text)}</h{level}>')
                html_parts.append(f'<div class="{callout_class}">')
                if callout_label:
                    html_parts.append(f'<span class="callout-label">{callout_label}</span>')
                html_parts.append(_convert_block(block))
                html_parts.append("</div>")
                continue

            # Regular heading
            html_parts.append(f'<h{level}>{_inline(heading_text)}</h{level}>')
            i += 1
            continue

        # Table
        if "|" in stripped and i + 1 < len(lines) and re.match(r"^\s*\|[\s\-:|]+\|", lines[i + 1]):
            table_lines = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                table_lines.append(lines[i])
                i += 1
            html_parts.append(_convert_table(table_lines))
            continue

        # Summary/total line
        if re.match(r"^(Total|Cash|Capital|Deployed)", stripped, re.IGNORECASE):
            html_parts.append(f'<div class="summary-line">{_inline(_escape(stripped))}</div>')
            i += 1
            continue

        # Status line
        if re.match(r"^Status:\s*(ACTIVE|CLOSED)", stripped, re.IGNORECASE):
            status = "ACTIVE" if "ACTIVE" in stripped.upper() else "CLOSED"
            css = "status-active" if status == "ACTIVE" else "status-closed"
            html_parts.append(f'<p>Status: <span class="{css}">{status}</span></p>')
            i += 1
            continue

        # Unordered list
        if re.match(r"^[-*] ", stripped):
            list_lines = []
            while i < len(lines) and re.match(r"^\s*[-*] ", lines[i]):
                list_lines.append(re.sub(r"^\s*[-*] ", "", lines[i]).strip())
                i += 1
            html_parts.append("<ul>")
            for item in list_lines:
                html_parts.append(f"<li>{_inline(_escape(item))}</li>")
            html_parts.append("</ul>")
            continue

        # Ordered list
        if re.match(r"^\d+\. ", stripped):
            list_lines = []
            while i < len(lines) and re.match(r"^\s*\d+\. ", lines[i]):
                list_lines.append(re.sub(r"^\s*\d+\.\s*", "", lines[i]).strip())
                i += 1
            html_parts.append("<ol>")
            for item in list_lines:
                html_parts.append(f"<li>{_inline(_escape(item))}</li>")
            html_parts.append("</ol>")
            continue

        # Code block
        if stripped.startswith("```"):
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(_escape(lines[i]))
                i += 1
            i += 1  # skip closing ```
            html_parts.append(f'<pre><code>{chr(10).join(code_lines)}</code></pre>')
            continue

        # Blockquote
        if stripped.startswith(">"):
            content = stripped.lstrip("> ").strip()
            html_parts.append(f"<blockquote>{_inline(_escape(content))}</blockquote>")
            i += 1
            continue

        # Empty line
        if not stripped:
            i += 1
            continue

        # Regular paragraph
        html_parts.append(f"<p>{_inline(_escape(stripped))}</p>")
        i += 1

    # Render into template
    body = "\n".join(html_parts)
    return _render_template(title, body)


def _escape(text):
    """Escape HTML entities."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def _inline(text):
    """Convert inline markdown (bold, italic, code) to HTML."""
    # Bold + italic
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic (single *)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    # Inline code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # Arrow →
    text = text.replace("→", "&rarr;")
    return text


def _parse_heading(line):
    """Return (level, text) from a markdown heading line."""
    match = re.match(r"^(#{1,4})\s+(.+)$", line)
    if match:
        return len(match.group(1)), match.group(2)
    return 2, line


def _collect_section_content(lines, start):
    """Collect lines until next heading or end of file."""
    block = []
    i = start
    while i < len(lines):
        if lines[i].strip().startswith("#"):
            break
        if re.match(r"^---+\s*$", lines[i].strip()):
            i += 1
            continue
        block.append(lines[i])
        i += 1
    return block, i


def _convert_block(lines):
    """Convert a block of markdown lines to HTML."""
    parts = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Table
        if "|" in stripped and i + 1 < len(lines) and re.match(r"^\s*\|[\s\-:|]+\|", lines[i + 1]):
            table_lines = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                table_lines.append(lines[i])
                i += 1
            parts.append(_convert_table(table_lines))
            continue

        # List
        if re.match(r"^[-*] ", stripped):
            list_lines = []
            while i < len(lines) and re.match(r"^\s*[-*] ", lines[i]):
                list_lines.append(re.sub(r"^\s*[-*] ", "", lines[i]).strip())
                i += 1
            parts.append("<ul>")
            for item in list_lines:
                parts.append(f"<li>{_inline(_escape(item))}</li>")
            parts.append("</ul>")
            continue

        if re.match(r"^\d+\. ", stripped):
            list_lines = []
            while i < len(lines) and re.match(r"^\s*\d+\. ", lines[i]):
                list_lines.append(re.sub(r"^\s*\d+\.\s*", "", lines[i]).strip())
                i += 1
            parts.append("<ol>")
            for item in list_lines:
                parts.append(f"<li>{_inline(_escape(item))}</li>")
            parts.append("</ol>")
            continue

        if not stripped:
            i += 1
            continue

        parts.append(f"<p>{_inline(_escape(stripped))}</p>")
        i += 1

    return "\n".join(parts)


def _convert_table(lines):
    """Convert markdown table lines to HTML table."""
    headers = [c.strip() for c in lines[0].split("|") if c.strip()]
    rows = []
    for line in lines[2:]:  # skip header + separator
        if "|" in line:
            cells = [c.strip() for c in line.split("|") if c.strip()]
            rows.append(cells)

    table = ['<div class="table-wrap"><table>']
    table.append("<thead><tr>")
    for h in headers:
        table.append(f"<th>{_escape(h)}</th>")
    table.append("</tr></thead>")
    table.append("<tbody>")

    for row in rows:
        table.append("<tr>")
        for j, cell in enumerate(row):
            css = _classify_cell(cell)
            display = _format_cell(cell)
            table.append(f"<td{css}>{display}</td>")
        for _ in range(len(headers) - len(row)):
            table.append("<td></td>")
        table.append("</tr>")

    table.append("</tbody></table></div>")
    return "\n".join(table)


def _classify_cell(cell):
    """Return CSS class for a table cell."""
    upper = cell.upper().strip()

    if upper in ("BUY", "BUY MORE", "BUY (ADD)"):
        return ' class="action-buy"'
    if upper in ("SELL", "TRIM"):
        return ' class="action-sell"'
    if upper == "HOLD":
        return ' class="action-hold"'
    if upper == "AVOID":
        return ' class="action-avoid"'

    if re.match(r"^[+]\$?\d", cell) or re.match(r"^\+\d", cell):
        return ' class="positive"'
    if re.match(r"^-\$?\d", cell) or re.match(r"^-\d", cell):
        return ' class="negative"'

    return ""


def _format_cell(cell):
    """Format cell content — conviction stars, inline markdown."""
    stripped = cell.strip()

    # Conviction: *** / ** / *
    if stripped == "***":
        return '<span class="conviction conviction-high">HIGH</span>'
    if stripped == "**":
        return '<span class="conviction conviction-med">MED</span>'
    if stripped == "*":
        return '<span class="conviction conviction-low">LOW</span>'

    return _inline(_escape(stripped))


def _render_template(title, body):
    """Load templates and assemble final HTML."""
    try:
        template = _load_template("base.html")
        styles = _load_template("styles.css")
    except FileNotFoundError as e:
        print(f"WARNING: Template not found ({e}), using minimal fallback.")
        return f"<!DOCTYPE html><html><head><title>{title}</title></head><body>{body}</body></html>"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = template.replace("{{title}}", _escape(title))
    html = html.replace("{{styles}}", styles)
    html = html.replace("{{body}}", body)
    html = html.replace("{{timestamp}}", timestamp)

    return html


def save_html_report(md_text, output_path):
    """Convert markdown to HTML and save to file."""
    html = markdown_to_html(md_text)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML report saved: {output_path}")
    return output_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tools/html_report.py <markdown_file.md>")
        print("Output: same path with .html extension")
        sys.exit(1)

    md_path = sys.argv[1]
    if not os.path.exists(md_path):
        print(f"ERROR: File not found: {md_path}")
        sys.exit(1)

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    html_path = md_path.rsplit(".", 1)[0] + ".html"
    save_html_report(md_text, html_path)


if __name__ == "__main__":
    main()
