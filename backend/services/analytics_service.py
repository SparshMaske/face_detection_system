from sqlalchemy import and_, extract, func, or_
from models import db
from models.visitor import VisitorSession
from models.staff import Staff
from datetime import datetime, timedelta

class AnalyticsService:
    @staticmethod
    def _event_windows():
        try:
            from routes.events import get_event_state_snapshot, get_event_windows_for_name
            state = get_event_state_snapshot(sync=True)
            event_name = state.get('event_name')
            windows = get_event_windows_for_name(event_name) if event_name else []
            if not windows and state.get('start_time') and state.get('end_time'):
                windows = [(state.get('start_time'), state.get('end_time'))]
            return windows
        except Exception:
            return []

    @staticmethod
    def _window_filter():
        windows = AnalyticsService._event_windows()
        if not windows:
            return None
        return or_(*[
            and_(
                VisitorSession.entry_time <= end_time,
                or_(VisitorSession.exit_time.is_(None), VisitorSession.exit_time >= start_time)
            )
            for start_time, end_time in windows
        ])
    
    def get_footfall_trends(self, days=7):
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        query = db.session.query(
            func.date(VisitorSession.entry_time).label('date'),
            func.count(VisitorSession.id).label('count')
        )
        event_filter = self._window_filter()
        if event_filter is not None:
            query = query.filter(event_filter)
        else:
            query = query.filter(VisitorSession.entry_time >= start_date)
        results = query.group_by(func.date(VisitorSession.entry_time)).order_by('date').all()
        
        return [{'date': str(r.date), 'count': r.count} for r in results]

    def get_peak_hours(self, days=7):
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        query = db.session.query(
            extract('hour', VisitorSession.entry_time).label('hour'),
            func.count(VisitorSession.id).label('count')
        )
        event_filter = self._window_filter()
        if event_filter is not None:
            query = query.filter(event_filter)
        else:
            query = query.filter(VisitorSession.entry_time >= start_date)
        results = query.group_by('hour').order_by('hour').all()
        
        return [{'hour': int(r.hour), 'count': r.count} for r in results]

    def get_average_duration(self):
        query = db.session.query(
            func.avg(
                func.extract('epoch', VisitorSession.exit_time) - 
                func.extract('epoch', VisitorSession.entry_time)
            )
        ).filter(VisitorSession.exit_time.isnot(None))
        event_filter = self._window_filter()
        if event_filter is not None:
            query = query.filter(event_filter)
        results = query.first()
        
        avg_seconds = results[0] if results else 0
        return {
            'average_seconds': avg_seconds,
            'average_minutes': avg_seconds / 60.0 if avg_seconds else 0
        }

    def get_summary(self, days=30):
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        total_visitors_q = db.session.query(VisitorSession)
        event_filter = self._window_filter()
        if event_filter is not None:
            total_visitors_q = total_visitors_q.filter(event_filter)
        else:
            total_visitors_q = total_visitors_q.filter(VisitorSession.entry_time >= start_date)
        total_sessions = total_visitors_q.count()
        
        avg_q = db.session.query(
            func.avg(
                func.extract('epoch', VisitorSession.exit_time) - 
                func.extract('epoch', VisitorSession.entry_time)
            )
        ).filter(VisitorSession.exit_time.isnot(None))
        if event_filter is not None:
            avg_q = avg_q.filter(event_filter)
        else:
            avg_q = avg_q.filter(VisitorSession.entry_time >= start_date)
        avg_res = avg_q.first()
        avg_seconds = avg_res[0] if avg_res else 0

        peak_day_q = db.session.query(
            func.date(VisitorSession.entry_time).label('date'),
            func.count(VisitorSession.id).label('count')
        )
        if event_filter is not None:
            peak_day_q = peak_day_q.filter(event_filter)
        else:
            peak_day_q = peak_day_q.filter(VisitorSession.entry_time >= start_date)
        peak_day_q = peak_day_q.group_by('date').order_by(func.count(VisitorSession.id).desc()).first()
        active_staff = Staff.query.filter_by(is_active=True).count()
        inactive_staff = Staff.query.filter_by(is_active=False).count()
        
        return {
            'total_visitors': total_sessions,
            'total_sessions': total_sessions,
            'average_duration_seconds': avg_seconds,
            'average_visits_per_day': total_sessions / days if days > 0 else 0,
            'total_staff': active_staff,
            'inactive_staff': inactive_staff,
            'peak_day': {
                'date': str(peak_day_q.date),
                'count': peak_day_q.count
            } if peak_day_q else None
        }
