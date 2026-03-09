import cv2
import datetime
import time
from threading import Event, Lock, Thread

import numpy as np
from flask import request, jsonify, Response, stream_with_context, current_app
from flask_jwt_extended import jwt_required
from routes import camera_bp
from models import db
from models.camera import Camera

_CLIENT_CLEANUP_TIMES = {}
_CLIENT_CLEANUP_LOCK = Lock()
_VIEWER_COUNTS = {}
_VIEWER_LOCK = Lock()
_RUNTIME_STATS = {}
_RUNTIME_LOCK = Lock()
_BACKGROUND_LOCK = Lock()
_BACKGROUND_THREAD = None
_BACKGROUND_STOP = Event()


def _default_runtime(camera_id):
    return {
        'camera_id': camera_id,
        'fps': 0.0,
        'window_start': time.monotonic(),
        'window_frames': 0,
        'last_frame_at': None,
        'source': 'idle',
        'processing_active': False,
        'camera_online': None,
        'last_error': '',
        'viewers': 0,
        'updated_at': datetime.datetime.utcnow().isoformat(),
    }


def _set_runtime(camera_id, **kwargs):
    with _RUNTIME_LOCK:
        item = _RUNTIME_STATS.setdefault(camera_id, _default_runtime(camera_id))
        for key, value in kwargs.items():
            if value is not None:
                item[key] = value
        item['updated_at'] = datetime.datetime.utcnow().isoformat()
        return dict(item)


def _mark_camera_frame(camera_id, source='unknown', processing_active=None, camera_online=True, last_error=''):
    with _RUNTIME_LOCK:
        item = _RUNTIME_STATS.setdefault(camera_id, _default_runtime(camera_id))
        now_mono = time.monotonic()
        item['window_frames'] = int(item.get('window_frames', 0)) + 1
        start = float(item.get('window_start', now_mono))
        elapsed = max(0.0001, now_mono - start)
        if elapsed >= 1.0:
            current_fps = float(item.get('window_frames', 0)) / elapsed
            prior_fps = float(item.get('fps', 0.0) or 0.0)
            item['fps'] = current_fps if prior_fps <= 0 else ((prior_fps * 0.6) + (current_fps * 0.4))
            item['window_start'] = now_mono
            item['window_frames'] = 0

        item['last_frame_at'] = datetime.datetime.utcnow().isoformat()
        item['source'] = source
        item['camera_online'] = camera_online
        item['last_error'] = last_error or ''
        if processing_active is not None:
            item['processing_active'] = bool(processing_active)
        item['updated_at'] = datetime.datetime.utcnow().isoformat()


def _viewer_count(camera_id):
    with _VIEWER_LOCK:
        return int(_VIEWER_COUNTS.get(camera_id, 0) or 0)


def _bump_viewers(camera_id, delta):
    with _VIEWER_LOCK:
        current = int(_VIEWER_COUNTS.get(camera_id, 0) or 0)
        next_count = max(0, current + int(delta))
        _VIEWER_COUNTS[camera_id] = next_count
    _set_runtime(camera_id, viewers=next_count)
    return next_count


