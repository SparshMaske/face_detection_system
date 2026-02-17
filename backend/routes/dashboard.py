from flask import jsonify
from flask_jwt_extended import jwt_required
from routes import dashboard_bp
from models import db
from models.visitor import VisitorSession, Visitor
from models.staff import Staff
import datetime
from sqlalchemy import and_, or_, distinct


def _get_current_event_scope():
    try:
        from routes.events import get_event_state_snapshot, get_event_windows_for_name
        state = get_event_state_snapshot(sync=True)
        event_name = state.get('event_name')
        windows = get_event_windows_for_name(event_name) if event_name else []
        if not windows and state.get('start_time') and state.get('end_time'):
            windows = [(state.get('start_time'), state.get('end_time'))]
        return event_name, windows
    except Exception:
        return None, []


def _apply_windows(query, windows):
    if not windows:
        return query
    overlaps = [
        and_(
            VisitorSession.entry_time <= end_time,
            or_(VisitorSession.exit_time.is_(None), VisitorSession.exit_time >= start_time)
        )
        for start_time, end_time in windows
    ]
    return query.filter(or_(*overlaps))

@dashboard_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_stats():
    event_name, windows = _get_current_event_scope()

    session_query = VisitorSession.query
    if windows:
        session_query = _apply_windows(session_query, windows)
    else:
        today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        session_query = session_query.filter(VisitorSession.entry_time >= today_start)

    today_visitors = session_query.count()

    active_visitors = session_query.filter(VisitorSession.is_active.is_(True)).count()

    if windows:
        total_visitors = _apply_windows(
            db.session.query(distinct(VisitorSession.visitor_id)),
            windows
        ).count()
    else:
        total_visitors = Visitor.query.count()
    
    total_staff = Staff.query.filter_by(is_active=True).count()
    inactive_staff = Staff.query.filter_by(is_active=False).count()
    
    return jsonify({
        'event_name': event_name,
        'today_visitors': today_visitors,
        'active_visitors': active_visitors,
        'total_visitors': total_visitors,
        'total_staff': total_staff,
        'inactive_staff': inactive_staff,
    })

@dashboard_bp.route('/recent-activity', methods=['GET'])
@jwt_required()
def recent_activity():
    event_name, windows = _get_current_event_scope()

    query = VisitorSession.query
    if windows:
        query = _apply_windows(query, windows)
    recent_sessions = query.order_by(VisitorSession.entry_time.desc()).limit(10).all()
    
    results = []
    for session in recent_sessions:
        # Use backref to get visitor object
        v = session.visitor
        results.append({
            'id': session.id,
            'visitor_id': v.visitor_id if v else 'Unknown',
            'entry_time': session.entry_time.isoformat() if session.entry_time else None,
            'exit_time': session.exit_time.isoformat() if session.exit_time else None,
            'duration_formatted': session.to_dict()['duration_formatted'],
            'is_active': session.is_active,
            'event_name': event_name,
        })
        
    return jsonify(results)
