from flask import request, jsonify, current_app
from flask_jwt_extended import jwt_required
from routes import settings_bp
from models import db
from models.camera import SystemSettings

DEFAULT_SETTINGS = {
    'detection_confidence_threshold': {
        'value': 0.35,
        'value_type': 'float',
        'description': 'Minimum detector confidence score for a face candidate',
    },
    'similarity_threshold': {
        'value': 0.5,
        'value_type': 'float',
        'description': 'Face recognition similarity threshold',
    },
    'staff_similarity_threshold': {
        'value': 0.65,
        'value_type': 'float',
        'description': 'Staff recognition threshold',
    },
    'face_threshold': {
        'value': 0.5,
        'value_type': 'float',
        'description': 'Legacy alias for similarity threshold',
    },
    'blur_threshold': {
        'value': 50.0,
        'value_type': 'float',
        'description': 'Blur detection threshold',
    },
    'tilt_threshold': {
        'value': 0.25,
        'value_type': 'float',
        'description': 'Nose/eye alignment tilt threshold',
    },
    'min_face_area': {
        'value': 11000,
        'value_type': 'int',
        'description': 'Minimum face area in pixels',
    },
    'max_visitor_identities': {
        'value': 99999,
        'value_type': 'int',
        'description': 'Maximum number of unique visitor identities allowed in recognition memory',
    },
    'recognition_interval_frames': {
        'value': 5,
        'value_type': 'int',
        'description': 'Run full face recognition every N frames (intermediate frames use fast tracking overlay)',
    },
    'db_commit_interval_ms': {
        'value': 1200,
        'value_type': 'int',
        'description': 'Minimum interval between database commits during live recognition',
    },
    'max_event_match_candidates': {
        'value': 256,
        'value_type': 'int',
        'description': 'Maximum event visitor embeddings checked per recognition pass',
    },
    'async_visitor_pdf': {
        'value': True,
        'value_type': 'bool',
        'description': 'Generate visitor PDFs asynchronously to keep frame loop non-blocking',
    },
    'enforce_backend_camera_mode': {
        'value': False,
        'value_type': 'bool',
        'description': 'Require backend-owned cameras for active event AI processing (better realtime FPS)',
    },
    'face_model_name': {
        'value': 'buffalo_s',
        'value_type': 'string',
        'description': 'InsightFace model family used for detection/recognition',
    },
    'face_det_size': {
        'value': 320,
        'value_type': 'int',
        'description': 'Detector input size (square) for face analysis model',
    },
    'perf_capture_width': {
        'value': 512,
        'value_type': 'int',
        'description': 'Performance profile capture width for local webcams',
    },
    'perf_capture_height': {
        'value': 384,
        'value_type': 'int',
        'description': 'Performance profile capture height for local webcams',
    },
}

CONFIG_KEY_MAP = {
    'detection_confidence_threshold': ('FACE_CONFIDENCE_THRESHOLD', float),
    'similarity_threshold': ('FACE_SIMILARITY_THRESHOLD', float),
    'staff_similarity_threshold': ('STAFF_SIMILARITY_THRESHOLD', float),
    'face_threshold': ('FACE_SIMILARITY_THRESHOLD', float),
    'blur_threshold': ('BLUR_THRESHOLD', float),
    'tilt_threshold': ('TILT_THRESHOLD', float),
    'min_face_area': ('MIN_FACE_AREA', int),
    'max_visitor_identities': ('MAX_VISITOR_IDENTITIES', int),
    'recognition_interval_frames': ('RECOGNITION_INTERVAL_FRAMES', int),
    'db_commit_interval_ms': ('DB_COMMIT_INTERVAL_MS', int),
    'max_event_match_candidates': ('MAX_EVENT_MATCH_CANDIDATES', int),
    'async_visitor_pdf': ('ASYNC_VISITOR_PDF', bool),
    'enforce_backend_camera_mode': ('ENFORCE_BACKEND_CAMERA_MODE', bool),
    'face_model_name': ('FACE_MODEL_NAME', str),
    'face_det_size': ('FACE_DET_SIZE', int),
    'perf_capture_width': ('PERF_CAPTURE_WIDTH', int),
    'perf_capture_height': ('PERF_CAPTURE_HEIGHT', int),
}


