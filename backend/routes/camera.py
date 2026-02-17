import cv2
import datetime
from flask import request, jsonify, Response, stream_with_context, current_app
from flask_jwt_extended import jwt_required
from routes import camera_bp
from models import db
from models.camera import Camera

@camera_bp.route('/', methods=['GET'])
@jwt_required()
def get_cameras():
    cams = Camera.query.all()
    return jsonify([c.to_dict() for c in cams])

@camera_bp.route('/', methods=['POST'])
@jwt_required()
def create_camera():
    data = request.get_json()
    cam = Camera(
        camera_id=data.get('camera_id'),
        name=data.get('name'),
        location=data.get('location'),
        stream_url=data.get('stream_url'),
        camera_type=data.get('camera_type', 'webcam'),
        # Extract resolution if nested in JSON from frontend
        resolution_width=data.get('resolution', {}).get('width', 1920),
        resolution_height=data.get('resolution', {}).get('height', 1080)
    )
    db.session.add(cam)
    db.session.commit()
    return jsonify(cam.to_dict()), 201

@camera_bp.route('/feed/<camera_id>', methods=['GET'])
def stream_feed(camera_id):
    """Stream MJPEG video with face detection overlays"""
    cam = Camera.query.filter_by(camera_id=camera_id).first()
    if not cam:
        return jsonify({'error': 'Camera not found'}), 404

    def gen(camera):
        fr_service = None
        last_inactive_cleanup = datetime.datetime.min
        try:
            # Import lazily to avoid hard-failing stream on model import issues.
            from services.face_recognition import FaceRecognitionService
            fr_service = FaceRecognitionService()
        except Exception as exc:
            current_app.logger.warning("Face model unavailable for stream: %s", exc)

        stream_url = (camera.stream_url or '0').strip()
        source = 0 if stream_url in ('', '0') else stream_url
        cap = cv2.VideoCapture(source)
        
        if not cap.isOpened():
            current_app.logger.error("Could not open camera stream: %s", source)
            return

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                if fr_service is not None:
                    try:
                        from routes.events import get_event_state_snapshot
                        event_state = get_event_state_snapshot(sync=True)
                        event_active = bool(event_state.get('workflow_active'))
                        selected_camera_id = event_state.get('selected_camera_id')
                        if selected_camera_id and selected_camera_id != cam.camera_id:
                            event_active = False

                        if event_active:
                            frame = fr_service.process_frame_for_stream(
                                frame,
                                cam,
                                event_context=event_state,
                            )
                        else:
                            now_local = datetime.datetime.now()
                            if (now_local - last_inactive_cleanup).total_seconds() >= 2.0:
                                fr_service.finalize_active_sessions(
                                    now_local=now_local,
                                    event_start=event_state.get('start_time'),
                                    event_end=event_state.get('end_time'),
                                    camera_db_id=cam.id,
                                )
                                last_inactive_cleanup = now_local
                    except Exception as exc:
                        current_app.logger.warning("Stream frame annotation failed: %s", exc)
                
                ret, jpeg = cv2.imencode('.jpg', frame)
                if not ret:
                    continue
                frame_bytes = jpeg.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n\r\n')
        finally:
            cap.release()

    return Response(
        stream_with_context(gen(cam)),
        mimetype='multipart/x-mixed-replace; boundary=frame',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
        },
    )
