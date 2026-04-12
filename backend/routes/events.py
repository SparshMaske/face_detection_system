import json
import os
from datetime import date as date_cls
from datetime import datetime, time as time_cls, timedelta, timezone
from threading import Lock
from typing import Dict, List, Optional, Tuple

from flask import jsonify, request, send_file
from flask_jwt_extended import jwt_required

from models import db
from models.camera import Camera
from routes import events_bp


_EVENT_LOCK = Lock()
_EVENT_STATE = {
    'event_id': None,
    'status': 'idle',
    'workflow_active': False,
    'event_name': '',
    'start_time': None,
    'end_time': None,
    'camera_mode': None,
    'selected_camera_id': None,
    'rtsp_url': None,
    'manual_stop': False,
    'updated_at': None,
}

_ALLOWED_STATUSES = {'scheduled', 'active', 'completed'}


def _now() -> datetime:
    return datetime.now()


def _make_event_id() -> str:
    return f"evt_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"


def _parse_client_tz_offset_minutes(payload: Dict) -> Optional[int]:
    raw = payload.get('client_tz_offset_minutes')
    if raw is None or raw == '':
        return None
    try:
        return int(raw)
    except Exception:
        return None


def _normalize_to_server_local(local_naive_dt: datetime, client_tz_offset_minutes: Optional[int]) -> datetime:
    """
    Convert client-local naive datetime into server-local naive datetime.
    JS getTimezoneOffset returns UTC - local, so IST => -330.
    """
    if client_tz_offset_minutes is None:
        return local_naive_dt
    try:
        client_tz = timezone(timedelta(minutes=-int(client_tz_offset_minutes)))
        aware_client = local_naive_dt.replace(tzinfo=client_tz)
        server_local = aware_client.astimezone().replace(tzinfo=None)
        return server_local
    except Exception:
        return local_naive_dt


def _parse_datetime(raw_value, field_name, client_tz_offset_minutes: Optional[int] = None):
    if not raw_value:
        raise ValueError(f'{field_name} is required')
    try:
        parsed = datetime.fromisoformat(str(raw_value))
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        return _normalize_to_server_local(parsed, client_tz_offset_minutes)
    except ValueError as exc:
        raise ValueError(f'Invalid {field_name}. Use ISO datetime format') from exc


def _parse_datetime_optional(raw_value) -> Optional[datetime]:
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(str(raw_value))
    except Exception:
        return None


def _parse_date_value(raw_value, field_name) -> date_cls:
    if not raw_value:
        raise ValueError(f'{field_name} is required')
    try:
        return date_cls.fromisoformat(str(raw_value))
    except Exception as exc:
        raise ValueError(f'Invalid {field_name}. Use YYYY-MM-DD format') from exc


def _parse_time_value(raw_value, field_name) -> time_cls:
    if not raw_value:
        raise ValueError(f'{field_name} is required')
    text = str(raw_value).strip()
    try:
        if len(text) == 5:
            return time_cls.fromisoformat(f"{text}:00")
        return time_cls.fromisoformat(text)
    except Exception as exc:
        raise ValueError(f'Invalid {field_name}. Use HH:MM format') from exc


def _parse_days_of_week(raw_days) -> List[int]:
    if raw_days is None:
        return [0, 1, 2, 3, 4, 5, 6]
    if not isinstance(raw_days, list):
        raise ValueError('days_of_week must be an array of weekday numbers (0-6, Sunday=0)')
    parsed = []
    for item in raw_days:
        try:
            day = int(item)
        except Exception:
            continue
        if 0 <= day <= 6:
            parsed.append(day)
    parsed = sorted(set(parsed))
    if not parsed:
        raise ValueError('days_of_week cannot be empty for range/daytime scheduling')
    return parsed


