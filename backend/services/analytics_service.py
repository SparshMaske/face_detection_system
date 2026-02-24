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

    @staticmethod
    def _build_visitor_spans(start_date=None, end_date=None, windows=None):
        now_local = datetime.utcnow()
        spans = {}

        if windows:
            overlap_filters = [
                and_(
                    VisitorSession.entry_time <= window_end,
                    or_(VisitorSession.exit_time.is_(None), VisitorSession.exit_time >= window_start)
                )
                for window_start, window_end in windows
            ]
            sessions = VisitorSession.query.filter(or_(*overlap_filters)).all()

            for session in sessions:
                for window_start, window_end in windows:
                    overlap_start = max(session.entry_time, window_start)
                    overlap_end = min(session.exit_time or now_local, window_end)
                    if overlap_end < overlap_start:
                        continue
                    current = spans.setdefault(session.visitor_id, {'first_in': None, 'last_out': None})
                    if current['first_in'] is None or overlap_start < current['first_in']:
                        current['first_in'] = overlap_start
                    if current['last_out'] is None or overlap_end > current['last_out']:
                        current['last_out'] = overlap_end
            return spans

        window_end = end_date or now_local
        query = VisitorSession.query.filter(VisitorSession.entry_time <= window_end)
        if start_date is not None:
            query = query.filter(or_(VisitorSession.exit_time.is_(None), VisitorSession.exit_time >= start_date))

        sessions = query.all()
        for session in sessions:
            overlap_start = session.entry_time if start_date is None else max(session.entry_time, start_date)
            overlap_end = min(session.exit_time or now_local, window_end)
            if overlap_end < overlap_start:
                continue

            current = spans.setdefault(session.visitor_id, {'first_in': None, 'last_out': None})
            if current['first_in'] is None or overlap_start < current['first_in']:
                current['first_in'] = overlap_start
            if current['last_out'] is None or overlap_end > current['last_out']:
                current['last_out'] = overlap_end
        return spans

    @staticmethod
    def _average_duration_from_spans(spans):
        durations = []
        for item in spans.values():
            first_in = item.get('first_in')
            last_out = item.get('last_out')
            if not first_in or not last_out:
                continue
            durations.append(max(0, (last_out - first_in).total_seconds()))
        if not durations:
            return 0
        return sum(durations) / len(durations)
    
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
        windows = self._event_windows()
        spans = self._build_visitor_spans(windows=windows if windows else None)
        avg_seconds = self._average_duration_from_spans(spans)
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
        
        windows = self._event_windows()
        if windows:
            visitor_spans = self._build_visitor_spans(windows=windows)
        else:
            visitor_spans = self._build_visitor_spans(start_date=start_date, end_date=end_date)
        avg_seconds = self._average_duration_from_spans(visitor_spans)

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