def _ensure_default_settings():
    changed = False
    for key, payload in DEFAULT_SETTINGS.items():
        if not SystemSettings.query.get(key):
            db.session.add(SystemSettings(
                key=key,
                value=str(payload['value']),
                value_type=payload['value_type'],
                description=payload['description'],
            ))
            changed = True
    if changed:
        db.session.commit()


def _infer_value_type(value):
    if isinstance(value, bool):
        return 'bool'
    if isinstance(value, int) and not isinstance(value, bool):
        return 'int'
    if isinstance(value, float):
        return 'float'
    return 'string'


def _apply_runtime_config(key, value):
    if key not in CONFIG_KEY_MAP:
        return
    config_key, caster = CONFIG_KEY_MAP[key]
    if caster is bool:
        if isinstance(value, bool):
            current_app.config[config_key] = value
            return
        lowered = str(value).strip().lower()
        current_app.config[config_key] = lowered in ('1', 'true', 'yes', 'on')
        return
    current_app.config[config_key] = caster(value)


def _parse_setting_value(raw_value):
    if isinstance(raw_value, (int, float, bool)):
        return raw_value
    text = str(raw_value).strip()
    lowered = text.lower()
    if lowered in ('true', 'false'):
        return lowered == 'true'
    try:
        if '.' in text:
            return float(text)
        return int(text)
    except Exception:
        return text


def sync_runtime_settings_from_db():
    """Apply persisted system settings into runtime app config."""
    _ensure_default_settings()
    for row in SystemSettings.query.all():
        _apply_runtime_config(row.key, _parse_setting_value(row.value))


@settings_bp.route('/', methods=['GET'])
@jwt_required()
def get_settings():
    sync_runtime_settings_from_db()
    settings = SystemSettings.query.all()
    return jsonify([s.to_dict() for s in settings])

@settings_bp.route('/<key>', methods=['GET'])
@jwt_required()
def get_setting(key):
    setting = SystemSettings.query.get(key)
    if not setting:
        return jsonify({'error': 'Setting not found'}), 404
    return jsonify(setting.to_dict())

@settings_bp.route('/', methods=['POST'])
@jwt_required()
def update_settings():
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid payload'}), 400

    updated_keys = []
    
    for key, value in data.items():
        setting = SystemSettings.query.get(key)
        if setting:
            setting.value = str(value)
            setting.value_type = _infer_value_type(value)
            updated_keys.append(key)
        else:
            new_setting = SystemSettings(
                key=key,
                value=str(value),
                value_type=_infer_value_type(value),
                description=DEFAULT_SETTINGS.get(key, {}).get('description'),
            )
            db.session.add(new_setting)
            updated_keys.append(key)

        _apply_runtime_config(key, value)

    # Keep both threshold keys in sync for backward compatibility.
    if 'similarity_threshold' in data and 'face_threshold' not in data:
        alias = SystemSettings.query.get('face_threshold')
        if alias:
            alias.value = str(data['similarity_threshold'])
            alias.value_type = _infer_value_type(data['similarity_threshold'])
        else:
            db.session.add(SystemSettings(
                key='face_threshold',
                value=str(data['similarity_threshold']),
                value_type=_infer_value_type(data['similarity_threshold']),
                description=DEFAULT_SETTINGS['face_threshold']['description'],
            ))
        _apply_runtime_config('face_threshold', data['similarity_threshold'])
        updated_keys.append('face_threshold')

    if 'face_threshold' in data and 'similarity_threshold' not in data:
        alias = SystemSettings.query.get('similarity_threshold')
        if alias:
            alias.value = str(data['face_threshold'])
            alias.value_type = _infer_value_type(data['face_threshold'])
        else:
            db.session.add(SystemSettings(
                key='similarity_threshold',
                value=str(data['face_threshold']),
                value_type=_infer_value_type(data['face_threshold']),
                description=DEFAULT_SETTINGS['similarity_threshold']['description'],
            ))
        _apply_runtime_config('similarity_threshold', data['face_threshold'])
        updated_keys.append('similarity_threshold')

    db.session.commit()
    return jsonify({'updated': sorted(set(updated_keys))})


@settings_bp.route('/runtime', methods=['GET'])
@jwt_required()
def get_runtime_settings_status():
    sync_runtime_settings_from_db()
    payload = {}
    for key, (config_key, _) in CONFIG_KEY_MAP.items():
        payload[key] = current_app.config.get(config_key)
    return jsonify(payload)
