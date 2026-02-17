from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        # user = User.query.get(user_id)
        # if user.role != 'admin': return jsonify({'error': 'Admin required'}), 403
        return fn(*args, **kwargs)
    return wrapper