def _build_daytime_windows(payload: Dict, client_tz_offset_minutes: Optional[int]) -> List[Tuple[datetime, datetime]]:
    range_start_date = _parse_date_value(payload.get('range_start_date'), 'range_start_date')
    range_end_date = _parse_date_value(payload.get('range_end_date'), 'range_end_date')
    if range_end_date < range_start_date:
        raise ValueError('range_end_date must be on or after range_start_date')

    day_start_time = _parse_time_value(payload.get('day_start_time'), 'day_start_time')
    day_end_time = _parse_time_value(payload.get('day_end_time'), 'day_end_time')
    if day_end_time <= day_start_time:
        raise ValueError('day_end_time must be after day_start_time for daytime scheduling')
    repeat_every_days = int(payload.get('repeat_every_days') or 1)
    if repeat_every_days < 1 or repeat_every_days > 30:
        raise ValueError('repeat_every_days must be between 1 and 30')

    days_of_week = _parse_days_of_week(payload.get('days_of_week'))
    windows: List[Tuple[datetime, datetime]] = []
    cursor_date = range_start_date
    total_days = (range_end_date - range_start_date).days
    for day_offset in range(total_days + 1):
        candidate_date = cursor_date + timedelta(days=day_offset)
        js_weekday = (candidate_date.weekday() + 1) % 7  # python Monday=0 -> JS Sunday=0
        if js_weekday not in days_of_week:
            continue
        if day_offset % repeat_every_days != 0:
            continue

        start_dt_local = datetime.combine(candidate_date, day_start_time)
        end_dt_local = datetime.combine(candidate_date, day_end_time)

        start_dt = _normalize_to_server_local(start_dt_local, client_tz_offset_minutes)
        end_dt = _normalize_to_server_local(end_dt_local, client_tz_offset_minutes)
        if end_dt <= start_dt:
            continue
        windows.append((start_dt, end_dt))

    if not windows:
        raise ValueError('No valid event windows were generated for this range/filter.')
    return windows


def _safe_token(raw_value: str) -> str:
    text = str(raw_value or '').strip()
    if not text:
        return 'event'
    cleaned = []
    for ch in text:
        if ch.isalnum() or ch in ('-', '_'):
            cleaned.append(ch)
        elif ch.isspace():
            cleaned.append('_')
        else:
            cleaned.append('_')
    normalized = ''.join(cleaned).strip('_')
    return normalized or 'event'


