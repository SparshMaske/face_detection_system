import os
from datetime import datetime
from flask import request, jsonify, send_file, current_app
from flask_jwt_extended import jwt_required
from routes import reports_bp
from models.visitor import Visitor

@reports_bp.route('/generate', methods=['POST'])
@jwt_required()
def generate_report():
    data = request.get_json() or {}
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')
    report_type = data.get('report_type', 'daily')
    event_id = (data.get('event_id') or '').strip()
    event_name = (data.get('event_name') or '').strip()

    if event_id:
        try:
            from routes.events import get_event_by_id
            event_record = get_event_by_id(event_id)
        except Exception:
            event_record = None
        if event_record is None:
            return jsonify({'error': 'Selected event not found'}), 404
        start_date_str = event_record.get('start_time')
        end_date_str = event_record.get('end_time')
        if not event_name:
            event_name = (event_record.get('event_name') or '').strip()

    if not start_date_str or not end_date_str:
        try:
            from routes.events import get_event_state_snapshot
            event_state = get_event_state_snapshot(sync=True)
            if event_state.get('start_time') and event_state.get('end_time'):
                start_date_str = event_state['start_time'].isoformat()
                end_date_str = event_state['end_time'].isoformat()
        except Exception:
            pass

    if not start_date_str or not end_date_str:
        return jsonify({'error': 'start_date and end_date are required'}), 400
    
    try:
        from services.report_generator import ReportGenerator
        generator = ReportGenerator()
        filename = generator.generate_pdf_report(
            start_date=start_date_str,
            end_date=end_date_str,
            report_type=report_type,
            event_name=event_name,
            event_id=event_id,
        )
        
        return send_file(filename, as_attachment=True, download_name=os.path.basename(filename))
    except ModuleNotFoundError as e:
        return jsonify({'error': f'Missing dependency: {e.name}. Install backend requirements.'}), 500
    except Exception as e:
        current_app.logger.exception("Report generation failed")
        return jsonify({'error': str(e)}), 500

@reports_bp.route('/list', methods=['GET'])
@jwt_required()
def list_reports():
    reports_dir = current_app.config['REPORTS_FOLDER']
    files = []
    
    if os.path.exists(reports_dir):
        for f in os.listdir(reports_dir):
            if f.endswith('.pdf'):
                path = os.path.join(reports_dir, f)
                stat = os.stat(path)
                files.append({
                    'filename': f,
                    'size': stat.st_size,
                    'created': datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
    
    return jsonify(files)


@reports_bp.route('/events-on-date', methods=['GET'])
@jwt_required()
def events_on_date():
    date_str = (request.args.get('date') or '').strip()
    if not date_str:
        return jsonify({'error': 'date is required (YYYY-MM-DD)'}), 400

    try:
        target_date = datetime.fromisoformat(date_str).date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    try:
        from routes.events import get_events_for_date
        records = get_events_for_date(target_date)
    except Exception:
        current_app.logger.exception("Failed to load events for date")
        return jsonify({'error': 'Unable to load events'}), 500

    events = []
    for item in records:
        start_raw = item.get('start_time')
        end_raw = item.get('end_time')
        try:
            start_dt = datetime.fromisoformat(start_raw) if start_raw else None
            end_dt = datetime.fromisoformat(end_raw) if end_raw else None
        except Exception:
            start_dt = None
            end_dt = None
        start_label = start_dt.strftime('%I:%M %p') if start_dt else '--:--'
        end_label = end_dt.strftime('%I:%M %p') if end_dt else '--:--'
        events.append({
            'event_id': item.get('event_id'),
            'event_name': item.get('event_name') or 'Unnamed Event',
            'status': item.get('status') or 'scheduled',
            'start_time': start_raw,
            'end_time': end_raw,
            'label': f"{item.get('event_name') or 'Unnamed Event'} ({start_label} - {end_label})",
        })

    return jsonify({'events': events})

@reports_bp.route('/download/<filename>', methods=['GET'])
@jwt_required()
def download_report(filename):
    reports_dir = current_app.config['REPORTS_FOLDER']
    return send_file(os.path.join(reports_dir, filename), as_attachment=True)


@reports_bp.route('/visitor/<visitor_id>', methods=['GET'])
@jwt_required()
def download_visitor_report(visitor_id):
    visitor = Visitor.query.filter_by(visitor_id=visitor_id).first_or_404()
    from services.report_generator import ReportGenerator
    filepath = ReportGenerator().generate_visitor_pdf(visitor)
    return send_file(filepath, as_attachment=True, download_name=os.path.basename(filepath))
