import json
import os
from datetime import datetime
from threading import Lock
from typing import List, Tuple

from flask import jsonify, request
from flask_jwt_extended import jwt_required

from models import db
from models.camera import Camera
from routes import events_bp


_EVENT_LOCK = Lock()
_EVENT_STATE = {
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


def _now():
    return datetime.now()


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
        record.get('event_name'),
        record.get('start_time'),
        record.get('end_time'),
        record.get('camera_mode'),
        record.get('selected_camera_id'),
    )
    for item in records:
        key = (
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


def get_event_windows_for_name(event_name: str) -> List[Tuple[datetime, datetime]]:
    if not event_name:
        return []

    windows = []
    for item in _load_event_history():
        if (item.get('event_name') or '').strip() != event_name.strip():
            continue
        start_raw = item.get('start_time')
        end_raw = item.get('end_time')
        if not start_raw or not end_raw:
            continue
        try:
            start_dt = datetime.fromisoformat(start_raw)
            end_dt = datetime.fromisoformat(end_raw)
            if end_dt >= start_dt:
                windows.append((start_dt, end_dt))
        except Exception:
            continue
    windows.sort(key=lambda window: window[0])
    return windows


def _parse_datetime(raw_value, field_name):
    if not raw_value:
        raise ValueError(f'{field_name} is required')
    try:
        return datetime.fromisoformat(raw_value)
    except ValueError as exc:
        raise ValueError(f'Invalid {field_name}. Use ISO datetime format') from exc


def _sync_state_with_time():
    if not _EVENT_STATE['start_time'] or not _EVENT_STATE['end_time']:
        return

    if _EVENT_STATE.get('manual_stop'):
        _EVENT_STATE['status'] = 'completed'
        _EVENT_STATE['workflow_active'] = False
        return

    now = _now()
    if now > _EVENT_STATE['end_time']:
        _EVENT_STATE['status'] = 'completed'
        _EVENT_STATE['workflow_active'] = False
    elif _EVENT_STATE['start_time'] <= now <= _EVENT_STATE['end_time']:
        _EVENT_STATE['status'] = 'active'
        _EVENT_STATE['workflow_active'] = True
    else:
        _EVENT_STATE['status'] = 'scheduled'
        _EVENT_STATE['workflow_active'] = False


def _serialize_state():
    return {
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
                name='Event Default Camera',
                location='Event Scheduler',
                stream_url='0',
                camera_type='webcam',
                is_active=True,
            )
            db.session.add(camera)
        else:
            camera.stream_url = '0'
            camera.camera_type = 'webcam'
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
        _EVENT_STATE['event_name'] = event_name
        _EVENT_STATE['start_time'] = start_time
        _EVENT_STATE['end_time'] = end_time
        _EVENT_STATE['camera_mode'] = camera_mode
        _EVENT_STATE['selected_camera_id'] = camera.camera_id if camera else None
        _EVENT_STATE['rtsp_url'] = rtsp_url if camera_mode == 'rtsp' else None
        _EVENT_STATE['manual_stop'] = False
        _sync_state_with_time()
        _EVENT_STATE['updated_at'] = _now().isoformat()
        _append_event_history({
            'event_name': event_name,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'camera_mode': camera_mode,
            'selected_camera_id': camera.camera_id if camera else None,
            'rtsp_url': rtsp_url if camera_mode == 'rtsp' else None,
            'created_at': _EVENT_STATE['updated_at'],
        })
        return jsonify(_serialize_state())


@events_bp.route('/start', methods=['POST'])
@jwt_required()
def start_event():
    with _EVENT_LOCK:
        if not _EVENT_STATE['event_name']:
            return jsonify({'error': 'No scheduled event found'}), 400

        _EVENT_STATE['status'] = 'active'
        _EVENT_STATE['workflow_active'] = True
        _EVENT_STATE['manual_stop'] = False
        _EVENT_STATE['updated_at'] = _now().isoformat()

        selected_camera_id = _EVENT_STATE.get('selected_camera_id')
        if selected_camera_id:
            camera = Camera.query.filter_by(camera_id=selected_camera_id).first()
            _activate_camera(camera)

        return jsonify(_serialize_state())


@events_bp.route('/stop', methods=['POST'])
@jwt_required()
def stop_event():
    with _EVENT_LOCK:
        if not _EVENT_STATE['event_name']:
            return jsonify({'error': 'No active/scheduled event found'}), 400
        _EVENT_STATE['status'] = 'completed'
        _EVENT_STATE['workflow_active'] = False
        _EVENT_STATE['manual_stop'] = True
        _EVENT_STATE['updated_at'] = _now().isoformat()
        return jsonify(_serialize_state())
