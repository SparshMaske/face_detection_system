from flask import request, jsonify, current_app
from flask_jwt_extended import jwt_required
from routes import settings_bp
from models import db
from models.camera import SystemSettings

DEFAULT_SETTINGS = {
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
}

CONFIG_KEY_MAP = {
    'similarity_threshold': ('FACE_SIMILARITY_THRESHOLD', float),
    'staff_similarity_threshold': ('STAFF_SIMILARITY_THRESHOLD', float),
    'face_threshold': ('FACE_SIMILARITY_THRESHOLD', float),
    'blur_threshold': ('BLUR_THRESHOLD', float),
    'tilt_threshold': ('TILT_THRESHOLD', float),
    'min_face_area': ('MIN_FACE_AREA', int),
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
    current_app.config[config_key] = caster(value)


@settings_bp.route('/', methods=['GET'])
@jwt_required()
def get_settings():
    _ensure_default_settings()
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
