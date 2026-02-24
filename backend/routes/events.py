import csv
import json
import os
from datetime import datetime
from io import StringIO
from threading import Lock
from typing import Dict, List, Optional, Tuple

from flask import Response, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import or_

from models import db
from models.camera import Camera
from models.visitor import Visitor, VisitorSession
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


def _parse_datetime(raw_value, field_name):
    if not raw_value:
        raise ValueError(f'{field_name} is required')
    try:
        return datetime.fromisoformat(str(raw_value))
    except ValueError as exc:
        raise ValueError(f'Invalid {field_name}. Use ISO datetime format') from exc


def _parse_datetime_optional(raw_value) -> Optional[datetime]:
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(str(raw_value))
    except Exception:
        return None


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds or 0))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


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
    elif _load_event_history():
        now = _now()
        for item in _load_event_history():
            start_dt = _parse_datetime_optional(item.get('start_time'))
            end_dt = _parse_datetime_optional(item.get('end_time'))
            if not start_dt or not end_dt:
                continue
            status = 'completed' if now > end_dt else 'scheduled'
            seeded = _normalize_event_record({
                'event_id': item.get('event_id') or _make_event_id(),
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
                records.append(seeded)
        _save_event_registry(records)

    normalized = []
    for record in records:
        item = _normalize_event_record(record)
        if item:
            normalized.append(item)
    normalized.sort(key=lambda rec: (rec.get('start_time') or '', rec.get('created_at') or ''))
    return normalized


def _save_event_registry(records: List[Dict]):
    path = _registry_path()
    with open(path, 'w', encoding='utf-8') as fp:
        json.dump(records, fp, ensure_ascii=True, indent=2)


def _record_window(record: Dict) -> Tuple[Optional[datetime], Optional[datetime]]:
    return _parse_datetime_optional(record.get('start_time')), _parse_datetime_optional(record.get('end_time'))


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


def _resolve_camera(camera_mode, rtsp_url=None, existing_camera_id=None):
    if camera_mode == 'default':
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
    camera_mode = payload.get('camera_mode')
    rtsp_url = (payload.get('rtsp_url') or '').strip()
    existing_camera_id = payload.get('camera_id')

    if not event_name:
        return jsonify({'error': 'event_name is required'}), 400

    try:
        start_time = _parse_datetime(payload.get('start_time'), 'start_time')
        end_time = _parse_datetime(payload.get('end_time'), 'end_time')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if end_time <= start_time:
        return jsonify({'error': 'end_time must be after start_time'}), 400

    camera, camera_error = _resolve_camera(camera_mode, rtsp_url=rtsp_url, existing_camera_id=existing_camera_id)
    if camera_error:
        return jsonify({'error': camera_error}), 400

    with _EVENT_LOCK:
        records = _load_event_registry()
        active_record = _sync_registry_status(records)
        if active_record is not None:
            return jsonify({'error': 'An event is already active. Stop the active event before scheduling another.'}), 409

        now = _now()
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
        records.sort(key=lambda rec: (rec.get('start_time') or '', rec.get('created_at') or ''))
        _save_event_registry(records)

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

        _apply_state_from_record(record, status='scheduled', workflow_active=False)
        return jsonify(_serialize_state())


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


@events_bp.route('/completed/<event_id>/export-csv', methods=['GET'])
@jwt_required()
def export_completed_event_csv(event_id):
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
        return jsonify({'error': 'CSV export is available only for completed events'}), 400

    sessions = VisitorSession.query.filter(
        VisitorSession.entry_time <= end_dt,
        or_(VisitorSession.exit_time.is_(None), VisitorSession.exit_time >= start_dt),
    ).all()

    now_local = _now()
    grouped = {}
    for session in sessions:
        overlap_start = max(session.entry_time, start_dt)
        overlap_end = min(session.exit_time or now_local, end_dt)
        if overlap_end < overlap_start:
            continue

        item = grouped.setdefault(session.visitor_id, {
            'first_in': None,
            'last_out': None,
        })
        if item['first_in'] is None or overlap_start < item['first_in']:
            item['first_in'] = overlap_start
        if item['last_out'] is None or overlap_end > item['last_out']:
            item['last_out'] = overlap_end

    visitors = Visitor.query.filter(Visitor.id.in_(grouped.keys())).all() if grouped else []
    visitor_by_id = {visitor.id: visitor for visitor in visitors}

    reports_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'reports', 'visitors')
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'event_id',
        'event_name',
        'visitor_id',
        'date',
        'first_in_time',
        'last_out_time',
        'duration',
        'pdf_file',
        'pdf_content',
    ])

    for visitor_db_id in sorted(grouped.keys()):
        summary = grouped[visitor_db_id]
        visitor = visitor_by_id.get(visitor_db_id)
        visitor_code = visitor.visitor_id if visitor else f'VISITOR-{visitor_db_id}'
        first_in = summary.get('first_in')
        last_out = summary.get('last_out')
        duration_seconds = 0
        if first_in and last_out:
            duration_seconds = max(0, int((last_out - first_in).total_seconds()))
        duration_text = _format_duration(duration_seconds)

        pdf_filename = f"{visitor_code}_report.pdf"
        pdf_path = os.path.join(reports_root, pdf_filename)
        pdf_file = pdf_filename if os.path.exists(pdf_path) else ''

        date_text = first_in.strftime('%Y-%m-%d') if first_in else ''
        first_in_text = first_in.strftime('%Y-%m-%d %H:%M:%S') if first_in else ''
        last_out_text = last_out.strftime('%Y-%m-%d %H:%M:%S') if last_out else ''
        pdf_content = (
            f"Date={date_text}; First In={first_in_text}; "
            f"Last Out={last_out_text}; Duration={duration_text}"
        )

        writer.writerow([
            event_record.get('event_id'),
            event_record.get('event_name'),
            visitor_code,
            date_text,
            first_in_text,
            last_out_text,
            duration_text,
            pdf_file,
            pdf_content,
        ])

    csv_bytes = output.getvalue().encode('utf-8')
    output.close()

    safe_event_name = str(event_record.get('event_name') or 'event').strip().replace(' ', '_')
    filename = f"{safe_event_name}_{event_record.get('event_id')}_results.csv"

    return Response(
        csv_bytes,
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={filename}',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
        },
    )