def _background_worker_loop(app):
    fr_service = None
    active_camera_id = None
    active_source = None
    cap = None
    last_inactive_cleanup = datetime.datetime.min

    while not _BACKGROUND_STOP.is_set():
        try:
            with app.app_context():
                from routes.events import get_event_state_snapshot
                event_state = get_event_state_snapshot(sync=True) or {}
                workflow_active = bool(event_state.get('workflow_active'))
                selected_camera_id = str(event_state.get('selected_camera_id') or '').strip()
        except Exception as exc:
            app.logger.warning("Background camera worker: failed to read event state: %s", exc)
            time.sleep(0.4)
            continue

        if not workflow_active or not selected_camera_id:
            if active_camera_id:
                _set_runtime(active_camera_id, processing_active=False, source='idle')
            if cap is not None:
                cap.release()
                cap = None
            active_camera_id = None
            active_source = None
            time.sleep(0.25)
            continue

        # Avoid opening the same camera twice; live stream endpoint already processes frames.
        if _viewer_count(selected_camera_id) > 0:
            _set_runtime(selected_camera_id, processing_active=True, source='live-view')
            if cap is not None:
                cap.release()
                cap = None
            active_camera_id = None
            active_source = None
            time.sleep(0.2)
            continue

        with app.app_context():
            cam = Camera.query.filter_by(camera_id=selected_camera_id).first()

        if cam is None:
            _set_runtime(
                selected_camera_id,
                processing_active=False,
                source='background',
                camera_online=False,
                last_error='Camera not found',
            )
            if cap is not None:
                cap.release()
                cap = None
            active_camera_id = None
            active_source = None
            time.sleep(0.5)
            continue

        if str(cam.camera_type or '').lower() == 'browser':
            # Browser cameras require client-provided frames; no backend capture source exists.
            _set_runtime(
                selected_camera_id,
                processing_active=True,
                source='browser-client',
                camera_online=True,
                last_error='',
            )
            if cap is not None:
                cap.release()
                cap = None
            active_camera_id = None
            active_source = None
            time.sleep(0.2)
            continue

        if fr_service is None:
            try:
                from services.face_recognition import FaceRecognitionService
                fr_service = FaceRecognitionService()
            except Exception as exc:
                app.logger.warning("Background camera worker: face model unavailable: %s", exc)
                fr_service = None

        stream_url = (cam.stream_url or '0').strip()
        source = 0 if stream_url in ('', '0') else stream_url
        source_token = str(source)

        if cap is None or active_camera_id != selected_camera_id or active_source != source_token:
            if cap is not None:
                cap.release()
            cap = cv2.VideoCapture(source)
            active_camera_id = selected_camera_id
            active_source = source_token
            if not cap.isOpened():
                _set_runtime(
                    selected_camera_id,
                    processing_active=True,
                    source='background',
                    camera_online=False,
                    last_error='Could not open camera stream',
                )
                cap.release()
                cap = None
                time.sleep(0.9)
                continue
            _set_runtime(
                selected_camera_id,
                processing_active=True,
                source='background',
                camera_online=True,
                last_error='',
            )

        ret, frame = cap.read()
        if not ret or frame is None:
            _set_runtime(
                selected_camera_id,
                processing_active=True,
                source='background',
                camera_online=False,
                last_error='Failed to read camera frame',
            )
            cap.release()
            cap = None
            time.sleep(0.35)
            continue

        try:
            with app.app_context():
                frame, last_inactive_cleanup, meta = _apply_event_processing(
                    frame,
                    cam,
                    fr_service,
                    last_inactive_cleanup,
                )
            _mark_camera_frame(
                selected_camera_id,
                source='background',
                processing_active=bool(meta.get('event_active')),
                camera_online=True,
                last_error='',
            )
        except Exception as exc:
            _set_runtime(
                selected_camera_id,
                processing_active=True,
                source='background',
                camera_online=True,
                last_error=f'Processing error: {exc}',
            )

        fps_limit = int(getattr(cam, 'fps_limit', 10) or 10)
        target_fps = max(4, min(15, fps_limit))
        time.sleep(max(0.02, 1.0 / float(target_fps)))

    if cap is not None:
        cap.release()


def _ensure_background_worker():
    global _BACKGROUND_THREAD
    with _BACKGROUND_LOCK:
        if _BACKGROUND_THREAD and _BACKGROUND_THREAD.is_alive():
            return
        app = current_app._get_current_object()
        _BACKGROUND_STOP.clear()
        _BACKGROUND_THREAD = Thread(
            target=_background_worker_loop,
            args=(app,),
            name='camera-background-worker',
            daemon=True,
        )
        _BACKGROUND_THREAD.start()


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
    _ensure_background_worker()
    cams = Camera.query.all()
    return jsonify([c.to_dict() for c in cams])

