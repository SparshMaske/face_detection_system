import os
from datetime import datetime
from glob import glob

from flask import current_app
from models.visitor import Visitor, VisitorSession
from sqlalchemy import or_
import cv2

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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

    def _resolve_visitor_image_path(self, visitor):
        upload_root = current_app.config.get('UPLOAD_FOLDER')
        visitor_root = current_app.config.get('VISITOR_UPLOAD_FOLDER')

        candidates = []
        # Prefer newest stored visitor image so event report uses the latest capture.
        images = sorted(visitor.images or [], key=lambda item: item.captured_at or datetime.min, reverse=True)
        for item in images:
            if item.image_path:
                candidates.append(item.image_path)
        if visitor.primary_image_path:
            candidates.append(visitor.primary_image_path)

        for raw_path in candidates:
            if not raw_path:
                continue

            # Support absolute file path records directly.
            if os.path.isabs(raw_path) and os.path.exists(raw_path):
                return raw_path

            normalized = raw_path.replace('\\', '/')
            if normalized.startswith('/'):
                normalized = normalized.lstrip('/')
            if normalized.startswith('static/'):
                normalized = normalized[len('static/'):]
            if normalized.startswith('uploads/'):
                normalized = normalized[len('uploads/'):]

            possible_paths = []
            if upload_root:
                possible_paths.append(os.path.join(upload_root, normalized))
            if visitor_root:
                possible_paths.append(os.path.join(visitor_root, os.path.basename(normalized)))
            possible_paths.append(os.path.join(self.visitor_reports_dir, 'snapshots', os.path.basename(normalized)))

            for abs_path in possible_paths:
                if abs_path and os.path.exists(abs_path):
                    return abs_path
        return None

    def _prepare_face_to_shoulder_snapshot(self, image_path, visitor_code):
        if not image_path or not os.path.exists(image_path):
            return image_path
        try:
            img = cv2.imread(image_path)
            if img is None:
                return image_path
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            cascade_path = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
            face_cascade = cv2.CascadeClassifier(cascade_path)
            if face_cascade.empty():
                return image_path

            faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(48, 48),
            )
            if len(faces) == 0:
                # Fallback crop when detector misses: centered portrait crop.
                img_h, img_w = img.shape[:2]
                crop_w = int(img_w * 0.64)
                crop_h = int(img_h * 0.82)
                nx1 = max(0, (img_w - crop_w) // 2)
                ny1 = max(0, int(img_h * 0.04))
                nx2 = min(img_w, nx1 + crop_w)
                ny2 = min(img_h, ny1 + crop_h)
                crop = img[ny1:ny2, nx1:nx2]
                if crop.size == 0:
                    return image_path

                snapshots_dir = os.path.join(self.visitor_reports_dir, 'snapshots')
                os.makedirs(snapshots_dir, exist_ok=True)
                snapshot_path = os.path.join(
                    snapshots_dir,
                    f"{visitor_code}_face_shoulder_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
                )
                cv2.imwrite(snapshot_path, crop)
                return snapshot_path

            x, y, w, h = max(faces, key=lambda face: face[2] * face[3])
            img_h, img_w = img.shape[:2]
            expand_x = int(w * 0.35)
            expand_y_top = int(h * 0.35)
            expand_y_bottom = int(h * 1.55)

            nx1 = max(0, x - expand_x)
            ny1 = max(0, y - expand_y_top)
            nx2 = min(img_w, x + w + expand_x)
            ny2 = min(img_h, y + h + expand_y_bottom)
            crop = img[ny1:ny2, nx1:nx2]
            if crop.size == 0:
                return image_path

            snapshots_dir = os.path.join(self.visitor_reports_dir, 'snapshots')
            os.makedirs(snapshots_dir, exist_ok=True)
            snapshot_path = os.path.join(
                snapshots_dir,
                f"{visitor_code}_face_shoulder_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
            )
            cv2.imwrite(snapshot_path, crop)
            return snapshot_path
        except Exception:
            return image_path

    def _latest_existing_snapshot(self, visitor_code):
        snapshots_dir = os.path.join(self.visitor_reports_dir, 'snapshots')
        if not os.path.isdir(snapshots_dir):
            return None
        patterns = [
            os.path.join(snapshots_dir, f"{visitor_code}_face_shoulder_*.jpg"),
            os.path.join(snapshots_dir, f"{visitor_code}_face_shoulder.jpg"),
        ]
        candidates = []
        for pattern in patterns:
            candidates.extend(glob(pattern))
        candidates = [path for path in candidates if os.path.exists(path)]
        if not candidates:
            return None
        candidates.sort(key=lambda path: os.path.getmtime(path), reverse=True)
        return candidates[0]

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

    def _build_event_visitors_with_reportlab(self, filepath, title_text, subtitle_text, visitors_payload):
        doc = SimpleDocTemplate(filepath, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        if not visitors_payload:
            elements.append(Paragraph(title_text, styles['Title']))
            elements.append(Paragraph(subtitle_text, styles['Normal']))
            elements.append(Spacer(1, 12))
            elements.append(Paragraph("No visitors found in selected window.", styles['Normal']))
            doc.build(elements)
            return

        def _card_for_visitor(item):
            body = []
            body.append(Paragraph(f"ID: {item['visitor_id']}", styles['Heading4']))
            body.append(Spacer(1, 4))

            detail_table = Table([
                ['Date', item['date']],
                ['First In', item['first_in']],
                ['Last Out', item['last_out']],
                ['Duration', item['duration']],
            ], colWidths=[58, 148])
            detail_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.35, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.whitesmoke, colors.beige]),
            ]))
            body.append(detail_table)
            body.append(Spacer(1, 5))

            image_path = item.get('snapshot_path')
            if image_path and os.path.exists(image_path):
                body.append(Image(image_path, width=106, height=132))
            else:
                body.append(Paragraph("Snapshot unavailable", styles['Italic']))

            card = Table([[body]], colWidths=[210])
            card.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), 0.7, colors.HexColor('#6b7280')),
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            return card

        page_size = 4
        for start in range(0, len(visitors_payload), page_size):
            if start > 0:
                elements.append(PageBreak())

            elements.append(Paragraph(title_text, styles['Title']))
            elements.append(Paragraph(subtitle_text, styles['Normal']))
            elements.append(Spacer(1, 10))

            chunk = visitors_payload[start:start + page_size]
            row_data = []
            current_row = []
            for item in chunk:
                current_row.append(_card_for_visitor(item))
                if len(current_row) == 2:
                    row_data.append(current_row)
                    current_row = []
            if current_row:
                current_row.append('')
                row_data.append(current_row)

            grid = Table(row_data, colWidths=[220, 220], hAlign='LEFT')
            grid.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            elements.append(grid)

        doc.build(elements)

    def _build_event_visitors_with_fpdf(self, filepath, title_text, subtitle_text, visitors_payload):
        pdf = FPDF()
        pdf.set_auto_page_break(auto=False)

        if not visitors_payload:
            pdf.add_page()
            pdf.set_font('Arial', 'B', 16)
            pdf.cell(0, 10, self._safe_text(title_text), ln=1)
            pdf.set_font('Arial', '', 11)
            pdf.cell(0, 8, self._safe_text(subtitle_text), ln=1)
            pdf.ln(6)
            pdf.set_font('Arial', '', 11)
            pdf.cell(0, 8, 'No visitors found in selected window.', ln=1)
            pdf.output(filepath)
            return

        page_index = -1
        for idx, visitor_item in enumerate(visitors_payload):
            slot = idx % 4
            if slot == 0:
                page_index += 1
                pdf.add_page()
                pdf.set_font('Arial', 'B', 15)
                pdf.cell(0, 9, self._safe_text(title_text), ln=1)
                pdf.set_font('Arial', '', 10)
                pdf.multi_cell(0, 5, self._safe_text(subtitle_text))
                pdf.ln(2)

            row = slot // 2
            col = slot % 2
            card_x = 10 + (col * 98)
            card_y = 30 + (row * 130)
            card_w = 92
            card_h = 122

            pdf.set_draw_color(108, 117, 125)
            pdf.rect(card_x, card_y, card_w, card_h)

            pdf.set_xy(card_x + 3, card_y + 4)
            pdf.set_font('Arial', 'B', 11)
            pdf.cell(card_w - 6, 6, self._safe_text(f"ID: {visitor_item['visitor_id']}"), ln=1)

            details = [
                f"Date: {visitor_item['date']}",
                f"First In: {visitor_item['first_in']}",
                f"Last Out: {visitor_item['last_out']}",
                f"Duration: {visitor_item['duration']}",
            ]
            pdf.set_font('Arial', '', 8)
            text_y = card_y + 12
            for line in details:
                pdf.set_xy(card_x + 3, text_y)
                pdf.multi_cell(card_w - 6, 4.3, self._safe_text(line))
                text_y = pdf.get_y() + 0.5

            image_path = visitor_item.get('snapshot_path')
            if image_path and os.path.exists(image_path):
                try:
                    image_w = 44
                    image_h = 54
                    image_x = card_x + (card_w - image_w) / 2
                    image_y = card_y + card_h - image_h - 4
                    pdf.image(image_path, x=image_x, y=image_y, w=image_w, h=image_h)
                except Exception:
                    pdf.set_xy(card_x + 3, card_y + card_h - 10)
                    pdf.set_font('Arial', 'I', 8)
                    pdf.cell(card_w - 6, 5, 'Snapshot unavailable', ln=1)
            else:
                pdf.set_xy(card_x + 3, card_y + card_h - 10)
                pdf.set_font('Arial', 'I', 8)
                pdf.cell(card_w - 6, 5, 'Snapshot unavailable', ln=1)

        pdf.output(filepath)

    def _build_visitor_with_reportlab(
        self,
        filepath,
        visitor_code,
        first_in,
        last_out,
        duration_text,
        capture_date_text,
        visitor_image_path,
    ):
        doc = SimpleDocTemplate(filepath, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph(f"Visitor ID: {visitor_code}", styles['Title']))
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
            elements.append(Image(visitor_image_path, width=180, height=230))
        doc.build(elements)

    def _build_visitor_with_fpdf(
        self,
        filepath,
        visitor_code,
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
        pdf.cell(0, 10, self._safe_text(f"Visitor ID: {visitor_code}"), ln=1)

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
            try:
                pdf.image(visitor_image_path, w=62)
            except Exception:
                pass

        pdf.output(filepath)

    def generate_pdf_report(self, start_date, end_date, report_type='daily', event_name=None, event_id=None):
        self._ensure_pdf_backend()
        safe_event_name = (event_name or '').strip().replace(' ', '_')
        if safe_event_name:
            filename = f"Visitor_Report_{safe_event_name}_{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        else:
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
                'sessions': 0,
            })
            item['sessions'] += 1
            if item['first_in'] is None or start < item['first_in']:
                item['first_in'] = start
            if item['last_out'] is None or end > item['last_out']:
                item['last_out'] = end

        visitors_payload = []
        if grouped:
            visitors = Visitor.query.filter(Visitor.id.in_(grouped.keys())).all()
            visitors_by_id = {v.id: v for v in visitors}
            ordered_visitor_ids = sorted(
                grouped.keys(),
                key=lambda vid: grouped[vid]['first_in'] or datetime.max,
            )
            display_id_map = {
                visitor_db_id: f"ID{idx}"
                for idx, visitor_db_id in enumerate(ordered_visitor_ids, start=1)
            }

            for visitor_db_id in ordered_visitor_ids:
                summary = grouped[visitor_db_id]
                visitor = visitors_by_id.get(visitor_db_id)
                visitor_code = display_id_map.get(visitor_db_id, f'ID{visitor_db_id}')
                canonical_code = visitor.visitor_id if visitor else f'VISITOR-{visitor_db_id}'
                first_in = summary['first_in']
                last_out = summary['last_out']
                snapshot_path = None
                if visitor is not None:
                    raw_path = self._resolve_visitor_image_path(visitor)
                    snapshot_path = self._prepare_face_to_shoulder_snapshot(raw_path, canonical_code)
                    if not snapshot_path or not os.path.exists(snapshot_path):
                        snapshot_path = self._latest_existing_snapshot(canonical_code)
                duration_seconds = 0
                if first_in and last_out:
                    duration_seconds = max(0, int((last_out - first_in).total_seconds()))

                visitors_payload.append({
                    'visitor_id': visitor_code,
                    'date': first_in.strftime('%Y-%m-%d') if first_in else '-',
                    'first_in': first_in.strftime('%Y-%m-%d %H:%M:%S') if first_in else '-',
                    'last_out': last_out.strftime('%Y-%m-%d %H:%M:%S') if last_out else '-',
                    'duration': self._format_duration(duration_seconds),
                    'snapshot_path': snapshot_path,
                })

        visitors_payload.sort(key=lambda item: item['first_in'])
        title_text = f"Visitor Report ({report_type.title()})"
        subtitle_text = f"Period: {start_date} to {end_date}"
        if event_name:
            subtitle_text = f"Event: {event_name} | {subtitle_text}"
        if event_id:
            subtitle_text = f"{subtitle_text} | Event ID: {event_id}"
        if REPORTLAB_AVAILABLE:
            self._build_event_visitors_with_reportlab(filepath, title_text, subtitle_text, visitors_payload)
        else:
            self._build_event_visitors_with_fpdf(filepath, title_text, subtitle_text, visitors_payload)

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
        duration_seconds = max(0, int((last_out - first_in).total_seconds()))
        duration_text = self._format_duration(duration_seconds)
        capture_date_text = first_in.strftime('%Y-%m-%d')
        visitor_image_path = self._resolve_visitor_image_path(visitor)
        visitor_image_path = self._prepare_face_to_shoulder_snapshot(visitor_image_path, visitor.visitor_id)
        if not visitor_image_path or not os.path.exists(visitor_image_path):
            visitor_image_path = self._latest_existing_snapshot(visitor.visitor_id)

        filename = f"{visitor.visitor_id}_report.pdf"
        filepath = os.path.join(self.visitor_reports_dir, filename)

        if REPORTLAB_AVAILABLE:
            self._build_visitor_with_reportlab(
                filepath,
                visitor.visitor_id,
                first_in,
                last_out,
                duration_text,
                capture_date_text,
                visitor_image_path,
            )
        else:
            self._build_visitor_with_fpdf(
                filepath,
                visitor.visitor_id,
                first_in,
                last_out,
                duration_text,
                capture_date_text,
                visitor_image_path,
            )
        return filepath
