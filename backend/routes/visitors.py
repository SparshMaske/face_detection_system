from flask import request, jsonify
from flask_jwt_extended import jwt_required
from routes import visitors_bp
from models import db
from models.visitor import Visitor, VisitorSession
from datetime import datetime
import re
from sqlalchemy import and_, or_


def _next_visitor_code():
    max_num = 0
    for value in db.session.query(Visitor.visitor_id).all():
        visitor_id = value[0] or ''
        match = re.match(r'^ID(\d+)$', visitor_id)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"ID{max_num + 1}"


def _format_duration(seconds):
    total = max(0, int(seconds or 0))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}h {minutes}m {secs}s"


def _event_window_summary(visitor, windows):
    if not windows:
        return None

    first_seen = None
    last_seen = None
    duration_seconds = 0
    visit_count = 0
    counted_sessions = set()
    now_local = datetime.now()

    for session in visitor.sessions:
        for window_start, window_end in windows:
            session_exit = session.exit_time or now_local
            overlap_start = max(session.entry_time, window_start)
            overlap_end = min(session_exit, window_end)
            if overlap_end < overlap_start:
                continue
            if session.id not in counted_sessions:
                counted_sessions.add(session.id)
                visit_count += 1
            duration_seconds += (overlap_end - overlap_start).total_seconds()
            if first_seen is None or overlap_start < first_seen:
                first_seen = overlap_start
            if last_seen is None or overlap_end > last_seen:
                last_seen = overlap_end

    if first_seen is None or last_seen is None:
        return None

    return {
        'first_seen': first_seen,
        'last_seen': last_seen,
        'visit_count': visit_count,
        'duration_seconds': int(duration_seconds),
        'duration_formatted': _format_duration(duration_seconds),
    }

@visitors_bp.route('/', methods=['GET'])
@jwt_required()
def get_visitors():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = Visitor.query
    event_name = None
    event_windows = []

    try:
        from routes.events import get_event_state_snapshot, get_event_windows_for_name
        event_state = get_event_state_snapshot(sync=True)
        event_name = event_state.get('event_name')
        event_windows = get_event_windows_for_name(event_name) if event_name else []
        if not event_windows and event_state.get('start_time') and event_state.get('end_time'):
            event_windows = [(event_state.get('start_time'), event_state.get('end_time'))]
    except Exception:
        event_name = None
        event_windows = []
    
    if start_date:
        try:
            s_date = datetime.fromisoformat(start_date)
            query = query.filter(Visitor.first_seen >= s_date)
        except ValueError:
            pass
            
    if end_date:
        try:
            e_date = datetime.fromisoformat(end_date)
            query = query.filter(Visitor.first_seen <= e_date)
        except ValueError:
            pass

    if event_windows:
        overlap_conditions = [
            and_(
                VisitorSession.entry_time <= window_end,
                or_(VisitorSession.exit_time.is_(None), VisitorSession.exit_time >= window_start),
            )
            for window_start, window_end in event_windows
        ]
        query = query.join(VisitorSession).filter(or_(*overlap_conditions)).distinct()
            
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    visitor_rows = []
    for visitor in pagination.items:
        payload = visitor.to_dict()
        if event_windows:
            summary = _event_window_summary(visitor, event_windows)
            if summary is None:
                continue
            payload['first_seen'] = summary['first_seen'].isoformat()
            payload['last_seen'] = summary['last_seen'].isoformat()
            payload['visit_count'] = summary['visit_count']
            payload['event_duration_seconds'] = summary['duration_seconds']
            payload['event_duration_formatted'] = summary['duration_formatted']
            payload['event_name'] = event_name
        visitor_rows.append(payload)
    
    return jsonify({
        'visitors': visitor_rows,
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page
    })

@visitors_bp.route('/<int:id>', methods=['GET'])
@jwt_required()
def get_visitor_detail(id):
    visitor = Visitor.query.get_or_404(id)
    return jsonify(visitor.to_dict(include_sessions=True))


@visitors_bp.route('/check-in', methods=['POST'])
@jwt_required()
def check_in():
    data = request.get_json() or {}
    external_visitor_id = data.get('visitor_id')
    camera_id = data.get('camera_id')

    visitor = None
    if external_visitor_id:
        visitor = Visitor.query.filter_by(visitor_id=external_visitor_id).first()

    if visitor is None:
        generated_id = external_visitor_id or _next_visitor_code()
        visitor = Visitor(
            visitor_id=generated_id,
            first_seen=datetime.now(),
            last_seen=datetime.now(),
            visit_count=1
        )
        db.session.add(visitor)
        db.session.flush()
    else:
        visitor.last_seen = datetime.now()
        visitor.visit_count = (visitor.visit_count or 0) + 1

    active_session = VisitorSession.query.filter_by(visitor_id=visitor.id, is_active=True).first()
    if active_session:
        return jsonify(active_session.to_dict())

    session = VisitorSession(
        visitor_id=visitor.id,
        camera_id=camera_id,
        entry_time=datetime.now(),
        is_active=True
    )
    db.session.add(session)
    db.session.commit()

    return jsonify(session.to_dict()), 201


@visitors_bp.route('/<int:id>/check-out', methods=['POST'])
@jwt_required()
def check_out(id):
    visitor = Visitor.query.get_or_404(id)
    active_session = VisitorSession.query.filter_by(visitor_id=visitor.id, is_active=True).order_by(VisitorSession.entry_time.desc()).first()

    if not active_session:
        return jsonify({'error': 'No active session for visitor'}), 404

    active_session.exit_time = datetime.now()
    active_session.is_active = False
    visitor.last_seen = datetime.now()
    db.session.commit()

    try:
        from services.report_generator import ReportGenerator
        ReportGenerator().generate_visitor_pdf(visitor)
    except Exception:
        # Session closure should still succeed even if report generation fails.
        pass

    return jsonify(active_session.to_dict())
