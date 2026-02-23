import cv2
import datetime
from threading import Lock

import numpy as np
from flask import request, jsonify, Response, stream_with_context, current_app
from flask_jwt_extended import jwt_required
from routes import camera_bp
from models import db
from models.camera import Camera

_CLIENT_CLEANUP_TIMES = {}
_CLIENT_CLEANUP_LOCK = Lock()


def _apply_event_processing(frame, camera, fr_service, last_inactive_cleanup):
    meta = {
        'event_active': False,
        'reason': 'unknown',
        'stats': None,
    }
    try:
        from routes.events import get_event_state_snapshot
        event_state = get_event_state_snapshot(sync=True)
        event_active = bool(event_state.get('workflow_active'))
        selected_camera_id = event_state.get('selected_camera_id')
        if selected_camera_id and selected_camera_id != camera.camera_id:
            event_active = False

        if event_active:
            meta['event_active'] = True
            if fr_service is None:
                meta['reason'] = 'model_unavailable'
            else:
                result = fr_service.process_frame_for_stream(
                    frame,
                    camera,
                    event_context=event_state,
                    return_stats=True,
                )
                if isinstance(result, tuple):
                    frame, stats = result
                    meta['stats'] = stats
                else:
                    frame = result
                meta['reason'] = 'processed'
        else:
            meta['reason'] = 'event_inactive'
            now_local = datetime.datetime.now()
            if fr_service is not None and (now_local - last_inactive_cleanup).total_seconds() >= 2.0:
                fr_service.finalize_active_sessions(
                    now_local=now_local,
                    event_start=event_state.get('start_time'),
                    event_end=event_state.get('end_time'),
                    camera_db_id=camera.id,
                )
                last_inactive_cleanup = now_local
    except Exception as exc:
        current_app.logger.warning("Stream frame annotation failed: %s", exc)
        meta['reason'] = 'processing_error'

    return frame, last_inactive_cleanup, meta


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
    if (cam.camera_type or '').lower() == 'browser':
        return jsonify({'error': 'Browser camera stream must use /api/camera/process-client-frame'}), 400

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
                    frame, last_inactive_cleanup, _ = _apply_event_processing(
                        frame,
                        cam,
                        fr_service,
                        last_inactive_cleanup,
                    )
                
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


@camera_bp.route('/process-client-frame', methods=['POST'])
@jwt_required()
def process_client_frame():
    """Accept a browser-captured frame and return processed JPEG with overlays."""
    camera_id = (request.form.get('camera_id') or request.args.get('camera_id') or 'EVENT_DEFAULT').strip()
    cam = Camera.query.filter_by(camera_id=camera_id).first()
    if cam is None and camera_id == 'EVENT_DEFAULT':
        cam = Camera(
            camera_id='EVENT_DEFAULT',
            name='Event Device Camera',
            location='Event Scheduler',
            stream_url='browser://device',
            camera_type='browser',
            is_active=True,
        )
        db.session.add(cam)
        db.session.commit()
    if cam is None:
        return jsonify({'error': 'Camera not found'}), 404

    upload = request.files.get('frame')
    frame_bytes = upload.read() if upload is not None else request.get_data(cache=False)
    if not frame_bytes:
        return jsonify({'error': 'frame is required'}), 400

    np_buf = np.frombuffer(frame_bytes, dtype=np.uint8)
    frame = cv2.imdecode(np_buf, cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify({'error': 'Invalid image frame'}), 400

    try:
        from services.face_recognition import FaceRecognitionService
        fr_service = FaceRecognitionService()
    except Exception as exc:
        current_app.logger.warning("Face model unavailable for client frame: %s", exc)
        fr_service = None

    with _CLIENT_CLEANUP_LOCK:
        last_cleanup = _CLIENT_CLEANUP_TIMES.get(cam.camera_id, datetime.datetime.min)
    frame, last_cleanup, meta = _apply_event_processing(frame, cam, fr_service, last_cleanup)
    with _CLIENT_CLEANUP_LOCK:
        _CLIENT_CLEANUP_TIMES[cam.camera_id] = last_cleanup

    info_text = None
    info_color = (80, 220, 80)
    if meta.get('reason') == 'processed':
        stats = meta.get('stats') or {}
        faces = int(stats.get('faces_detected') or 0)
        staff_hits = int(stats.get('staff_matches') or 0)
        visitor_hits = int(stats.get('known_visitors') or 0) + int(stats.get('new_visitors') or 0)
        if faces <= 0:
            info_text = "AI active: no face detected"
            info_color = (0, 215, 255)
        else:
            info_text = f"AI active: faces={faces} staff={staff_hits} visitors={visitor_hits}"
            info_color = (80, 220, 80)
    elif meta.get('reason') == 'event_inactive':
        info_text = "AI idle: event is not active for this camera"
        info_color = (0, 200, 255)
    elif meta.get('reason') == 'model_unavailable':
        info_text = "AI error: face model unavailable on backend"
        info_color = (0, 0, 255)
    elif meta.get('reason') == 'processing_error':
        info_text = "AI error: processing failed (check backend logs)"
        info_color = (0, 0, 255)

    if info_text:
        cv2.putText(
            frame,
            info_text,
            (16, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            info_color,
            2,
        )

    ok, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if not ok:
        return jsonify({'error': 'Failed to encode processed frame'}), 500

    return Response(
        jpeg.tobytes(),
        mimetype='image/jpeg',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
        },
    )
