import os
from datetime import datetime

from flask import current_app
from models.visitor import Visitor, VisitorSession
from sqlalchemy import or_

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    REPORTLAB_AVAILABLE = True
except ModuleNotFoundError:
    REPORTLAB_AVAILABLE = False

try:
    from fpdf import FPDF
except ModuleNotFoundError:
    FPDF = None

class ReportGenerator:
    def __init__(self):
        self.reports_dir = current_app.config['REPORTS_FOLDER']
        os.makedirs(self.reports_dir, exist_ok=True)
        self.visitor_reports_dir = os.path.join(self.reports_dir, 'visitors')
        os.makedirs(self.visitor_reports_dir, exist_ok=True)

    @staticmethod
    def _safe_text(value):
        if value is None:
            return ''
        text = str(value)
        return text.encode('latin-1', 'replace').decode('latin-1')

    @staticmethod
    def _ensure_pdf_backend():
        if REPORTLAB_AVAILABLE:
            return
        if FPDF is None:
            raise ModuleNotFoundError('No PDF backend installed (reportlab/fpdf)')

    @staticmethod
    def _parse_datetime(value, is_end=False):
        if not value:
            raise ValueError('Date is required')
        parsed = datetime.fromisoformat(value)
        # If only a date is provided for end bound, include full day.
        if is_end and len(value) <= 10:
            parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        return parsed

    @staticmethod
    def _format_duration(seconds):
        total = max(0, int(seconds or 0))
        hours, remainder = divmod(total, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _build_summary_with_reportlab(self, filepath, title_text, subtitle_text, rows):
        doc = SimpleDocTemplate(filepath, pagesize=A4)
        elements = []
        styles = getSampleStyleSheet()

        elements.append(Paragraph(title_text, styles['Title']))
        elements.append(Paragraph(subtitle_text, styles['Normal']))
        elements.append(Spacer(1, 12))

        table = Table(rows)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 0.75, colors.black),
        ]))
        elements.append(table)
        doc.build(elements)

    def _build_summary_with_fpdf(self, filepath, title_text, subtitle_text, rows):
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=12)
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, self._safe_text(title_text), ln=1)
        pdf.set_font('Arial', '', 11)
        pdf.cell(0, 8, self._safe_text(subtitle_text), ln=1)
        pdf.ln(3)

        col_count = max(1, len(rows[0]) if rows else 1)
        usable_width = 190
        col_width = usable_width / col_count

        for row_idx, row in enumerate(rows):
            if row_idx == 0:
                pdf.set_font('Arial', 'B', 10)
            else:
                pdf.set_font('Arial', '', 10)
            for cell in row:
                pdf.cell(col_width, 8, self._safe_text(cell), border=1, ln=0)
            pdf.ln(8)

        pdf.output(filepath)

    def _build_visitor_with_reportlab(
        self,
        filepath,
        first_in,
        last_out,
        duration_text,
        capture_date_text,
        visitor_image_path,
    ):
        doc = SimpleDocTemplate(filepath, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph("Visitor Presence Report", styles['Title']))
        elements.append(Spacer(1, 8))

        summary_table = Table([
            ['Date', capture_date_text],
            ['First In Time', first_in.strftime('%Y-%m-%d %H:%M:%S')],
            ['Last Out Time', last_out.strftime('%Y-%m-%d %H:%M:%S')],
            ['Total Duration', duration_text],
        ], colWidths=[150, 280])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.whitesmoke, colors.beige]),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 14))

        if visitor_image_path and os.path.exists(visitor_image_path):
            elements.append(Paragraph("Visitor Snapshot (Face to Shoulder)", styles['Heading3']))
            elements.append(Spacer(1, 8))
            elements.append(Image(visitor_image_path, width=180, height=230))
        doc.build(elements)

    def _build_visitor_with_fpdf(
        self,
        filepath,
        first_in,
        last_out,
        duration_text,
        capture_date_text,
        visitor_image_path,
    ):
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=12)
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, 'Visitor Presence Report', ln=1)

        pdf.set_font('Arial', 'B', 10)
        summary_rows = [
            ('Date', capture_date_text),
            ('First In Time', first_in.strftime('%Y-%m-%d %H:%M:%S')),
            ('Last Out Time', last_out.strftime('%Y-%m-%d %H:%M:%S')),
            ('Total Duration', duration_text),
        ]
        for key, value in summary_rows:
            pdf.cell(45, 8, self._safe_text(key), border=1)
            pdf.cell(130, 8, self._safe_text(value), border=1, ln=1)

        if visitor_image_path and os.path.exists(visitor_image_path):
            pdf.ln(8)
            pdf.set_font('Arial', 'B', 11)
            pdf.cell(0, 8, 'Visitor Snapshot (Face to Shoulder)', ln=1)
            try:
                pdf.image(visitor_image_path, w=62)
            except Exception:
                pass

        pdf.output(filepath)

    def generate_pdf_report(self, start_date, end_date, report_type='daily'):
        self._ensure_pdf_backend()
        filename = f"Visitor_Report_{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        filepath = os.path.join(self.reports_dir, filename)

        s_date = self._parse_datetime(start_date, is_end=False)
        e_date = self._parse_datetime(end_date, is_end=True)
        if e_date < s_date:
            raise ValueError('end_date must be on/after start_date')

        sessions = VisitorSession.query.filter(
            VisitorSession.entry_time <= e_date,
            or_(VisitorSession.exit_time.is_(None), VisitorSession.exit_time >= s_date),
        ).order_by(VisitorSession.entry_time.asc()).all()

        grouped = {}
        now_local = datetime.now()
        for session in sessions:
            visitor_id = session.visitor_id
            start = max(session.entry_time, s_date)
            end = min(session.exit_time or now_local, e_date)
            if end < start:
                continue
            item = grouped.setdefault(visitor_id, {
                'first_in': None,
                'last_out': None,
                'duration': 0,
                'sessions': 0,
            })
            item['sessions'] += 1
            item['duration'] += (end - start).total_seconds()
            if item['first_in'] is None or start < item['first_in']:
                item['first_in'] = start
            if item['last_out'] is None or end > item['last_out']:
                item['last_out'] = end

        data = [['Visitor ID', 'First In', 'Last Out', 'Duration', 'Sessions']]
        if not grouped:
            data.append(['-', 'No records found', '-', '-', '-'])
        else:
            visitors = Visitor.query.filter(Visitor.id.in_(grouped.keys())).all()
            visitors_by_id = {v.id: v for v in visitors}
            for visitor_db_id, summary in grouped.items():
                visitor = visitors_by_id.get(visitor_db_id)
                visitor_code = visitor.visitor_id if visitor else f'VISITOR-{visitor_db_id}'
                row = [
                    visitor_code,
                    summary['first_in'].strftime('%Y-%m-%d %H:%M:%S') if summary['first_in'] else '-',
                    summary['last_out'].strftime('%Y-%m-%d %H:%M:%S') if summary['last_out'] else '-',
                    self._format_duration(summary['duration']),
                    str(summary['sessions']),
                ]
                data.append(row)
        
        title_text = f"Visitor Report ({report_type.title()})"
        subtitle_text = f"Period: {start_date} to {end_date}"
        if REPORTLAB_AVAILABLE:
            self._build_summary_with_reportlab(filepath, title_text, subtitle_text, data)
        else:
            self._build_summary_with_fpdf(filepath, title_text, subtitle_text, data)

        return filepath

    def generate_visitor_pdf(self, visitor, event_start=None, event_end=None):
        self._ensure_pdf_backend()
        if visitor is None:
            raise ValueError('visitor is required')

        sessions = VisitorSession.query.filter_by(visitor_id=visitor.id).order_by(VisitorSession.entry_time.asc()).all()
        if not sessions:
            raise ValueError('No sessions found for visitor')

        now_local = datetime.now()
        normalized_sessions = []
        for session in sessions:
            in_time = session.entry_time
            out_time = session.exit_time or visitor.last_seen or now_local
            if event_start:
                in_time = max(in_time, event_start)
            if event_end:
                out_time = min(out_time, event_end)
            if out_time < in_time:
                continue
            normalized_sessions.append((in_time, out_time, bool(session.exit_time)))

        if not normalized_sessions:
            raise ValueError('No session data found in selected event window')

        first_in = min(item[0] for item in normalized_sessions)
        last_out = max(item[1] for item in normalized_sessions)
        duration_seconds = sum(max(0, int((out - inn).total_seconds())) for inn, out, _ in normalized_sessions)
        duration_text = self._format_duration(duration_seconds)
        capture_date_text = first_in.strftime('%Y-%m-%d')
        upload_root = current_app.config.get('UPLOAD_FOLDER')
        visitor_image_path = os.path.join(upload_root, visitor.primary_image_path) if (upload_root and visitor.primary_image_path) else None

        filename = f"{visitor.visitor_id}_report.pdf"
        filepath = os.path.join(self.visitor_reports_dir, filename)

        if REPORTLAB_AVAILABLE:
            self._build_visitor_with_reportlab(
                filepath,
                first_in,
                last_out,
                duration_text,
                capture_date_text,
                visitor_image_path,
            )
        else:
            self._build_visitor_with_fpdf(
                filepath,
                first_in,
                last_out,
                duration_text,
                capture_date_text,
                visitor_image_path,
            )
        return filepath