@camera_bp.route('/', methods=['POST'])
@jwt_required()
def create_camera():
    _ensure_background_worker()
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
    _ensure_background_worker()
    cam = Camera.query.filter_by(camera_id=camera_id).first()
    if not cam:
        return jsonify({'error': 'Camera not found'}), 404
    if (cam.camera_type or '').lower() == 'browser':
        return jsonify({'error': 'Browser camera stream must use /api/camera/process-client-frame'}), 400

    def gen(camera):
        _bump_viewers(camera.camera_id, 1)
        fr_service = None
        last_inactive_cleanup = datetime.datetime.min
        cap = None
        try:
            # Import lazily to avoid hard-failing stream on model import issues.
            from services.face_recognition import FaceRecognitionService
            fr_service = FaceRecognitionService()
        except Exception as exc:
            current_app.logger.warning("Face model unavailable for stream: %s", exc)

        stream_url = (camera.stream_url or '0').strip()
        source = 0 if stream_url in ('', '0') else stream_url
        try:
            while True:
                if cap is None:
                    cap = cv2.VideoCapture(source)
                    if not cap.isOpened():
                        current_app.logger.warning("Could not open camera stream: %s", source)
                        _set_runtime(
                            camera.camera_id,
                            source='live-stream',
                            processing_active=True,
                            camera_online=False,
                            last_error='Could not open camera stream',
                        )
                        cap.release()
                        cap = None
                        # Give the background worker time to release/reopen if needed.
                        time.sleep(0.45)
                        continue
                    _set_runtime(
                        camera.camera_id,
                        source='live-stream',
                        processing_active=True,
                        camera_online=True,
                        last_error='',
                    )

                ret, frame = cap.read()
                if not ret or frame is None:
                    _set_runtime(
                        camera.camera_id,
                        source='live-stream',
                        processing_active=True,
                        camera_online=False,
                        last_error='Failed to read camera frame',
                    )
                    cap.release()
                    cap = None
                    time.sleep(0.1)
                    continue
                
                meta = None
                if fr_service is not None:
                    frame, last_inactive_cleanup, meta = _apply_event_processing(
                        frame,
                        cam,
                        fr_service,
                        last_inactive_cleanup,
                    )
                _mark_camera_frame(
                    camera.camera_id,
                    source='live-stream',
                    processing_active=bool((meta or {}).get('event_active', False)),
                    camera_online=True,
                    last_error='',
                )
                
                ret, jpeg = cv2.imencode('.jpg', frame)
                if not ret:
                    continue
                frame_bytes = jpeg.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n\r\n')
        except GeneratorExit:
            # Client disconnected.
            pass
        finally:
            if cap is not None:
                cap.release()
            _bump_viewers(camera.camera_id, -1)

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
    _ensure_background_worker()
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
    _mark_camera_frame(
        cam.camera_id,
        source='client-frame',
        processing_active=bool(meta.get('event_active')),
        camera_online=True,
        last_error='',
    )

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


@camera_bp.route('/runtime-status', methods=['GET'])
@jwt_required()
def runtime_status():
    _ensure_background_worker()
    camera_id = (request.args.get('camera_id') or '').strip()
    if not camera_id:
        return jsonify({'error': 'camera_id is required'}), 400

    cam = Camera.query.filter_by(camera_id=camera_id).first()
    if cam is None:
        return jsonify({'error': 'Camera not found'}), 404

    with _RUNTIME_LOCK:
        runtime = dict(_RUNTIME_STATS.get(camera_id, _default_runtime(camera_id)))
    runtime['viewers'] = _viewer_count(camera_id)
    runtime['camera_type'] = cam.camera_type
    runtime['camera_name'] = cam.name
    runtime['camera_online'] = bool(runtime.get('camera_online')) if runtime.get('camera_online') is not None else bool(cam.is_online)

    try:
        from routes.events import is_event_active_for_camera
        runtime['workflow_active'] = bool(is_event_active_for_camera(camera_id=camera_id))
    except Exception:
        runtime['workflow_active'] = False

    return jsonify(runtime)
