"""docs/DEPLOY_WINDOWS.md -> dist/DEPLOY_WINDOWS.pdf 변환 스크립트

사용법: python scripts/build_guide_pdf.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, Preformatted,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_CENTER
import xml.sax.saxutils as saxutils

# ── Paths ──
BASE = Path(__file__).resolve().parent.parent
MD_PATH = BASE / "docs" / "DEPLOY_WINDOWS.md"
PDF_PATH = BASE / "dist" / "SPRi_Newsletter_Setup_Guide.pdf"
PDF_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── Korean font registration ──
FONT_DIR = Path("C:/Windows/Fonts")
FONT_REGULAR = FONT_DIR / "malgun.ttf"
FONT_BOLD = FONT_DIR / "malgunbd.ttf"

if not FONT_REGULAR.exists():
    print(f"[ERROR] {FONT_REGULAR} not found")
    sys.exit(1)

pdfmetrics.registerFont(TTFont("Malgun", str(FONT_REGULAR)))
pdfmetrics.registerFont(TTFont("MalgunBold", str(FONT_BOLD)))

# ── Styles ──
COLOR_PRIMARY = HexColor("#1a73e8")
COLOR_DARK = HexColor("#202124")
COLOR_GRAY = HexColor("#5f6368")
COLOR_CODE_BG = HexColor("#f8f9fa")
COLOR_WARN_BG = HexColor("#fef7e0")
COLOR_WARN_BORDER = HexColor("#f9ab00")

styles = {
    "title": ParagraphStyle(
        "Title", fontName="MalgunBold", fontSize=18, leading=24,
        textColor=COLOR_PRIMARY, spaceAfter=6,
    ),
    "subtitle": ParagraphStyle(
        "Subtitle", fontName="Malgun", fontSize=10, leading=14,
        textColor=COLOR_GRAY, spaceAfter=12,
    ),
    "h2": ParagraphStyle(
        "H2", fontName="MalgunBold", fontSize=14, leading=18,
        textColor=COLOR_DARK, spaceBefore=16, spaceAfter=8,
    ),
    "h3": ParagraphStyle(
        "H3", fontName="MalgunBold", fontSize=11, leading=15,
        textColor=COLOR_DARK, spaceBefore=10, spaceAfter=6,
    ),
    "body": ParagraphStyle(
        "Body", fontName="Malgun", fontSize=9.5, leading=14,
        textColor=COLOR_DARK, spaceAfter=4,
    ),
    "bullet": ParagraphStyle(
        "Bullet", fontName="Malgun", fontSize=9.5, leading=14,
        textColor=COLOR_DARK, leftIndent=16, spaceAfter=2,
        bulletIndent=6, bulletFontSize=9.5,
    ),
    "code": ParagraphStyle(
        "Code", fontName="Courier", fontSize=8.5, leading=12,
        textColor=HexColor("#333333"), backColor=COLOR_CODE_BG,
        leftIndent=8, rightIndent=8, spaceBefore=4, spaceAfter=4,
        borderPadding=(4, 6, 4, 6),
    ),
    "note": ParagraphStyle(
        "Note", fontName="Malgun", fontSize=9, leading=13,
        textColor=HexColor("#6a4f00"), leftIndent=10, spaceAfter=6,
    ),
    "table_header": ParagraphStyle(
        "TH", fontName="MalgunBold", fontSize=9, leading=12,
        textColor=HexColor("#ffffff"),
    ),
    "table_cell": ParagraphStyle(
        "TD", fontName="Malgun", fontSize=9, leading=12,
        textColor=COLOR_DARK,
    ),
}


def esc(text):
    """XML-escape text for ReportLab paragraphs."""
    return saxutils.escape(text)


def bold_wrap(text):
    """Convert **text** markdown bold to <b>text</b>."""
    import re
    text = esc(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # inline code
    text = re.sub(r'`([^`]+)`', r'<font face="Courier" size="8.5" color="#c7254e">\1</font>', text)
    # checkbox
    text = text.replace("[x]", "V").replace("[ ]", "O")
    return text


def parse_md_to_flowables(md_text):
    """Parse markdown text into ReportLab flowables."""
    flowables = []
    lines = md_text.split("\n")
    i = 0
    in_code_block = False
    code_lines = []
    in_table = False
    table_rows = []

    while i < len(lines):
        line = lines[i]

        # Code block toggle
        if line.strip().startswith("```"):
            if in_code_block:
                # End code block
                code_text = "\n".join(code_lines)
                if code_text.strip():
                    flowables.append(Preformatted(code_text, styles["code"]))
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            # End table if in one
            if in_table:
                flowables.extend(_build_table(table_rows))
                table_rows = []
                in_table = False
            i += 1
            continue

        # Horizontal rule
        if stripped == "---":
            if in_table:
                flowables.extend(_build_table(table_rows))
                table_rows = []
                in_table = False
            flowables.append(Spacer(1, 4))
            flowables.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#dadce0")))
            flowables.append(Spacer(1, 4))
            i += 1
            continue

        # Title (# )
        if stripped.startswith("# ") and not stripped.startswith("## "):
            flowables.append(Paragraph(bold_wrap(stripped[2:]), styles["title"]))
            i += 1
            continue

        # H2 (## )
        if stripped.startswith("## "):
            if in_table:
                flowables.extend(_build_table(table_rows))
                table_rows = []
                in_table = False
            flowables.append(Paragraph(bold_wrap(stripped[3:]), styles["h2"]))
            i += 1
            continue

        # H3 (### )
        if stripped.startswith("### "):
            flowables.append(Paragraph(bold_wrap(stripped[4:]), styles["h3"]))
            i += 1
            continue

        # Table row
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            # Skip separator row (|---|---|)
            if all(set(c) <= set("-: ") for c in cells):
                i += 1
                continue
            table_rows.append(cells)
            in_table = True
            i += 1
            continue

        # Blockquote / note
        if stripped.startswith("> "):
            note_text = bold_wrap(stripped[2:])
            flowables.append(Paragraph(note_text, styles["note"]))
            i += 1
            continue
        if stripped == ">":
            i += 1
            continue

        # Numbered list
        import re
        num_match = re.match(r'^(\d+)\.\s+(.+)', stripped)
        if num_match:
            num, text = num_match.groups()
            flowables.append(Paragraph(
                f"{num}. {bold_wrap(text)}", styles["bullet"]
            ))
            i += 1
            continue

        # Bullet list (- or *)
        if stripped.startswith("- ") or stripped.startswith("* "):
            text = stripped[2:]
            # Sub-bullet
            if line.startswith("   ") or line.startswith("\t"):
                flowables.append(Paragraph(
                    f"  - {bold_wrap(text)}",
                    ParagraphStyle("SubBullet", parent=styles["bullet"], leftIndent=32)
                ))
            else:
                flowables.append(Paragraph(
                    f"- {bold_wrap(text)}", styles["bullet"]
                ))
            i += 1
            continue

        # Regular paragraph
        flowables.append(Paragraph(bold_wrap(stripped), styles["body"]))
        i += 1

    # Flush remaining table
    if in_table:
        flowables.extend(_build_table(table_rows))

    return flowables


def _build_table(rows):
    """Build a ReportLab Table from parsed rows."""
    if not rows:
        return []

    # First row is header
    header = rows[0]
    data_rows = rows[1:] if len(rows) > 1 else []

    col_count = len(header)
    page_width = A4[0] - 30 * mm
    col_width = page_width / col_count

    table_data = []
    # Header
    table_data.append([
        Paragraph(bold_wrap(cell), styles["table_header"])
        for cell in header
    ])
    # Data
    for row in data_rows:
        # Pad row if needed
        while len(row) < col_count:
            row.append("")
        table_data.append([
            Paragraph(bold_wrap(cell), styles["table_cell"])
            for cell in row[:col_count]
        ])

    t = Table(table_data, colWidths=[col_width] * col_count)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#ffffff")),
        ("BACKGROUND", (0, 1), (-1, -1), HexColor("#ffffff")),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dadce0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#ffffff"), HexColor("#f8f9fa")]),
    ]))

    return [Spacer(1, 4), t, Spacer(1, 8)]


def build_pdf():
    md_text = MD_PATH.read_text(encoding="utf-8")

    doc = SimpleDocTemplate(
        str(PDF_PATH),
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="SPRi Newsletter Setup Guide",
        author="SPRi Newsletter Team",
    )

    flowables = parse_md_to_flowables(md_text)
    doc.build(flowables)
    print(f"PDF generated: {PDF_PATH}")
    print(f"Size: {PDF_PATH.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    build_pdf()
