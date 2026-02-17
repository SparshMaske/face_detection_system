import os
import uuid
from flask import request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from routes import staff_bp
from models import db
from models.staff import Staff, StaffImage
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
    if not staff_id or not name:
        return jsonify({'error': 'staff_id and name are required'}), 400
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
