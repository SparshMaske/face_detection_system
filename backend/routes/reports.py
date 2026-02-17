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
            report_type=report_type
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
