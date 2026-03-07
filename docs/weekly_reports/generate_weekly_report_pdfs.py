from pathlib import Path
from fpdf import FPDF

BASE = Path('/Users/sparshmaske/Desktop/venv/face_detection_system/docs/weekly_reports')

class ReportPDF(FPDF):
    pass


def safe_text(s: str) -> str:
    # pyfpdf default fonts support latin-1 only
    return s.encode('latin-1', 'replace').decode('latin-1')


def render_markdown_to_pdf(md_path: Path, pdf_path: Path):
    lines = md_path.read_text(encoding='utf-8').splitlines()

    pdf = ReportPDF(format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()

    for raw in lines:
        line = raw.rstrip()

        if not line:
            pdf.ln(3)
            continue

        if line.startswith('# '):
            pdf.set_font('Arial', 'B', 17)
            pdf.multi_cell(0, 10, safe_text(line[2:].strip()), align='C')
            pdf.ln(2)
            continue

        if line.startswith('## '):
            pdf.set_font('Arial', 'B', 13)
            pdf.multi_cell(0, 8, safe_text(line[3:].strip()))
            pdf.ln(1)
            continue

        if line.startswith('### '):
            pdf.set_font('Arial', 'B', 11)
            pdf.multi_cell(0, 7, safe_text(line[4:].strip()))
            continue

        if line.startswith('- '):
            pdf.set_font('Arial', '', 11)
            pdf.multi_cell(0, 7, safe_text(f"- {line[2:].strip()}"))
            continue

        pdf.set_font('Arial', '', 11)
        pdf.multi_cell(0, 7, safe_text(line))

    pdf.output(str(pdf_path))


def main():
    md_files = sorted(BASE.glob('Week_*_Progress_Report.md'))
    if not md_files:
        print('No markdown reports found.')
        return

    for md in md_files:
        out = md.with_suffix('.pdf')
        render_markdown_to_pdf(md, out)
        print(f'Generated: {out}')


if __name__ == '__main__':
    main()