def _history_path():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    reports_dir = os.path.join(base_dir, '..', 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    return os.path.join(reports_dir, 'events_history.json')


def _load_event_history():
    path = _history_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as fp:
            payload = json.load(fp)
        if isinstance(payload, list):
            return payload
    except Exception:
        pass
    return []


def _save_event_history(records):
    path = _history_path()
    with open(path, 'w', encoding='utf-8') as fp:
        json.dump(records, fp, ensure_ascii=True, indent=2)


def _append_event_history(record):
    records = _load_event_history()
    dedup_key = (
        record.get('event_id'),
        record.get('event_name'),
        record.get('start_time'),
        record.get('end_time'),
        record.get('camera_mode'),
        record.get('selected_camera_id'),
    )
    for item in records:
        key = (
            item.get('event_id'),
            item.get('event_name'),
            item.get('start_time'),
            item.get('end_time'),
            item.get('camera_mode'),
            item.get('selected_camera_id'),
        )
        if key == dedup_key:
            return
    records.append(record)
    _save_event_history(records)


def _registry_path():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    reports_dir = os.path.join(base_dir, '..', 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    return os.path.join(reports_dir, 'events_registry.json')


def _normalize_event_record(record: Dict) -> Optional[Dict]:
    if not isinstance(record, dict):
        return None

    start_dt = _parse_datetime_optional(record.get('start_time'))
    end_dt = _parse_datetime_optional(record.get('end_time'))
    if not start_dt or not end_dt:
        return None

    event_id = (record.get('event_id') or '').strip() or _make_event_id()
    status = str(record.get('status') or 'scheduled').lower()
    if status not in _ALLOWED_STATUSES:
        status = 'scheduled'

    return {
        'event_id': event_id,
        'event_name': (record.get('event_name') or '').strip(),
        'start_time': start_dt.isoformat(),
        'end_time': end_dt.isoformat(),
        'camera_mode': record.get('camera_mode'),
        'selected_camera_id': record.get('selected_camera_id'),
        'rtsp_url': record.get('rtsp_url'),
        'status': status,
        'manual_stop': bool(record.get('manual_stop', False)),
        'created_at': record.get('created_at') or _now().isoformat(),
        'updated_at': record.get('updated_at') or _now().isoformat(),
        'completed_at': record.get('completed_at'),
    }


def _load_event_registry() -> List[Dict]:
    path = _registry_path()
    records = []

    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as fp:
                payload = json.load(fp)
            if isinstance(payload, list):
                records = payload
        except Exception:
            records = []
    now = _now()
    normalized = []
    for record in records:
        item = _normalize_event_record(record)
        if item:
            normalized.append(item)

    # Always merge missing items from history so completed events remain available
    # after logout/relogin or registry partial loss.
    known_ids = {item.get('event_id') for item in normalized if item.get('event_id')}
    for item in _load_event_history():
        start_dt = _parse_datetime_optional(item.get('start_time'))
        end_dt = _parse_datetime_optional(item.get('end_time'))
        if not start_dt or not end_dt:
            continue
        history_event_id = (item.get('event_id') or '').strip()
        if history_event_id and history_event_id in known_ids:
            continue

        status = 'completed' if now > end_dt else 'scheduled'
        seeded = _normalize_event_record({
            'event_id': history_event_id or _make_event_id(),
            'event_name': item.get('event_name') or '',
            'start_time': start_dt.isoformat(),
            'end_time': end_dt.isoformat(),
            'camera_mode': item.get('camera_mode'),
            'selected_camera_id': item.get('selected_camera_id'),
            'rtsp_url': item.get('rtsp_url'),
            'status': status,
            'manual_stop': status == 'completed',
            'created_at': item.get('created_at') or now.isoformat(),
            'updated_at': now.isoformat(),
            'completed_at': end_dt.isoformat() if status == 'completed' else None,
        })
        if seeded:
            normalized.append(seeded)
            known_ids.add(seeded.get('event_id'))

    normalized.sort(key=lambda rec: (rec.get('start_time') or '', rec.get('created_at') or ''))
    _save_event_registry(normalized)
    return normalized


def _save_event_registry(records: List[Dict]):
    path = _registry_path()
    with open(path, 'w', encoding='utf-8') as fp:
        json.dump(records, fp, ensure_ascii=True, indent=2)


def _record_window(record: Dict) -> Tuple[Optional[datetime], Optional[datetime]]:
    return _parse_datetime_optional(record.get('start_time')), _parse_datetime_optional(record.get('end_time'))


def _windows_overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and end_a > start_b


def _serialize_record(record: Dict) -> Dict:
    return {
        'event_id': record.get('event_id'),
        'event_name': record.get('event_name'),
        'start_time': record.get('start_time'),
        'end_time': record.get('end_time'),
        'camera_mode': record.get('camera_mode'),
        'selected_camera_id': record.get('selected_camera_id'),
        'rtsp_url': record.get('rtsp_url'),
        'status': record.get('status'),
        'manual_stop': bool(record.get('manual_stop', False)),
        'created_at': record.get('created_at'),
        'updated_at': record.get('updated_at'),
        'completed_at': record.get('completed_at'),
    }


def _apply_state_from_record(record: Optional[Dict], status='idle', workflow_active=False):
    if not record:
        _EVENT_STATE['event_id'] = None
        _EVENT_STATE['status'] = status
        _EVENT_STATE['workflow_active'] = bool(workflow_active)
        _EVENT_STATE['event_name'] = ''
        _EVENT_STATE['start_time'] = None
        _EVENT_STATE['end_time'] = None
        _EVENT_STATE['camera_mode'] = None
        _EVENT_STATE['selected_camera_id'] = None
        _EVENT_STATE['rtsp_url'] = None
        _EVENT_STATE['manual_stop'] = False
        _EVENT_STATE['updated_at'] = _now().isoformat()
        return

    _EVENT_STATE['event_id'] = record.get('event_id')
    _EVENT_STATE['status'] = status
    _EVENT_STATE['workflow_active'] = bool(workflow_active)
    _EVENT_STATE['event_name'] = record.get('event_name')
    _EVENT_STATE['start_time'] = _parse_datetime_optional(record.get('start_time'))
    _EVENT_STATE['end_time'] = _parse_datetime_optional(record.get('end_time'))
    _EVENT_STATE['camera_mode'] = record.get('camera_mode')
    _EVENT_STATE['selected_camera_id'] = record.get('selected_camera_id')
    _EVENT_STATE['rtsp_url'] = record.get('rtsp_url')
    _EVENT_STATE['manual_stop'] = bool(record.get('manual_stop', False))
    _EVENT_STATE['updated_at'] = _now().isoformat()


def _sync_registry_status(records: List[Dict]) -> Optional[Dict]:
    now = _now()
    changed = False
    active_candidates: List[Dict] = []

    for record in records:
        start_dt, end_dt = _record_window(record)
        if not start_dt or not end_dt:
            if record.get('status') != 'completed':
                record['status'] = 'completed'
                record['updated_at'] = now.isoformat()
                record['completed_at'] = record.get('completed_at') or now.isoformat()
                changed = True
            continue

        if record.get('manual_stop'):
            if record.get('status') != 'completed':
                record['status'] = 'completed'
                record['updated_at'] = now.isoformat()
                changed = True
            if not record.get('completed_at'):
                record['completed_at'] = now.isoformat()
                changed = True
            continue

        if now > end_dt:
            if record.get('status') != 'completed':
                record['status'] = 'completed'
                record['updated_at'] = now.isoformat()
                changed = True
            if not record.get('completed_at'):
                record['completed_at'] = end_dt.isoformat()
                changed = True
            continue

        if start_dt <= now <= end_dt:
            active_candidates.append(record)
            continue

        if record.get('status') != 'scheduled':
            record['status'] = 'scheduled'
            record['updated_at'] = now.isoformat()
            changed = True

    active_record = None
    if active_candidates:
        active_candidates.sort(key=lambda rec: (rec.get('start_time') or '', rec.get('created_at') or ''))
        active_record = active_candidates[0]
        for record in active_candidates:
            desired = 'active' if record is active_record else 'scheduled'
            if record.get('status') != desired:
                record['status'] = desired
                record['updated_at'] = now.isoformat()
                changed = True

    if changed:
        _save_event_registry(records)

    return active_record


def _next_scheduled_record(records: List[Dict]) -> Optional[Dict]:
    scheduled = []
    for record in records:
        if record.get('status') != 'scheduled':
            continue
        start_dt, end_dt = _record_window(record)
        if not start_dt or not end_dt:
            continue
        if _now() > end_dt:
            continue
        scheduled.append(record)

    if not scheduled:
        return None

    scheduled.sort(key=lambda rec: (rec.get('start_time') or '', rec.get('created_at') or ''))
    return scheduled[0]


def _sync_state_with_time():
    records = _load_event_registry()
    active_record = _sync_registry_status(records)

    if active_record:
        _apply_state_from_record(active_record, status='active', workflow_active=True)
        return

    next_scheduled = _next_scheduled_record(records)
    if next_scheduled:
        _apply_state_from_record(next_scheduled, status='scheduled', workflow_active=False)
        return

    _apply_state_from_record(None, status='idle', workflow_active=False)


def _serialize_state():
    return {
        'event_id': _EVENT_STATE['event_id'],
        'status': _EVENT_STATE['status'],
        'workflow_active': _EVENT_STATE['workflow_active'],
        'event_name': _EVENT_STATE['event_name'],
        'start_time': _EVENT_STATE['start_time'].isoformat() if _EVENT_STATE['start_time'] else None,
        'end_time': _EVENT_STATE['end_time'].isoformat() if _EVENT_STATE['end_time'] else None,
        'camera_mode': _EVENT_STATE['camera_mode'],
        'selected_camera_id': _EVENT_STATE['selected_camera_id'],
        'rtsp_url': _EVENT_STATE['rtsp_url'],
        'manual_stop': _EVENT_STATE.get('manual_stop', False),
        'updated_at': _EVENT_STATE['updated_at'],
    }


def get_event_state_snapshot(sync=True):
    with _EVENT_LOCK:
        if sync:
            _sync_state_with_time()
        return {
            'event_id': _EVENT_STATE['event_id'],
            'status': _EVENT_STATE['status'],
            'workflow_active': bool(_EVENT_STATE['workflow_active']),
            'event_name': _EVENT_STATE['event_name'],
            'start_time': _EVENT_STATE['start_time'],
            'end_time': _EVENT_STATE['end_time'],
            'camera_mode': _EVENT_STATE['camera_mode'],
            'selected_camera_id': _EVENT_STATE['selected_camera_id'],
            'rtsp_url': _EVENT_STATE['rtsp_url'],
            'manual_stop': _EVENT_STATE.get('manual_stop', False),
        }


def is_event_active_for_camera(camera_id=None):
    state = get_event_state_snapshot(sync=True)
    if not state.get('workflow_active'):
        return False
    selected = state.get('selected_camera_id')
    if camera_id and selected and selected != camera_id:
        return False
    return True


def _activate_camera(camera):
    if camera is None:
        return
    camera.is_active = True
    db.session.commit()


def _pick_default_camera() -> Optional[Camera]:
    cams = Camera.query.all()
    if not cams:
        return None

    def _score(cam: Camera) -> Tuple[int, int]:
        camera_id = str(cam.camera_id or '').strip().lower()
        name = str(cam.name or '').strip().lower()
        location = str(cam.location or '').strip().lower()
        ctype = str(cam.camera_type or '').strip().lower()
        hay = f"{camera_id} {name} {location} {ctype}"

        # browser/client cameras are last-resort fallback.
        if ctype == 'browser' or camera_id == 'event_default':
            return (0, 0)

        score = 10
        if cam.is_active:
            score += 6
        if ctype in ('webcam', 'usb', 'default'):
            score += 8
        if ctype == 'rtsp':
            score += 5
        if any(token in hay for token in ('rasp', 'rpi', 'picam', 'csi', 'wired')):
            score += 18
        if any(token in hay for token in ('usb', 'webcam', 'logitech', 'camera')):
            score += 7
        if camera_id in ('raspberry_camera', 'rpi_camera', 'picam', 'cam001'):
            score += 10

        # stable ordering fallback
        return (score, -int(cam.id or 0))

    ranked = sorted(cams, key=_score, reverse=True)
    return ranked[0] if ranked else None


def _resolve_camera(camera_mode, rtsp_url=None, existing_camera_id=None):
    if camera_mode == 'default':
        preferred = _pick_default_camera()
        if preferred and str(preferred.camera_type or '').lower() != 'browser':
            _activate_camera(preferred)
            return preferred, None

        camera = Camera.query.filter_by(camera_id='EVENT_DEFAULT').first()
        if not camera:
            camera = Camera(
                camera_id='EVENT_DEFAULT',
                name='Event Device Camera',
                location='Event Scheduler',
                stream_url='browser://device',
                camera_type='browser',
                is_active=True,
            )
            db.session.add(camera)
        else:
            camera.stream_url = 'browser://device'
            camera.camera_type = 'browser'
            camera.is_active = True
        db.session.commit()
        return camera, None

    if camera_mode == 'rtsp':
        if not rtsp_url:
            return None, 'RTSP URL is required for RTSP mode'
        camera = Camera.query.filter_by(camera_id='EVENT_RTSP').first()
        if not camera:
            camera = Camera(
                camera_id='EVENT_RTSP',
                name='Event RTSP Camera',
                location='Event Scheduler',
                stream_url=rtsp_url,
                camera_type='rtsp',
                is_active=True,
            )
            db.session.add(camera)
        else:
            camera.stream_url = rtsp_url
            camera.camera_type = 'rtsp'
            camera.is_active = True
        db.session.commit()
        return camera, None

    if camera_mode == 'existing':
        if not existing_camera_id:
            return None, 'camera_id is required for existing camera mode'
        camera = Camera.query.filter_by(camera_id=existing_camera_id).first()
        if not camera:
            return None, 'Selected camera was not found'
        _activate_camera(camera)
        return camera, None

    return None, "camera_mode must be one of: 'default', 'rtsp', 'existing'"


def get_event_windows_for_name(event_name: str) -> List[Tuple[datetime, datetime]]:
    if not event_name:
        return []

    target = event_name.strip()
    windows = []

    for item in _load_event_registry():
        if (item.get('event_name') or '').strip() != target:
            continue
        start_dt, end_dt = _record_window(item)
        if start_dt and end_dt and end_dt >= start_dt:
            windows.append((start_dt, end_dt))

    # Backward-compatible fallback for older history records.
    for item in _load_event_history():
        if (item.get('event_name') or '').strip() != target:
            continue
        start_dt = _parse_datetime_optional(item.get('start_time'))
        end_dt = _parse_datetime_optional(item.get('end_time'))
        if start_dt and end_dt and end_dt >= start_dt:
            windows.append((start_dt, end_dt))

    # De-duplicate same windows.
    dedup = {}
    for start_dt, end_dt in windows:
        dedup[(start_dt.isoformat(), end_dt.isoformat())] = (start_dt, end_dt)

    result = list(dedup.values())
    result.sort(key=lambda window: window[0])
    return result


def _find_event_by_id(records: List[Dict], event_id: Optional[str]) -> Optional[Dict]:
    if not event_id:
        return None
    for record in records:
        if record.get('event_id') == event_id:
            return record
    return None


def get_event_by_id(event_id: Optional[str]) -> Optional[Dict]:
    if not event_id:
        return None
    with _EVENT_LOCK:
        records = _load_event_registry()
        _sync_registry_status(records)
        record = _find_event_by_id(records, event_id)
        return _serialize_record(record) if record else None


def get_events_for_date(target_date):
    with _EVENT_LOCK:
        records = _load_event_registry()
        _sync_registry_status(records)

        matched = []
        for record in records:
            start_dt, end_dt = _record_window(record)
            if not start_dt or not end_dt:
                continue
            if start_dt.date() <= target_date <= end_dt.date():
                matched.append(_serialize_record(record))

        matched.sort(key=lambda item: (item.get('start_time') or '', item.get('created_at') or ''))
        return matched


@events_bp.route('/current', methods=['GET'])
@jwt_required()
def get_current_event():
    with _EVENT_LOCK:
        _sync_state_with_time()
        _EVENT_STATE['updated_at'] = _now().isoformat()
        return jsonify(_serialize_state())


@events_bp.route('/schedule', methods=['POST'])
@jwt_required()
def schedule_event():
    payload = request.get_json() or {}
    event_name = (payload.get('event_name') or '').strip()
    schedule_mode = str(payload.get('schedule_mode') or 'single').strip().lower()
    camera_mode = payload.get('camera_mode')
    rtsp_url = (payload.get('rtsp_url') or '').strip()
    existing_camera_id = payload.get('camera_id')
    client_tz_offset_minutes = _parse_client_tz_offset_minutes(payload)

    if not event_name:
        return jsonify({'error': 'event_name is required'}), 400

    try:
        if schedule_mode == 'single':
            start_time = _parse_datetime(
                payload.get('start_time'),
                'start_time',
                client_tz_offset_minutes=client_tz_offset_minutes,
            )
            end_time = _parse_datetime(
                payload.get('end_time'),
                'end_time',
                client_tz_offset_minutes=client_tz_offset_minutes,
            )
            windows_to_create = [(start_time, end_time)]
        elif schedule_mode in ('daytime_window', 'daily_window', 'multi_day'):
            windows_to_create = _build_daytime_windows(payload, client_tz_offset_minutes)
            start_time, end_time = windows_to_create[0]
        else:
            return jsonify({'error': "schedule_mode must be 'single' or 'daytime_window'"}), 400
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if any(end <= start for start, end in windows_to_create):
        return jsonify({'error': 'end_time must be after start_time'}), 400

    with _EVENT_LOCK:
        records = _load_event_registry()
        active_record = _sync_registry_status(records)
        if active_record is not None:
            return jsonify({'error': 'An event is already active. Stop the active event before scheduling another.'}), 409

        for existing in records:
            status = str(existing.get('status') or '').lower()
            if status not in ('scheduled', 'active'):
                continue
            existing_start, existing_end = _record_window(existing)
            if not existing_start or not existing_end:
                continue
            for start_time, end_time in windows_to_create:
                if _windows_overlap(start_time, end_time, existing_start, existing_end):
                    conflict_name = (existing.get('event_name') or '').strip() or existing.get('event_id') or 'another event'
                    return jsonify({
                        'error': f"Event '{conflict_name}' is already scheduled in this time window."
                    }), 409

        camera, camera_error = _resolve_camera(
            camera_mode,
            rtsp_url=rtsp_url,
            existing_camera_id=existing_camera_id,
        )
        if camera_error:
            return jsonify({'error': camera_error}), 400

        now = _now()
        created_records = []
        for start_time, end_time in windows_to_create:
            event_id = _make_event_id()
            record = {
                'event_id': event_id,
                'event_name': event_name,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'camera_mode': camera_mode,
                'selected_camera_id': camera.camera_id if camera else None,
                'rtsp_url': rtsp_url if camera_mode == 'rtsp' else None,
                'status': 'scheduled',
                'manual_stop': False,
                'created_at': now.isoformat(),
                'updated_at': now.isoformat(),
                'completed_at': None,
            }
            records.append(record)
            created_records.append(record)

            _append_event_history({
                'event_id': event_id,
                'event_name': event_name,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'camera_mode': camera_mode,
                'selected_camera_id': camera.camera_id if camera else None,
                'rtsp_url': rtsp_url if camera_mode == 'rtsp' else None,
                'status': 'scheduled',
                'created_at': now.isoformat(),
            })

        records.sort(key=lambda rec: (rec.get('start_time') or '', rec.get('created_at') or ''))
        _save_event_registry(records)
        _sync_state_with_time()
        response = _serialize_state()
        response['created_count'] = len(created_records)
        response['schedule_mode'] = schedule_mode
        return jsonify(response)


@events_bp.route('/start', methods=['POST'])
@jwt_required()
def start_event():
    payload = request.get_json(silent=True) or {}
    requested_id = payload.get('event_id') or request.args.get('event_id')

    with _EVENT_LOCK:
        records = _load_event_registry()
        active_record = _sync_registry_status(records)

        if active_record is not None and requested_id and active_record.get('event_id') != requested_id:
            return jsonify({'error': 'Another event is already active'}), 409

        target_record = None
        if requested_id:
            target_record = _find_event_by_id(records, requested_id)
        elif active_record is not None:
            target_record = active_record
        elif _EVENT_STATE.get('event_id'):
            target_record = _find_event_by_id(records, _EVENT_STATE.get('event_id'))
        if target_record is None:
            target_record = _next_scheduled_record(records)

        if target_record is None:
            return jsonify({'error': 'No scheduled event found'}), 400

        start_dt, end_dt = _record_window(target_record)
        now = _now()
        if not start_dt or not end_dt or now > end_dt:
            return jsonify({'error': 'Selected event has already ended'}), 400

        if now < start_dt:
            target_record['start_time'] = now.isoformat()
        target_record['status'] = 'active'
        target_record['manual_stop'] = False
        target_record['updated_at'] = now.isoformat()

        for record in records:
            if record.get('event_id') == target_record.get('event_id'):
                continue
            if record.get('status') == 'active':
                record['status'] = 'scheduled'
                record['updated_at'] = now.isoformat()

        _save_event_registry(records)
        _apply_state_from_record(target_record, status='active', workflow_active=True)

        selected_camera_id = target_record.get('selected_camera_id')
        if selected_camera_id:
            camera = Camera.query.filter_by(camera_id=selected_camera_id).first()
            _activate_camera(camera)

        return jsonify(_serialize_state())


@events_bp.route('/stop', methods=['POST'])
@jwt_required()
def stop_event():
    payload = request.get_json(silent=True) or {}
    requested_id = payload.get('event_id') or request.args.get('event_id')

    with _EVENT_LOCK:
        records = _load_event_registry()
        active_record = _sync_registry_status(records)

        target_record = None
        if requested_id:
            target_record = _find_event_by_id(records, requested_id)
        elif active_record is not None:
            target_record = active_record
        elif _EVENT_STATE.get('event_id'):
            target_record = _find_event_by_id(records, _EVENT_STATE.get('event_id'))

        if target_record is None:
            return jsonify({'error': 'No active/scheduled event found'}), 400

        if target_record.get('status') == 'completed':
            return jsonify({'error': 'Event is already completed'}), 400

        now = _now()
        end_dt = _parse_datetime_optional(target_record.get('end_time'))
        if not end_dt or now < end_dt:
            target_record['end_time'] = now.isoformat()

        target_record['status'] = 'completed'
        target_record['manual_stop'] = True
        target_record['completed_at'] = now.isoformat()
        target_record['updated_at'] = now.isoformat()

        _save_event_registry(records)
        _sync_state_with_time()
        return jsonify(_serialize_state())


@events_bp.route('/management', methods=['GET'])
@jwt_required()
def get_event_management():
    with _EVENT_LOCK:
        records = _load_event_registry()
        _sync_registry_status(records)

        scheduled_events = []
        active_events = []
        completed_events = []

        for record in records:
            status = str(record.get('status') or 'scheduled').lower()
            serialized = _serialize_record(record)
            if status == 'active':
                active_events.append(serialized)
            elif status == 'completed':
                completed_events.append(serialized)
            else:
                scheduled_events.append(serialized)

        scheduled_events.sort(key=lambda item: (item.get('start_time') or '', item.get('created_at') or ''))
        active_events.sort(key=lambda item: (item.get('start_time') or '', item.get('created_at') or ''))
        completed_events.sort(
            key=lambda item: (item.get('completed_at') or item.get('end_time') or '', item.get('created_at') or ''),
            reverse=True,
        )

        return jsonify({
            'scheduled_events': scheduled_events,
            'active_events': active_events,
            'completed_events': completed_events,
        })


@events_bp.route('/scheduled/<event_id>', methods=['DELETE'])
@jwt_required()
def delete_scheduled_event(event_id):
    with _EVENT_LOCK:
        records = _load_event_registry()
        _sync_registry_status(records)

        target_index = None
        for index, record in enumerate(records):
            if record.get('event_id') == event_id:
                target_index = index
                break

        if target_index is None:
            return jsonify({'error': 'Event not found'}), 404

        if str(records[target_index].get('status') or '').lower() != 'scheduled':
            return jsonify({'error': 'Only scheduled events can be deleted'}), 400

        del records[target_index]
        _save_event_registry(records)
        _sync_state_with_time()
        return jsonify({'message': 'Scheduled event deleted'})


@events_bp.route('/completed/<event_id>/export-excel', methods=['GET'])
@events_bp.route('/completed/<event_id>/export-csv', methods=['GET'])
@jwt_required()
def export_completed_event_excel(event_id):
    with _EVENT_LOCK:
        records = _load_event_registry()
        _sync_registry_status(records)
        event_record = _find_event_by_id(records, event_id)

    if event_record is None:
        return jsonify({'error': 'Event not found'}), 404

    start_dt, end_dt = _record_window(event_record)
    if not start_dt or not end_dt:
        return jsonify({'error': 'Invalid event window'}), 400

    status = str(event_record.get('status') or '').lower()
    if status != 'completed' and _now() <= end_dt:
        return jsonify({'error': 'Excel export is available only for completed events'}), 400

    try:
        from services.report_generator import ReportGenerator
        generator = ReportGenerator()
        filepath = generator.generate_excel_report(
            start_date=start_dt.isoformat(),
            end_date=end_dt.isoformat(),
            report_type='event_summary',
            event_name=event_record.get('event_name') or '',
            event_id=event_record.get('event_id') or '',
        )
    except ModuleNotFoundError:
        return jsonify({'error': 'Missing dependency: openpyxl. Install backend requirements.'}), 500
    except Exception as exc:
        return jsonify({'error': f'Failed to generate Excel export: {exc}'}), 500

    safe_event_name = _safe_token(event_record.get('event_name') or 'event')
    filename = f"{safe_event_name}_{event_record.get('event_id')}_results.xlsx"
    return send_file(
        filepath,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        max_age=0,
    )
