import os
import re
import uuid
import cv2
from flask import request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from routes import staff_bp
from models import db
from models.staff import Staff, StaffImage
from models.camera import Camera
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _generate_staff_id():
    existing_ids = {
        (row[0] or '').strip()
        for row in db.session.query(Staff.staff_id).all()
        if (row[0] or '').strip()
    }
    max_suffix = 0
    for sid in existing_ids:
        match = re.search(r'(\d+)$', sid)
        if match:
            max_suffix = max(max_suffix, int(match.group(1)))

    next_num = max_suffix + 1
    while True:
        candidate = f"STF{next_num:03d}"
        if candidate not in existing_ids and not Staff.query.filter_by(staff_id=candidate).first():
            return candidate
        next_num += 1


def _open_capture_for_staff(camera):
    stream_url = (camera.stream_url or '0').strip()
    source = 0 if stream_url in ('', '0') else stream_url
    source_candidates = []
    if isinstance(source, int):
        source_candidates.append(source)
    else:
        raw = str(source).strip()
        if raw.isdigit():
            source_candidates.extend([int(raw), raw])
        else:
            source_candidates.append(raw)

    backends = [cv2.CAP_ANY]
    for name in ('CAP_AVFOUNDATION', 'CAP_V4L2', 'CAP_DSHOW', 'CAP_MSMF'):
        if hasattr(cv2, name):
            backends.append(getattr(cv2, name))

    for candidate in source_candidates:
        for backend in backends:
            cap = None
            try:
                cap = cv2.VideoCapture(candidate, backend)
            except TypeError:
                cap = cv2.VideoCapture(candidate)
            except Exception:
                cap = None
            if cap is None:
                continue

            try:
                width = int(getattr(camera, 'resolution_width', 0) or 0)
                height = int(getattr(camera, 'resolution_height', 0) or 0)
                fps_limit = int(getattr(camera, 'fps_limit', 0) or 0)
                if width > 0:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(width))
                if height > 0:
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(height))
                if fps_limit > 0:
                    cap.set(cv2.CAP_PROP_FPS, float(max(1, min(60, fps_limit))))
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass

            if cap.isOpened():
                return cap
            cap.release()
    return None

@staff_bp.route('/', methods=['GET'])
@jwt_required()
def get_staff():
    staff_list = Staff.query.all()
    return jsonify([s.to_dict() for s in staff_list])

@staff_bp.route('/', methods=['POST'])
@jwt_required()
def create_staff():
    data = request.form
    files = request.files.getlist('images')

    staff_id = (data.get('staff_id') or '').strip()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    if not staff_id:
        staff_id = _generate_staff_id()
    if Staff.query.filter_by(staff_id=staff_id).first():
        return jsonify({'error': f'Staff ID {staff_id} already exists'}), 409
    
    new_staff = Staff(
        staff_id=staff_id,
        name=name,
        department=(data.get('department') or '').strip() or None,
        position=(data.get('position') or '').strip() or None,
        email=(data.get('email') or '').strip() or None,
        phone=(data.get('phone') or '').strip() or None
    )
    try:
        db.session.add(new_staff)
        db.session.flush() # Get ID
        
        if files:
            from services.staff_manager import StaffManager
            manager = StaffManager()
            has_primary = False
            detected_embeddings = 0
            for file in files:
                if not file or not file.filename:
                    continue
                if not allowed_file(file.filename):
                    continue

                filename = secure_filename(f"{new_staff.staff_id}_{uuid.uuid4().hex}.jpg")
                filepath = os.path.join(current_app.config['STAFF_UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                # Process image and generate embedding
                embedding, _ = manager.process_staff_image(filepath)
                if embedding is None:
                    continue
                
                new_image = StaffImage(
                    staff_id=new_staff.id,
                    image_path=f"staff/{filename}",
                    embedding=embedding.tobytes() if embedding is not None else None,
                    is_primary=not has_primary
                )
                has_primary = True
                detected_embeddings += 1
                db.session.add(new_image)

            if detected_embeddings == 0:
                raise ValueError('No valid face embedding found in uploaded staff image(s)')
        else:
            raise ValueError('At least one staff image is required')
        
        db.session.commit()
        try:
            from services.face_recognition import FaceRecognitionService
            FaceRecognitionService().refresh_staff_cache()
        except Exception:
            # Staff creation should not fail if cache refresh fails.
            pass
        return jsonify(new_staff.to_dict()), 201
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Duplicate or invalid staff data'}), 400
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Failed to create staff")
        return jsonify({'error': str(exc)}), 500


@staff_bp.route('/capture-photo', methods=['GET'])
@jwt_required()
def capture_staff_photo():
    camera_id = (request.args.get('camera_id') or '').strip()
    if not camera_id:
        return jsonify({'error': 'camera_id is required'}), 400

    camera = Camera.query.filter_by(camera_id=camera_id).first()
    if camera is None:
        return jsonify({'error': 'Camera not found'}), 404
    if str(camera.camera_type or '').lower() == 'browser':
        return jsonify({'error': 'Browser camera capture is not available from backend. Use upload on this device.'}), 400

    frame_bytes = None
    try:
        from routes.camera import _get_latest_frame
        frame_bytes = _get_latest_frame(camera.camera_id, max_age_sec=2.0)
    except Exception:
        frame_bytes = None

    if frame_bytes:
        return current_app.response_class(
            frame_bytes,
            mimetype='image/jpeg',
            headers={'Cache-Control': 'no-cache, no-store, must-revalidate'},
        )

    cap = _open_capture_for_staff(camera)
    if cap is None:
        return jsonify({'error': 'Could not open selected camera'}), 500
    try:
        frame = None
        for _ in range(10):
            ok, raw_frame = cap.read()
            if ok and raw_frame is not None:
                frame = raw_frame
                break
        if frame is None:
            return jsonify({'error': 'Could not read frame from selected camera'}), 500

        ok, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 86])
        if not ok:
            return jsonify({'error': 'Failed to encode captured image'}), 500
        return current_app.response_class(
            jpeg.tobytes(),
            mimetype='image/jpeg',
            headers={'Cache-Control': 'no-cache, no-store, must-revalidate'},
        )
    finally:
        cap.release()

@staff_bp.route('/<int:id>', methods=['GET'])
@jwt_required()
def get_staff_member(id):
    staff = Staff.query.get_or_404(id)
    return jsonify(staff.to_dict())

@staff_bp.route('/<int:id>', methods=['PUT'])
@jwt_required()
def update_staff(id):
    staff = Staff.query.get_or_404(id)
    data = request.get_json() or request.form
    
    staff.name = data.get('name', staff.name)
    staff.department = data.get('department', staff.department)
    staff.position = data.get('position', staff.position)
    staff.email = data.get('email', staff.email)
    staff.phone = data.get('phone', staff.phone)
    
    db.session.commit()
    return jsonify(staff.to_dict())

@staff_bp.route('/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_staff(id):
    staff = Staff.query.get_or_404(id)
    db.session.delete(staff)
    db.session.commit()
    try:
        from services.face_recognition import FaceRecognitionService
        FaceRecognitionService().refresh_staff_cache()
    except Exception:
        pass
    return jsonify({'message': 'Staff member deleted'})
