import datetime
import json
import os
import re
import shutil
import time
from threading import Thread
from typing import Dict, List, Optional, Set, Tuple

import cv2
import numpy as np
from flask import current_app, has_app_context
from insightface.app import FaceAnalysis

from models import db
from models.visitor import Visitor, VisitorImage, VisitorSession


class FaceRecognitionService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FaceRecognitionService, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        print("Initializing InsightFace model...")
        model_name = os.getenv('FACE_MODEL_NAME', 'buffalo_s')
        det_size = int(os.getenv('FACE_DET_SIZE', 320) or 320)
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        configured_model_root = os.getenv(
            'FACE_MODEL_ROOT',
            os.path.join(base_dir, 'models', 'insightface'),
        )
        offline_only = os.getenv('FACE_OFFLINE_ONLY', '1').strip().lower() in ('1', 'true', 'yes', 'on')
        if has_app_context():
            model_name = str(current_app.config.get('FACE_MODEL_NAME', model_name) or model_name)
            det_size = int(current_app.config.get('FACE_DET_SIZE', det_size) or det_size)
            configured_model_root = str(
                current_app.config.get('FACE_MODEL_ROOT', configured_model_root) or configured_model_root
            )
            offline_only = bool(current_app.config.get('FACE_OFFLINE_ONLY', offline_only))
        det_size = max(224, min(640, det_size))

        candidate_roots = []
        for root in (configured_model_root, os.path.expanduser('~/.insightface')):
            token = os.path.abspath(os.path.expanduser(str(root)))
            if token not in candidate_roots:
                candidate_roots.append(token)

        selected_root = None
        for root in candidate_roots:
            model_dir_a = os.path.join(root, 'models', model_name)
            model_dir_b = os.path.join(root, model_name)
            if os.path.isdir(model_dir_a) or os.path.isdir(model_dir_b):
                selected_root = root
                break
        if selected_root is None:
            selected_root = candidate_roots[0]

        os.makedirs(selected_root, exist_ok=True)
        if offline_only:
            model_dir_a = os.path.join(selected_root, 'models', model_name)
            model_dir_b = os.path.join(selected_root, model_name)
            if not os.path.isdir(model_dir_a) and not os.path.isdir(model_dir_b):
                raise RuntimeError(
                    f"Offline model not found for '{model_name}'. "
                    f"Expected under '{selected_root}'. "
                    "Place InsightFace model files locally before startup."
                )

        self.app = FaceAnalysis(
            name=model_name,
            root=selected_root,
            providers=['CPUExecutionProvider'],
            allowed_modules=['detection', 'recognition'],
        )
        self.app.prepare(ctx_id=0, det_size=(det_size, det_size))
        print("InsightFace model loaded.")

        self._embeddings: Dict[int, np.ndarray] = {}
        self._embedding_history: Dict[int, List[np.ndarray]] = {}
        self._visitor_codes: Dict[int, str] = {}
        self._staff_embeddings: List[Tuple[int, np.ndarray]] = []
        self._active_tracks: Dict[int, Dict] = {}
        self._pending_candidates: List[Dict] = []
        self._next_visitor_num: Optional[int] = None
        self._last_cache_sync = datetime.datetime.min
        self._last_staff_cache_sync = datetime.datetime.min
        self._active_event_key: Optional[str] = None
        self._event_visitor_ids: Set[int] = set()
        self._event_embedding_history: Dict[int, List[np.ndarray]] = {}
        self._event_display_ids: Dict[int, str] = {}
        self._event_next_display_num: int = 1
        self._recent_event_matches: List[int] = []
        self._frame_index_by_camera: Dict[str, int] = {}
        self._pending_db_changes: bool = False
        self._last_db_commit_mono: float = time.monotonic()
        self._event_capture_buffers: Dict[str, Dict] = {}
        cascade_path = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
        self._fallback_face_cascade = cv2.CascadeClassifier(cascade_path)

    @staticmethod
    def _norm(embedding: np.ndarray) -> np.ndarray:
        if embedding is None:
            return None
        arr = np.asarray(embedding, dtype=np.float32).reshape(-1)
        n = float(np.linalg.norm(arr))
        if n <= 0:
            return None
        return arr / n

    @staticmethod
    def _iou(box_a, box_b) -> float:
        xa = max(box_a[0], box_b[0])
        ya = max(box_a[1], box_b[1])
        xb = min(box_a[2], box_b[2])
        yb = min(box_a[3], box_b[3])
        inter_w = max(0, xb - xa)
        inter_h = max(0, yb - ya)
        inter = inter_w * inter_h
        if inter == 0:
            return 0.0
        area_a = max(0, box_a[2] - box_a[0]) * max(0, box_a[3] - box_a[1])
        area_b = max(0, box_b[2] - box_b[0]) * max(0, box_b[3] - box_b[1])
        union = area_a + area_b - inter
        if union <= 0:
            return 0.0
        return inter / float(union)

    @staticmethod
    def _tilt_metrics(face) -> Tuple[bool, float, float]:
        kps = getattr(face, 'kps', None)
        if kps is None or len(kps) < 3:
            return False, 0.0, 0.0
        left_eye = kps[0]
        right_eye = kps[1]
        nose = kps[2]

        dx = float(right_eye[0] - left_eye[0])
        eye_distance = abs(dx)
        if eye_distance == 0:
            # Follow P_app behavior: treat invalid eye geometry as tilted/rejected.
            return True, 1.0, 0.0
        eyes_mid_x = (float(left_eye[0]) + float(right_eye[0])) / 2.0
        yaw_ratio = abs(float(nose[0]) - eyes_mid_x) / eye_distance
        # P_app tilt check is based on nose-vs-eye-center deviation ratio.
        return True, yaw_ratio, 0.0

    @staticmethod
    def _draw_papp_style_box(frame, bbox, label, color, thickness=1, font_scale=0.55, text_thickness=1, y_offset=-10):
        """
        Match P_app.py box visibility parameters:
        - Recognized/New: slimmer box, readable label at y1-10
        - Too Far/Blurry: box thickness=1, font_scale=0.5, text near y1
        - Tilted: slim box with visible label
        """
        x1, y1, x2, y2 = bbox
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, max(1, int(thickness)))
        if not label:
            return
        text_x = max(0, x1)
        desired_y = y1 + int(y_offset)
        if desired_y < 16:
            desired_y = y1 + 16
        ((text_w, text_h), text_baseline) = cv2.getTextSize(
            str(label),
            cv2.FONT_HERSHEY_SIMPLEX,
            float(font_scale),
            max(1, int(text_thickness)),
        )
        bg_x1 = max(0, text_x - 2)
        bg_y1 = max(0, desired_y - text_h - 4)
        bg_x2 = min(frame.shape[1] - 1, text_x + text_w + 4)
        bg_y2 = min(frame.shape[0] - 1, desired_y + text_baseline + 2)
        cv2.rectangle(frame, (bg_x1, bg_y1), (bg_x2, bg_y2), (0, 0, 0), -1)
        cv2.putText(
            frame,
            label,
            (text_x, desired_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            float(font_scale),
            color,
            max(1, int(text_thickness)),
        )

    def _sync_embedding_cache(self, force=False):
        now = datetime.datetime.now()
        if not force and (now - self._last_cache_sync).total_seconds() < 15:
            return

        visitors = Visitor.query.filter(Visitor.embedding.isnot(None)).all()
        cache_embeddings = {}
        cache_history = {}
        cache_codes = {}
        for visitor in visitors:
            emb = np.frombuffer(visitor.embedding, dtype=np.float32)
            normed = self._norm(emb)
            if normed is not None:
                cache_embeddings[visitor.id] = normed
                prior_samples = list(self._embedding_history.get(visitor.id, []))
                merged_samples = prior_samples + [normed]
                cache_history[visitor.id] = self._dedupe_and_limit_embeddings(merged_samples, limit=5)
                cache_codes[visitor.id] = visitor.visitor_id
        self._embeddings = cache_embeddings
        self._embedding_history = cache_history
        self._visitor_codes = cache_codes
        self._last_cache_sync = now

    def _sync_staff_cache(self, force=False):
        now = datetime.datetime.now()
        if not force and (now - self._last_staff_cache_sync).total_seconds() < 15:
            return

        from models.staff import StaffImage

        cache_staff = []
        staff_images = StaffImage.query.filter(StaffImage.embedding.isnot(None)).all()
        for img in staff_images:
            if not img.staff or not img.staff.is_active:
                continue
            stored = np.frombuffer(img.embedding, dtype=np.float32)
            stored = self._norm(stored)
            if stored is None:
                continue
            cache_staff.append((img.staff.id, stored))

        self._staff_embeddings = cache_staff
        self._last_staff_cache_sync = now

    def refresh_staff_cache(self):
        self._last_staff_cache_sync = datetime.datetime.min
        self._sync_staff_cache(force=True)

    def _get_next_visitor_id(self) -> str:
        used_numbers = set()
        for value in db.session.query(Visitor.visitor_id).all():
            visitor_id = value[0] or ''
            match = re.match(r'^ID(\d+)$', visitor_id)
            if match:
                used_numbers.add(int(match.group(1)))

        if self._next_visitor_num is None:
            self._next_visitor_num = 1

        while self._next_visitor_num in used_numbers:
            self._next_visitor_num += 1

        visitor_code = f"ID{self._next_visitor_num}"
        self._next_visitor_num += 1
        return visitor_code

    def _upsert_pending_candidate(self, bbox, embedding, now_local, camera_db_id=None):
        best_idx = None
        best_rank = -1.0
        for idx, cand in enumerate(self._pending_candidates):
            if camera_db_id is not None and cand.get('camera_id') != camera_db_id:
                continue
            cand_bbox = cand.get('bbox')
            iou = self._iou(cand_bbox, bbox) if cand_bbox is not None else 0.0
            cand_embedding = cand.get('embedding')
            similarity = float(np.dot(embedding, cand_embedding)) if cand_embedding is not None else -1.0

            # Keep pending identity stable when face shifts quickly:
            # use IoU plus embedding agreement (P_app-style sticky IDs).
            if iou < 0.30 and similarity < 0.70:
                continue

            rank = (iou * 0.65) + (max(similarity, 0.0) * 0.35)
            if rank > best_rank:
                best_rank = rank
                best_idx = idx

        if best_idx is None:
            candidate = {
                'bbox': bbox,
                'embedding': embedding,
                'count': 1,
                'first_seen': now_local,
                'last_seen': now_local,
                'camera_id': camera_db_id,
            }
            self._pending_candidates.append(candidate)
            return candidate

        candidate = self._pending_candidates[best_idx]
        candidate['bbox'] = bbox
        candidate['last_seen'] = now_local
        candidate['count'] = int(candidate.get('count', 0)) + 1
        prior_embedding = candidate.get('embedding')
        if prior_embedding is not None:
            blended = self._norm((prior_embedding * 0.6) + (embedding * 0.4))
            candidate['embedding'] = blended if blended is not None else embedding
        else:
            candidate['embedding'] = embedding
        return candidate

    def _clear_pending_for_bbox(self, bbox, camera_db_id=None):
        self._pending_candidates = [
            cand for cand in self._pending_candidates
            if (
                (camera_db_id is not None and cand.get('camera_id') != camera_db_id)
                or self._iou(cand.get('bbox'), bbox) <= 0.30
            )
        ]

    def _clear_specific_candidate(self, candidate):
        self._pending_candidates = [cand for cand in self._pending_candidates if cand is not candidate]

    def _purge_pending_candidates(self, now_local):
        self._pending_candidates = [
            cand for cand in self._pending_candidates
            if (now_local - cand.get('last_seen', now_local)).total_seconds() <= 2.5
        ]

    def _save_primary_face_image(self, frame, bbox, visitor_code) -> Optional[str]:
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        face_w = max(1, x2 - x1)
        face_h = max(1, y2 - y1)

        expand_x = int(face_w * 0.30)
        expand_y_top = int(face_h * 0.40)
        expand_y_bottom = int(face_h * 1.60)

        nx1 = max(0, x1 - expand_x)
        ny1 = max(0, y1 - expand_y_top)
        nx2 = min(w, x2 + expand_x)
        ny2 = min(h, y2 + expand_y_bottom)

        crop = frame[ny1:ny2, nx1:nx2]
        if crop.size == 0:
            crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        # Guard against occasional bad bbox offsets: ensure stored image still contains a face.
        try:
            has_face = len(self._detect_faces(crop)) > 0
        except Exception:
            has_face = True
        if not has_face:
            tight_pad_x = int(face_w * 0.12)
            tight_pad_top = int(face_h * 0.18)
            tight_pad_bottom = int(face_h * 0.42)
            tx1 = max(0, x1 - tight_pad_x)
            ty1 = max(0, y1 - tight_pad_top)
            tx2 = min(w, x2 + tight_pad_x)
            ty2 = min(h, y2 + tight_pad_bottom)
            tight_crop = frame[ty1:ty2, tx1:tx2]
            if tight_crop.size != 0:
                crop = tight_crop

        filename = f"{visitor_code}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}.jpg"
        rel_path = os.path.join('visitors', filename)
        abs_path = os.path.join(current_app.config['UPLOAD_FOLDER'], rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        saved = bool(cv2.imwrite(abs_path, crop))
        return rel_path if saved else None

    def _resolve_upload_image_path(self, raw_path: Optional[str]) -> Optional[str]:
        if not raw_path:
            return None

        if os.path.isabs(raw_path) and os.path.exists(raw_path):
            return raw_path

        upload_root = current_app.config.get('UPLOAD_FOLDER')
        visitor_root = current_app.config.get('VISITOR_UPLOAD_FOLDER')
        normalized = str(raw_path).replace('\\', '/')
        if normalized.startswith('/'):
            normalized = normalized.lstrip('/')
        if normalized.startswith('static/'):
            normalized = normalized[len('static/'):]
        if normalized.startswith('uploads/'):
            normalized = normalized[len('uploads/'):]

        candidates = []
        if upload_root:
            candidates.append(os.path.join(upload_root, normalized))
        if visitor_root:
            candidates.append(os.path.join(visitor_root, os.path.basename(normalized)))

        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None

    @staticmethod
    def _normalize_datetime_value(value) -> Optional[datetime.datetime]:
        if value is None:
            return None
        if isinstance(value, datetime.datetime):
            return value
        try:
            return datetime.datetime.fromisoformat(str(value))
        except Exception:
            return None

    @staticmethod
    def _safe_token(raw_value: str) -> str:
        text = str(raw_value or '').strip()
        if not text:
            return 'event'
        cleaned = []
        for ch in text:
            if ch.isalnum() or ch in ('-', '_'):
                cleaned.append(ch)
            elif ch.isspace():
                cleaned.append('_')
            else:
                cleaned.append('_')
        normalized = ''.join(cleaned).strip('_')
        return normalized or 'event'

    def _is_deferred_event_mode(self, event_context: Optional[dict]) -> bool:
        if not isinstance(event_context, dict):
            return False
        if not bool(event_context.get('workflow_active')):
            return False
        deferred_default = True
        if has_app_context():
            deferred_default = bool(current_app.config.get('DEFER_EVENT_RECOGNITION', True))
        return deferred_default

    def _event_temp_root(self) -> str:
        reports_root = current_app.config.get('REPORTS_FOLDER')
        root = os.path.join(reports_root, 'event_temp')
        os.makedirs(root, exist_ok=True)
        return root

    def _event_temp_dir(self, event_id: str, event_name: Optional[str] = None) -> str:
        safe_event_id = self._safe_token(event_id or 'event')
        safe_name = self._safe_token(event_name or '')
        folder_name = f"{safe_name}_{safe_event_id}" if safe_name else safe_event_id
        return os.path.join(self._event_temp_root(), folder_name)

    def _buffer_manifest_path(self, buffer_obj: Dict) -> str:
        return os.path.join(buffer_obj['temp_dir'], 'captures.jsonl')

    def _load_captures_from_manifest(self, manifest_path: str) -> List[Dict]:
        captures = []
        if not manifest_path or not os.path.exists(manifest_path):
            return captures
        try:
            with open(manifest_path, 'r', encoding='utf-8') as fp:
                for line in fp:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                        if isinstance(item, dict):
                            captures.append(item)
                    except Exception:
                        continue
        except Exception:
            return []
        return captures

    def _append_capture_to_manifest(self, buffer_obj: Dict, capture_item: Dict):
        manifest_path = self._buffer_manifest_path(buffer_obj)
        try:
            with open(manifest_path, 'a', encoding='utf-8') as fp:
                fp.write(json.dumps(capture_item, ensure_ascii=True) + '\n')
        except Exception:
            # Keep runtime processing uninterrupted if disk append fails.
            pass

    def _get_or_create_event_capture_buffer(self, event_context: Optional[dict], camera_db_id: Optional[int]) -> Optional[Dict]:
        if not isinstance(event_context, dict):
            return None
        event_id = str(event_context.get('event_id') or '').strip()
        if not event_id:
            return None

        event_name = str(event_context.get('event_name') or '').strip()
        start_dt = self._normalize_datetime_value(event_context.get('start_time'))
        end_dt = self._normalize_datetime_value(event_context.get('end_time'))
        key = event_id

        buffer_obj = self._event_capture_buffers.get(key)
        if buffer_obj is None:
            temp_dir = self._event_temp_dir(event_id, event_name)
            captures_dir = os.path.join(temp_dir, 'captures')
            embeddings_dir = os.path.join(temp_dir, 'embeddings')
            os.makedirs(captures_dir, exist_ok=True)
            os.makedirs(embeddings_dir, exist_ok=True)

            buffer_obj = {
                'event_id': event_id,
                'event_name': event_name,
                'start_time': start_dt.isoformat() if start_dt else None,
                'end_time': end_dt.isoformat() if end_dt else None,
                'camera_id': camera_db_id,
                'temp_dir': temp_dir,
                'captures_dir': captures_dir,
                'embeddings_dir': embeddings_dir,
                'captures': [],
                'tracks': [],
                'next_seq': 1,
            }
            # Recover any persisted captures when process restarts.
            persisted = self._load_captures_from_manifest(self._buffer_manifest_path(buffer_obj))
            if persisted:
                buffer_obj['captures'] = persisted
                max_seq = 0
                for item in persisted:
                    try:
                        max_seq = max(max_seq, int(item.get('seq') or 0))
                    except Exception:
                        continue
                buffer_obj['next_seq'] = max_seq + 1

            self._event_capture_buffers[key] = buffer_obj
        else:
            if camera_db_id is not None:
                buffer_obj['camera_id'] = camera_db_id
            if start_dt:
                buffer_obj['start_time'] = start_dt.isoformat()
            if end_dt:
                buffer_obj['end_time'] = end_dt.isoformat()
            if event_name:
                buffer_obj['event_name'] = event_name

        return buffer_obj

    def _extract_face_to_shoulder_crop(self, frame, bbox):
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        face_w = max(1, x2 - x1)
        face_h = max(1, y2 - y1)

        expand_x = int(face_w * 0.30)
        expand_y_top = int(face_h * 0.40)
        expand_y_bottom = int(face_h * 1.60)

        nx1 = max(0, x1 - expand_x)
        ny1 = max(0, y1 - expand_y_top)
        nx2 = min(w, x2 + expand_x)
        ny2 = min(h, y2 + expand_y_bottom)

        crop = frame[ny1:ny2, nx1:nx2]
        if crop.size == 0:
            crop = frame[y1:y2, x1:x2]
        return crop

    def _purge_stale_event_tracks(self, buffer_obj: Dict, now_local: datetime.datetime):
        buffer_obj['tracks'] = [
            track for track in buffer_obj.get('tracks', [])
            if (now_local - track.get('last_seen', now_local)).total_seconds() <= 2.8
        ]

    def _match_or_create_event_track(
        self,
        buffer_obj: Dict,
        bbox,
        now_local: datetime.datetime,
        camera_db_id: Optional[int],
    ) -> Dict:
        self._purge_stale_event_tracks(buffer_obj, now_local)
        tracks = buffer_obj.setdefault('tracks', [])
        best_track = None
        best_iou = 0.0
        for track in tracks:
            if camera_db_id is not None and track.get('camera_id') != camera_db_id:
                continue
            iou = self._iou(track.get('bbox'), bbox)
            if iou > best_iou:
                best_iou = iou
                best_track = track

        if best_track is None or best_iou < 0.35:
            best_track = {
                'bbox': bbox,
                'camera_id': camera_db_id,
                'last_seen': now_local,
                'last_capture_at': None,
            }
            tracks.append(best_track)
        else:
            best_track['bbox'] = bbox
            best_track['last_seen'] = now_local

        return best_track

    def _save_event_capture(
        self,
        buffer_obj: Dict,
        frame,
        bbox,
        embedding: np.ndarray,
        now_local: datetime.datetime,
        det_score: float,
        blur_value: float,
        camera_db_id: Optional[int],
    ) -> Optional[Dict]:
        seq = int(buffer_obj.get('next_seq', 1))
        buffer_obj['next_seq'] = seq + 1
        capture_name = f"cap_{seq:06d}.jpg"
        emb_name = f"cap_{seq:06d}.npy"
        capture_path = os.path.join(buffer_obj['captures_dir'], capture_name)
        emb_path = os.path.join(buffer_obj['embeddings_dir'], emb_name)

        crop = self._extract_face_to_shoulder_crop(frame, bbox)
        if crop.size == 0:
            return None
        if not bool(cv2.imwrite(capture_path, crop)):
            return None
        try:
            np.save(emb_path, embedding.astype(np.float32))
        except Exception:
            try:
                os.remove(capture_path)
            except Exception:
                pass
            return None

        capture_item = {
            'seq': seq,
            'timestamp': now_local.isoformat(),
            'image_path': capture_path,
            'embedding_path': emb_path,
            'bbox': [int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])],
            'det_score': float(det_score or 0.0),
            'blur': float(blur_value or 0.0),
            'camera_id': camera_db_id,
        }
        buffer_obj.setdefault('captures', []).append(capture_item)
        self._append_capture_to_manifest(buffer_obj, capture_item)
        return capture_item

    def _load_event_buffer_by_id(self, event_id: str, event_name: Optional[str] = None) -> Optional[Dict]:
        if not event_id:
            return None
        existing = self._event_capture_buffers.get(event_id)
        if existing is not None:
            return existing

        temp_dir = self._event_temp_dir(event_id, event_name)
        if not os.path.isdir(temp_dir):
            return None
        captures_dir = os.path.join(temp_dir, 'captures')
        embeddings_dir = os.path.join(temp_dir, 'embeddings')
        if not os.path.isdir(captures_dir) or not os.path.isdir(embeddings_dir):
            return None

        buffer_obj = {
            'event_id': event_id,
            'event_name': event_name or '',
            'start_time': None,
            'end_time': None,
            'camera_id': None,
            'temp_dir': temp_dir,
            'captures_dir': captures_dir,
            'embeddings_dir': embeddings_dir,
            'captures': self._load_captures_from_manifest(os.path.join(temp_dir, 'captures.jsonl')),
            'tracks': [],
            'next_seq': 1,
        }
        max_seq = 0
        for item in buffer_obj['captures']:
            try:
                max_seq = max(max_seq, int(item.get('seq') or 0))
            except Exception:
                continue
        buffer_obj['next_seq'] = max_seq + 1
        self._event_capture_buffers[event_id] = buffer_obj
        return buffer_obj

    def _derive_event_key(self, event_context: Optional[dict]) -> Optional[str]:
        if not event_context or not isinstance(event_context, dict):
            return None
        event_id = str(event_context.get('event_id') or '').strip()
        if event_id:
            return f"event:{event_id}"

        event_name = str(event_context.get('event_name') or '').strip()
        start_dt = self._normalize_datetime_value(event_context.get('start_time'))
        end_dt = self._normalize_datetime_value(event_context.get('end_time'))
        if event_name and start_dt and end_dt:
            return f"event:{event_name}:{start_dt.isoformat()}:{end_dt.isoformat()}"
        return None

    def _commit_if_needed(self, changed=False, force=False):
        if changed:
            self._pending_db_changes = True
        if not self._pending_db_changes:
            return False

        interval_ms = 1200
        if has_app_context():
            interval_ms = int(current_app.config.get('DB_COMMIT_INTERVAL_MS', interval_ms) or interval_ms)
        interval_sec = max(0.08, float(interval_ms) / 1000.0)
        now_mono = time.monotonic()
        if not force and (now_mono - self._last_db_commit_mono) < interval_sec:
            return False

        try:
            db.session.commit()
            self._pending_db_changes = False
            self._last_db_commit_mono = now_mono
            return True
        except Exception as exc:
            db.session.rollback()
            self._pending_db_changes = False
            if has_app_context():
                current_app.logger.warning("Failed to persist recognition update: %s", exc)
            return False

    def _touch_recent_event_match(self, visitor_db_id: Optional[int]):
        if not visitor_db_id:
            return
        self._recent_event_matches = [vid for vid in self._recent_event_matches if vid != visitor_db_id]
        self._recent_event_matches.insert(0, int(visitor_db_id))
        if len(self._recent_event_matches) > 256:
            self._recent_event_matches = self._recent_event_matches[:256]

    def _iter_recent_tracks(self, now_local: datetime.datetime, camera_db_id: Optional[int], max_age_sec: float = 2.4):
        for visitor_db_id, track in list(self._active_tracks.items()):
            if camera_db_id is not None and track.get('camera_id') != camera_db_id:
                continue
            bbox = track.get('bbox')
            if bbox is None:
                continue
            last_seen = track.get('last_seen', now_local)
            if (now_local - last_seen).total_seconds() > float(max_age_sec):
                continue
            yield visitor_db_id, track

    def _fast_detect_bboxes(self, frame):
        cascade = self._fallback_face_cascade
        if cascade is None or cascade.empty():
            return []
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            detections = cascade.detectMultiScale(
                gray,
                scaleFactor=1.18,
                minNeighbors=4,
                minSize=(46, 46),
            )
        except Exception:
            return []
        result = []
        for (x, y, w, h) in detections:
            result.append((int(x), int(y), int(x + w), int(y + h)))
        return result

    def _update_tracks_from_fast_detections(self, detections, now_local, camera_db_id: Optional[int]):
        if not detections:
            return
        used_tracks = set()
        for det_bbox in detections:
            best_db_id = None
            best_iou = 0.0
            for visitor_db_id, track in self._iter_recent_tracks(now_local, camera_db_id, max_age_sec=4.5):
                if visitor_db_id in used_tracks:
                    continue
                iou = self._iou(track.get('bbox'), det_bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_db_id = visitor_db_id
            if best_db_id is not None and best_iou >= 0.14:
                track = self._active_tracks.get(best_db_id)
                if track is not None:
                    track['bbox'] = det_bbox
                    track['last_seen'] = now_local
                    used_tracks.add(best_db_id)

    def _draw_active_tracks_overlay(self, frame, now_local, camera_db_id: Optional[int], score_hint: Optional[float] = None):
        count = 0
        for visitor_db_id, track in self._iter_recent_tracks(now_local, camera_db_id, max_age_sec=3.2):
            bbox = track.get('bbox')
            if bbox is None:
                continue
            label = self._get_or_assign_event_display_id(visitor_db_id)
            if score_hint is not None:
                label = f"{label} ({score_hint:.2f})"
            self._draw_papp_style_box(
                frame,
                bbox,
                label,
                (0, 255, 0),
                thickness=1,
                font_scale=0.55,
                text_thickness=1,
                y_offset=-10,
            )
            count += 1
        return count

    def _load_event_identity_from_db(
        self,
        event_start: Optional[datetime.datetime],
        event_end: Optional[datetime.datetime],
    ):
        from sqlalchemy import or_

        self._event_visitor_ids = set()
        self._event_embedding_history = {}
        self._event_display_ids = {}
        self._event_next_display_num = 1
        if not event_start or not event_end:
            return

        session_rows = VisitorSession.query.filter(
            VisitorSession.entry_time <= event_end,
            or_(VisitorSession.exit_time.is_(None), VisitorSession.exit_time >= event_start),
        ).order_by(VisitorSession.entry_time.asc(), VisitorSession.id.asc()).all()

        visitor_ids = {row.visitor_id for row in session_rows if row.visitor_id}
        if not visitor_ids:
            return

        visitors = Visitor.query.filter(Visitor.id.in_(visitor_ids), Visitor.embedding.isnot(None)).all()
        for visitor in visitors:
            emb = np.frombuffer(visitor.embedding, dtype=np.float32)
            normed = self._norm(emb)
            if normed is None:
                continue
            self._event_visitor_ids.add(visitor.id)
            self._event_embedding_history[visitor.id] = [normed]
        for row in session_rows:
            visitor_db_id = row.visitor_id
            if visitor_db_id in self._event_visitor_ids and visitor_db_id not in self._event_display_ids:
                self._event_display_ids[visitor_db_id] = f"ID{self._event_next_display_num}"
                self._event_next_display_num += 1

    def _get_or_assign_event_display_id(self, visitor_db_id: int) -> str:
        if visitor_db_id in self._event_display_ids:
            return self._event_display_ids[visitor_db_id]
        label = f"ID{self._event_next_display_num}"
        self._event_display_ids[visitor_db_id] = label
        self._event_next_display_num += 1
        return label

    def _ensure_event_identity_state(self, event_context: Optional[dict]):
        event_key = self._derive_event_key(event_context)
        if event_key == self._active_event_key:
            return

        # Reset event matching state so each new event starts with fresh visitor embeddings.
        self._active_event_key = event_key
        self._active_tracks = {}
        self._pending_candidates = []
        self._recent_event_matches = []
        self._frame_index_by_camera = {}

        start_dt = self._normalize_datetime_value((event_context or {}).get('start_time'))
        end_dt = self._normalize_datetime_value((event_context or {}).get('end_time'))
        self._load_event_identity_from_db(start_dt, end_dt)

    def _visitor_has_usable_image(self, visitor: Visitor) -> bool:
        if self._resolve_upload_image_path(visitor.primary_image_path):
            return True
        for img in visitor.images or []:
            if self._resolve_upload_image_path(getattr(img, 'image_path', None)):
                return True
        return False

    @staticmethod
    def _dedupe_and_limit_embeddings(samples: List[np.ndarray], limit: int = 5) -> List[np.ndarray]:
        cleaned: List[np.ndarray] = []
        for sample in samples:
            normed = FaceRecognitionService._norm(sample)
            if normed is None:
                continue
            if cleaned and float(np.dot(cleaned[-1], normed)) >= 0.9995:
                continue
            cleaned.append(normed)
        if len(cleaned) > limit:
            cleaned = cleaned[-limit:]
        return cleaned

    def _append_embedding_sample(self, visitor_db_id: int, embedding: np.ndarray, limit: int = 5) -> Optional[np.ndarray]:
        if embedding is None:
            return None
        samples = list(self._embedding_history.get(visitor_db_id, []))
        samples.append(embedding)
        samples = self._dedupe_and_limit_embeddings(samples, limit=limit)
        if not samples:
            return None
        self._embedding_history[visitor_db_id] = samples
        centroid = self._norm(np.mean(np.stack(samples), axis=0))
        if centroid is not None:
            self._embeddings[visitor_db_id] = centroid
        return centroid

    def _best_similarity_to_visitor(self, embedding: np.ndarray, visitor_db_id: int) -> float:
        best_score = -1.0
        samples = self._embedding_history.get(visitor_db_id, [])
        for sample in samples:
            score = float(np.dot(embedding, sample))
            if score > best_score:
                best_score = score
        if best_score < 0.0:
            reference = self._embeddings.get(visitor_db_id)
            if reference is not None:
                best_score = float(np.dot(embedding, reference))
        return best_score

    @staticmethod
    def _best_similarity_in_samples(embedding: np.ndarray, samples: List[np.ndarray]) -> float:
        best_score = -1.0
        for sample in samples or []:
            score = float(np.dot(embedding, sample))
            if score > best_score:
                best_score = score
        return best_score

    def _append_event_embedding_sample(self, visitor_db_id: int, embedding: np.ndarray, limit: int = 5):
        if embedding is None:
            return
        samples = list(self._event_embedding_history.get(visitor_db_id, []))
        samples.append(embedding)
        self._event_embedding_history[visitor_db_id] = self._dedupe_and_limit_embeddings(samples, limit=limit)
        self._event_visitor_ids.add(visitor_db_id)

    def _match_event_visitor(self, embedding: np.ndarray, threshold: float, camera_db_id: Optional[int] = None):
        best_db_id = None
        best_score = -1.0
        max_candidates = 256
        if has_app_context():
            max_candidates = int(current_app.config.get('MAX_EVENT_MATCH_CANDIDATES', max_candidates) or max_candidates)
        max_candidates = max(24, max_candidates)

        prioritized_ids = []
        seen = set()
        for visitor_db_id, track in self._active_tracks.items():
            if camera_db_id is not None and track.get('camera_id') != camera_db_id:
                continue
            if visitor_db_id in self._event_visitor_ids and visitor_db_id not in seen:
                prioritized_ids.append(visitor_db_id)
                seen.add(visitor_db_id)
        for visitor_db_id in self._recent_event_matches:
            if visitor_db_id in self._event_visitor_ids and visitor_db_id not in seen:
                prioritized_ids.append(visitor_db_id)
                seen.add(visitor_db_id)

        if max_candidates > 0:
            remaining_slots = max(0, max_candidates - len(prioritized_ids))
            if remaining_slots > 0:
                for db_id in sorted(self._event_visitor_ids):
                    if db_id in seen:
                        continue
                    prioritized_ids.append(db_id)
                    seen.add(db_id)
                    remaining_slots -= 1
                    if remaining_slots <= 0:
                        break
        else:
            for db_id in sorted(self._event_visitor_ids):
                if db_id in seen:
                    continue
                prioritized_ids.append(db_id)
                seen.add(db_id)

        for db_id in prioritized_ids:
            score = self._best_similarity_in_samples(embedding, self._event_embedding_history.get(db_id, []))
            if score > best_score:
                best_score = score
                best_db_id = db_id
        if best_db_id is not None and best_score >= threshold:
            self._touch_recent_event_match(best_db_id)
            return best_db_id, best_score
        return None, best_score

    def _match_visitor(self, embedding: np.ndarray, threshold: float):
        best_db_id = None
        best_score = -1.0
        for db_id in self._embeddings.keys():
            score = self._best_similarity_to_visitor(embedding, db_id)
            if score > best_score:
                best_score = score
                best_db_id = db_id
        if best_db_id is not None and best_score >= threshold:
            return best_db_id, best_score
        return None, best_score

    def _match_recent_active_track(
        self,
        embedding: np.ndarray,
        bbox,
        now_local: datetime.datetime,
        camera_db_id: Optional[int],
        base_threshold: float,
    ):
        best_db_id = None
        best_score = -1.0
        best_rank = -1.0
        similarity_floor = max(0.30, float(base_threshold) - 0.14)
        for visitor_db_id, track in self._active_tracks.items():
            if camera_db_id is not None and track.get('camera_id') != camera_db_id:
                continue

            track_last_seen = track.get('last_seen', now_local)
            if (now_local - track_last_seen).total_seconds() > 4.0:
                continue

            reference_embedding = track.get('embedding')
            if reference_embedding is None:
                reference_embedding = self._embeddings.get(visitor_db_id)
            if reference_embedding is None:
                continue

            similarity = float(np.dot(embedding, reference_embedding))
            bank_similarity = self._best_similarity_to_visitor(embedding, visitor_db_id)
            if bank_similarity > similarity:
                similarity = bank_similarity
            track_bbox = track.get('bbox')
            iou = self._iou(track_bbox, bbox) if track_bbox is not None else 0.0

            if similarity < similarity_floor and not (iou >= 0.45 and similarity >= 0.24):
                continue

            rank = (similarity * 1.0) + (iou * 0.20)
            if rank > best_rank:
                best_rank = rank
                best_score = similarity
                best_db_id = visitor_db_id

        if best_db_id is not None:
            return best_db_id, best_score
        return None, best_score

    def _resolve_identity(
        self,
        embedding: np.ndarray,
        bbox,
        now_local: datetime.datetime,
        camera_db_id: Optional[int],
        visitor_threshold: float,
        staff_threshold: float,
    ):
        """
        Recognition order (as requested):
        1) Compare against staff embeddings.
        2) Compare against existing visitor embeddings.
        3) If no match -> caller registers as new visitor.
        """
        matched_staff, staff_score = self.find_matching_staff(
            embedding,
            db.session,
            threshold=staff_threshold,
            with_score=True,
        )
        if matched_staff is not None:
            return 'staff', matched_staff, staff_score

        matched_db_id, matched_score = self._match_recent_active_track(
            embedding,
            bbox,
            now_local,
            camera_db_id,
            base_threshold=visitor_threshold,
        )
        if matched_db_id is None:
            matched_db_id, matched_score = self._match_event_visitor(
                embedding,
                visitor_threshold,
                camera_db_id=camera_db_id,
            )
        if matched_db_id is not None:
            return 'visitor', matched_db_id, matched_score

        return None, None, -1.0

    def _process_frame_for_deferred_event(self, frame, camera=None, event_context=None, return_stats=False):
        now_local = datetime.datetime.now()
        cfg = current_app.config
        conf_threshold = float(cfg.get('FACE_CONFIDENCE_THRESHOLD', 0.5))
        blur_threshold = float(cfg.get('BLUR_THRESHOLD', 50.0))
        tilt_threshold = float(cfg.get('TILT_THRESHOLD', 0.25))
        min_face_area = int(cfg.get('MIN_FACE_AREA', 11000))
        capture_interval = float(cfg.get('EVENT_CAPTURE_INTERVAL_SEC', 0.85))
        max_event_captures = int(cfg.get('EVENT_MAX_CAPTURES', 99999) or 99999)

        camera_db_id = getattr(camera, 'id', None)
        camera_type = str(getattr(camera, 'camera_type', '') or '').lower()
        is_browser_camera = camera_type == 'browser'
        if is_browser_camera:
            conf_threshold = min(conf_threshold, 0.20)
            blur_threshold = min(blur_threshold, 22.0)
            min_face_area = min(min_face_area, 2600)
            tilt_threshold = max(tilt_threshold, 0.45)

        buffer_obj = self._get_or_create_event_capture_buffer(event_context, camera_db_id)
        faces = self._detect_faces(frame)
        stats = {
            'faces_detected': int(len(faces)),
            'staff_matches': 0,
            'new_visitors': 0,
            'known_visitors': 0,
            'rejected_faces': 0,
            'captures_saved': 0,
        }

        for face in faces:
            box = face.bbox.astype(int)
            x1, y1, x2, y2 = map(int, box)
            h, w = frame.shape[:2]
            x1 = max(0, min(x1, w - 1))
            x2 = max(0, min(x2, w - 1))
            y1 = max(0, min(y1, h - 1))
            y2 = max(0, min(y2, h - 1))
            if x2 <= x1 or y2 <= y1:
                continue

            current_bbox = (x1, y1, x2, y2)
            score = float(getattr(face, 'det_score', 0.0))
            if score < conf_threshold:
                stats['rejected_faces'] += 1
                continue

            face_area = (x2 - x1) * (y2 - y1)
            if face_area < min_face_area:
                stats['rejected_faces'] += 1
                continue

            try:
                gray = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
                blur_value = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            except Exception:
                blur_value = 0.0
            if blur_value < blur_threshold:
                stats['rejected_faces'] += 1
                continue

            has_pose, yaw_ratio, _ = self._tilt_metrics(face)
            if has_pose and yaw_ratio > tilt_threshold:
                stats['rejected_faces'] += 1
                continue

            emb = getattr(face, 'normed_embedding', None)
            if emb is None:
                emb = getattr(face, 'embedding', None)
            emb = self._norm(emb)
            if emb is None:
                stats['rejected_faces'] += 1
                continue

            if buffer_obj is not None and len(buffer_obj.get('captures', [])) < max_event_captures:
                track = self._match_or_create_event_track(
                    buffer_obj,
                    current_bbox,
                    now_local,
                    camera_db_id,
                )
                last_capture_at = track.get('last_capture_at')
                should_capture = (
                    last_capture_at is None
                    or (now_local - last_capture_at).total_seconds() >= max(0.20, capture_interval)
                )
                if should_capture:
                    saved_item = self._save_event_capture(
                        buffer_obj,
                        frame,
                        current_bbox,
                        emb,
                        now_local,
                        det_score=score,
                        blur_value=blur_value,
                        camera_db_id=camera_db_id,
                    )
                    if saved_item is not None:
                        track['last_capture_at'] = now_local
                        stats['captures_saved'] += 1

            # Deferred mode explicitly shows only face-detected marker and no IDs.
            self._draw_papp_style_box(
                frame,
                current_bbox,
                'Face Detected',
                (0, 255, 0),
                thickness=1,
                font_scale=0.55,
                text_thickness=1,
                y_offset=-10,
            )

        if not faces:
            fallback_boxes = self._fast_detect_bboxes(frame)
            for bbox in fallback_boxes:
                self._draw_papp_style_box(
                    frame,
                    bbox,
                    'Face Detected',
                    (0, 215, 255),
                    thickness=1,
                    font_scale=0.5,
                    text_thickness=1,
                    y_offset=0,
                )
            stats['faces_detected'] = max(int(stats.get('faces_detected', 0)), int(len(fallback_boxes)))

        if return_stats:
            return frame, stats
        return frame

    def _load_capture_embedding(self, capture_item: Dict) -> Optional[np.ndarray]:
        emb_path = str(capture_item.get('embedding_path') or '').strip()
        if not emb_path or not os.path.exists(emb_path):
            return None
        try:
            arr = np.load(emb_path)
        except Exception:
            return None
        return self._norm(arr)

    def _cluster_event_captures(self, captures: List[Dict], threshold: float) -> List[Dict]:
        clusters: List[Dict] = []
        sorted_captures = sorted(captures, key=lambda item: item.get('timestamp') or datetime.datetime.min)

        for capture in sorted_captures:
            emb = capture.get('embedding')
            if emb is None:
                continue

            best_idx = -1
            best_score = -1.0
            for idx, cluster in enumerate(clusters):
                centroid = cluster.get('centroid')
                if centroid is None:
                    continue
                score = float(np.dot(emb, centroid))
                if score > best_score:
                    best_score = score
                    best_idx = idx

            if best_idx >= 0 and best_score >= threshold:
                cluster = clusters[best_idx]
                cluster.setdefault('samples', []).append(capture)
                ts = capture.get('timestamp')
                if ts is not None:
                    if cluster.get('first_seen') is None or ts < cluster['first_seen']:
                        cluster['first_seen'] = ts
                        cluster['snapshot_path'] = capture.get('image_path')
                    if cluster.get('last_seen') is None or ts > cluster['last_seen']:
                        cluster['last_seen'] = ts
                sample_embeddings = [item.get('embedding') for item in cluster.get('samples', []) if item.get('embedding') is not None]
                if sample_embeddings:
                    centroid = self._norm(np.mean(np.stack(sample_embeddings[-12:]), axis=0))
                    if centroid is not None:
                        cluster['centroid'] = centroid
                continue

            ts = capture.get('timestamp')
            clusters.append({
                'samples': [capture],
                'centroid': emb,
                'first_seen': ts,
                'last_seen': ts,
                'snapshot_path': capture.get('image_path'),
            })

        # Merge any residual duplicate clusters conservatively.
        merged = True
        while merged and len(clusters) > 1:
            merged = False
            for i in range(len(clusters)):
                if merged:
                    break
                for j in range(i + 1, len(clusters)):
                    score = float(np.dot(clusters[i]['centroid'], clusters[j]['centroid']))
                    if score < (threshold + 0.02):
                        continue
                    left = clusters[i]
                    right = clusters[j]
                    left['samples'].extend(right.get('samples', []))
                    left['samples'] = sorted(
                        left['samples'],
                        key=lambda item: item.get('timestamp') or datetime.datetime.min,
                    )
                    left['first_seen'] = min(
                        [item.get('timestamp') for item in left['samples'] if item.get('timestamp') is not None] or [left.get('first_seen')]
                    )
                    left['last_seen'] = max(
                        [item.get('timestamp') for item in left['samples'] if item.get('timestamp') is not None] or [left.get('last_seen')]
                    )
                    left['snapshot_path'] = left['samples'][0].get('image_path') if left['samples'] else left.get('snapshot_path')
                    sample_embeddings = [item.get('embedding') for item in left['samples'] if item.get('embedding') is not None]
                    if sample_embeddings:
                        centroid = self._norm(np.mean(np.stack(sample_embeddings[-16:]), axis=0))
                        if centroid is not None:
                            left['centroid'] = centroid
                    del clusters[j]
                    merged = True
                    break

        clusters.sort(key=lambda item: item.get('first_seen') or datetime.datetime.max)
        return clusters

    def _copy_capture_for_visitor(self, image_path: Optional[str], visitor_code: str) -> Optional[str]:
        if not image_path or not os.path.exists(image_path):
            return None
        filename = f"{visitor_code}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}.jpg"
        rel_path = os.path.join('visitors', filename)
        abs_path = os.path.join(current_app.config['UPLOAD_FOLDER'], rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        try:
            shutil.copyfile(image_path, abs_path)
            return rel_path
        except Exception:
            return None

    def finalize_event_data(self, event_record: Dict, delete_temp: bool = False) -> Dict:
        event_id = str((event_record or {}).get('event_id') or '').strip()
        event_name = str((event_record or {}).get('event_name') or '').strip()
        if not event_id:
            raise ValueError('event_id is required to finalize event data')

        buffer_obj = self._load_event_buffer_by_id(event_id, event_name=event_name)
        if buffer_obj is None:
            return {
                'event_id': event_id,
                'event_name': event_name,
                'captured_faces': 0,
                'staff_matches': 0,
                'visitor_clusters': 0,
                'new_visitors': 0,
                'existing_visitors': 0,
                'deleted_temp_data': bool(delete_temp),
            }

        captures = []
        for item in buffer_obj.get('captures', []):
            ts = self._normalize_datetime_value(item.get('timestamp'))
            emb = self._load_capture_embedding(item)
            if ts is None or emb is None:
                continue
            captures.append({
                **item,
                'timestamp': ts,
                'embedding': emb,
            })

        if not captures:
            deleted = self.delete_event_temp_data(event_id, event_name=event_name) if delete_temp else False
            return {
                'event_id': event_id,
                'event_name': event_name,
                'captured_faces': 0,
                'staff_matches': 0,
                'visitor_clusters': 0,
                'new_visitors': 0,
                'existing_visitors': 0,
                'deleted_temp_data': bool(deleted),
            }

        self._sync_embedding_cache(force=True)
        self._sync_staff_cache(force=True)
        visitor_threshold = float(current_app.config.get('FACE_SIMILARITY_THRESHOLD', 0.5))
        staff_threshold = float(current_app.config.get('STAFF_SIMILARITY_THRESHOLD', 0.65))
        cluster_threshold = float(current_app.config.get('EVENT_CLUSTER_THRESHOLD', max(visitor_threshold, 0.60)))

        staff_matches = 0
        visitor_capture_rows = []
        for capture in captures:
            matched_staff, _score = self.find_matching_staff(
                capture['embedding'],
                db.session,
                threshold=staff_threshold,
                with_score=True,
            )
            if matched_staff is not None:
                staff_matches += 1
                continue
            visitor_capture_rows.append(capture)

        clusters = self._cluster_event_captures(visitor_capture_rows, threshold=cluster_threshold)
        start_dt = self._normalize_datetime_value((event_record or {}).get('start_time'))
        end_dt = self._normalize_datetime_value((event_record or {}).get('end_time'))

        new_visitors = 0
        existing_visitors = 0
        camera_db_id = buffer_obj.get('camera_id')
        if camera_db_id is None:
            camera_db_id = None
            if isinstance(event_record, dict):
                # Event registry stores camera_id as string camera token; DB id remains optional.
                camera_db_id = None

        for cluster in clusters:
            first_seen = cluster.get('first_seen') or datetime.datetime.now()
            last_seen = cluster.get('last_seen') or first_seen
            if start_dt:
                first_seen = max(first_seen, start_dt)
            if end_dt:
                last_seen = min(last_seen, end_dt)
            if last_seen < first_seen:
                last_seen = first_seen

            matched_db_id, _match_score = self._match_visitor(cluster.get('centroid'), threshold=visitor_threshold)
            visitor = Visitor.query.get(matched_db_id) if matched_db_id is not None else None

            if visitor is None:
                visitor_code = self._get_next_visitor_id()
                snapshot_rel = self._copy_capture_for_visitor(cluster.get('snapshot_path'), visitor_code)
                visitor = Visitor(
                    visitor_id=visitor_code,
                    primary_image_path=snapshot_rel,
                    embedding=cluster.get('centroid').astype(np.float32).tobytes() if cluster.get('centroid') is not None else None,
                    first_seen=first_seen,
                    last_seen=last_seen,
                    visit_count=1,
                )
                db.session.add(visitor)
                db.session.flush()
                if snapshot_rel:
                    db.session.add(VisitorImage(visitor_id=visitor.id, image_path=snapshot_rel, captured_at=first_seen))
                if cluster.get('centroid') is not None:
                    self._embeddings[visitor.id] = cluster['centroid']
                    self._embedding_history[visitor.id] = [cluster['centroid']]
                self._visitor_codes[visitor.id] = visitor_code
                new_visitors += 1
            else:
                existing_visitors += 1
                visitor.first_seen = min(visitor.first_seen or first_seen, first_seen)
                visitor.last_seen = max(visitor.last_seen or last_seen, last_seen)
                visitor.visit_count = int(visitor.visit_count or 0) + 1
                if cluster.get('centroid') is not None:
                    updated = self._append_embedding_sample(visitor.id, cluster['centroid'], limit=8)
                    if updated is not None:
                        visitor.embedding = updated.astype(np.float32).tobytes()
                snapshot_rel = self._copy_capture_for_visitor(cluster.get('snapshot_path'), visitor.visitor_id)
                if snapshot_rel:
                    visitor.primary_image_path = snapshot_rel
                    db.session.add(VisitorImage(visitor_id=visitor.id, image_path=snapshot_rel, captured_at=first_seen))

            session = VisitorSession(
                visitor_id=visitor.id,
                camera_id=camera_db_id,
                entry_time=first_seen,
                exit_time=last_seen,
                is_active=False,
            )
            db.session.add(session)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        self._sync_embedding_cache(force=True)
        deleted = self.delete_event_temp_data(event_id, event_name=event_name) if delete_temp else False
        return {
            'event_id': event_id,
            'event_name': event_name,
            'captured_faces': len(captures),
            'staff_matches': staff_matches,
            'visitor_clusters': len(clusters),
            'new_visitors': new_visitors,
            'existing_visitors': existing_visitors,
            'deleted_temp_data': bool(deleted),
        }

    def delete_event_temp_data(self, event_id: str, event_name: Optional[str] = None) -> bool:
        if not event_id:
            return False
        buffer_obj = self._event_capture_buffers.pop(event_id, None)
        temp_dir = None
        if buffer_obj:
            temp_dir = buffer_obj.get('temp_dir')
        if not temp_dir:
            temp_dir = self._event_temp_dir(event_id, event_name=event_name)
        if not temp_dir or not os.path.isdir(temp_dir):
            return False
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return True
        except Exception:
            return False

    def get_event_temp_status(self, event_id: str, event_name: Optional[str] = None) -> Dict:
        if not event_id:
            return {'event_id': '', 'capture_count': 0, 'temp_data_exists': False}
        buffer_obj = self._load_event_buffer_by_id(event_id, event_name=event_name)
        if buffer_obj is None:
            return {'event_id': event_id, 'capture_count': 0, 'temp_data_exists': False}
        capture_count = len(buffer_obj.get('captures', []))
        temp_data_exists = os.path.isdir(buffer_obj.get('temp_dir', ''))
        return {
            'event_id': event_id,
            'capture_count': capture_count,
            'temp_data_exists': bool(temp_data_exists and capture_count > 0),
        }

    def _detect_faces(self, frame):
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        except Exception:
            rgb = None
        faces = self.app.get(rgb) if rgb is not None else []
        if faces:
            return faces
        try:
            faces = self.app.get(frame)
            if faces:
                return faces
        except Exception:
            pass
        return []

    def _draw_fallback_face_boxes(self, frame):
        cascade = self._fallback_face_cascade
        if cascade is None or cascade.empty():
            return 0
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            detections = cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(50, 50))
        except Exception:
            return 0

        count = 0
        for (x, y, w, h) in detections:
            count += 1
            bbox = (int(x), int(y), int(x + w), int(y + h))
            self._draw_papp_style_box(
                frame,
                bbox,
                "Face",
                (0, 215, 255),
                thickness=1,
                font_scale=0.5,
                text_thickness=1,
                y_offset=0,
            )
        return count

    def _ensure_active_session(
        self,
        visitor: Visitor,
        camera_db_id: Optional[int],
        now_local: datetime.datetime,
        event_start: Optional[datetime.datetime] = None,
    ):
        track = self._active_tracks.get(visitor.id)
        if track is not None:
            return track.get('session_id')

        active_session = VisitorSession.query.filter_by(visitor_id=visitor.id, is_active=True).order_by(
            VisitorSession.entry_time.desc()
        ).first()
        if active_session is None:
            entry_time = max(now_local, event_start) if event_start else now_local
            active_session = VisitorSession(
                visitor_id=visitor.id,
                camera_id=camera_db_id,
                entry_time=entry_time,
                is_active=True,
            )
            db.session.add(active_session)
            visitor.visit_count = (visitor.visit_count or 0) + 1
            db.session.flush()

        self._active_tracks[visitor.id] = {
            'last_seen': now_local,
            'bbox': None,
            'session_id': active_session.id,
            'camera_id': camera_db_id,
            'embedding': self._embeddings.get(visitor.id),
        }
        return active_session.id

    def _generate_visitor_pdf(
        self,
        visitor_db_id: int,
        event_start: Optional[datetime.datetime] = None,
        event_end: Optional[datetime.datetime] = None,
    ):
        def _run_generation(app_obj=None):
            try:
                if app_obj is not None:
                    with app_obj.app_context():
                        from services.report_generator import ReportGenerator
                        visitor = Visitor.query.get(visitor_db_id)
                        if visitor:
                            ReportGenerator().generate_visitor_pdf(
                                visitor,
                                event_start=event_start,
                                event_end=event_end,
                            )
                else:
                    from services.report_generator import ReportGenerator
                    visitor = Visitor.query.get(visitor_db_id)
                    if visitor:
                        ReportGenerator().generate_visitor_pdf(
                            visitor,
                            event_start=event_start,
                            event_end=event_end,
                        )
            except Exception as exc:
                if has_app_context():
                    current_app.logger.warning("Visitor PDF generation failed for visitor_id=%s: %s", visitor_db_id, exc)

        async_enabled = True
        if has_app_context():
            async_enabled = bool(current_app.config.get('ASYNC_VISITOR_PDF', True))
        if async_enabled and has_app_context():
            app_obj = current_app._get_current_object()
            Thread(target=_run_generation, args=(app_obj,), daemon=True).start()
            return
        _run_generation()

    def _finalize_absent_sessions(
        self,
        valid_db_ids,
        invalid_bboxes,
        now_local,
        event_start: Optional[datetime.datetime] = None,
        event_end: Optional[datetime.datetime] = None,
        camera_db_id: Optional[int] = None,
    ):
        grace = float(current_app.config.get('SESSION_GRACE_PERIOD', 2.0))
        to_remove = []
        changed = False

        for visitor_db_id, track in list(self._active_tracks.items()):
            if camera_db_id is not None and track.get('camera_id') != camera_db_id:
                continue
            if visitor_db_id in valid_db_ids:
                continue

            last_bbox = track.get('bbox')
            is_still_present = False
            if last_bbox is not None:
                for invalid_bbox in invalid_bboxes:
                    if self._iou(last_bbox, invalid_bbox) > 0.30:
                        is_still_present = True
                        break

            if is_still_present:
                track['last_seen'] = now_local
                continue

            last_seen = track.get('last_seen', now_local)
            if (now_local - last_seen).total_seconds() <= grace:
                continue

            close_time = now_local
            if event_end is not None:
                close_time = min(close_time, event_end)
            if event_start is not None:
                close_time = max(close_time, event_start)

            session_id = track.get('session_id')
            if session_id:
                session = VisitorSession.query.get(session_id)
                if session and session.is_active:
                    session.is_active = False
                    session.exit_time = close_time
                    changed = True

            visitor = Visitor.query.get(visitor_db_id)
            if visitor:
                visitor.last_seen = close_time
                changed = True

            to_remove.append(visitor_db_id)
            self._generate_visitor_pdf(visitor_db_id, event_start=event_start, event_end=event_end)

        for visitor_db_id in to_remove:
            self._active_tracks.pop(visitor_db_id, None)

        return changed

    def finalize_active_sessions(
        self,
        now_local: Optional[datetime.datetime] = None,
        event_start: Optional[datetime.datetime] = None,
        event_end: Optional[datetime.datetime] = None,
        camera_db_id: Optional[int] = None,
    ):
        reference_time = now_local or datetime.datetime.now()
        changed = self._finalize_absent_sessions(
            valid_db_ids=set(),
            invalid_bboxes=[],
            now_local=reference_time,
            event_start=event_start,
            event_end=event_end,
            camera_db_id=camera_db_id,
        )

        # Safety net: if process restarted and in-memory tracking is empty,
        # close stale DB active sessions when event is not active anymore.
        query = VisitorSession.query.filter_by(is_active=True)
        if camera_db_id is not None:
            query = query.filter_by(camera_id=camera_db_id)
        active_sessions = query.all()
        for session in active_sessions:
            close_time = reference_time
            if event_end is not None:
                close_time = min(close_time, event_end)
            if event_start is not None:
                close_time = max(close_time, event_start)
            session.is_active = False
            session.exit_time = close_time
            visitor = Visitor.query.get(session.visitor_id)
            if visitor:
                visitor.last_seen = close_time
                self._generate_visitor_pdf(visitor.id, event_start=event_start, event_end=event_end)
            changed = True

        if changed:
            try:
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                current_app.logger.warning("Failed to finalize sessions: %s", exc)

    def get_embedding(self, image_array):
        if image_array is None or image_array.size == 0:
            return None
        faces = self.app.get(image_array)
        if not faces:
            return None
        raw = getattr(faces[0], 'normed_embedding', None)
        if raw is None:
            raw = getattr(faces[0], 'embedding', None)
        return self._norm(raw)

    def process_frame_for_stream(self, frame, camera=None, event_context=None, return_stats=False):
        now_local = datetime.datetime.now()
        if self._is_deferred_event_mode(event_context):
            return self._process_frame_for_deferred_event(
                frame,
                camera=camera,
                event_context=event_context,
                return_stats=return_stats,
            )

        self._sync_embedding_cache()
        self._sync_staff_cache()
        self._ensure_event_identity_state(event_context)

        cfg = current_app.config
        conf_threshold = float(cfg.get('FACE_CONFIDENCE_THRESHOLD', 0.5))
        similarity_threshold = float(cfg.get('FACE_SIMILARITY_THRESHOLD', 0.5))
        staff_similarity_threshold = float(cfg.get('STAFF_SIMILARITY_THRESHOLD', 0.65))
        blur_threshold = float(cfg.get('BLUR_THRESHOLD', 50.0))
        tilt_threshold = float(cfg.get('TILT_THRESHOLD', 0.25))
        min_face_area = int(cfg.get('MIN_FACE_AREA', 11000))

        camera_db_id = getattr(camera, 'id', None)
        camera_key = str(getattr(camera, 'camera_id', '') or (camera_db_id if camera_db_id is not None else 'GLOBAL'))
        camera_type = str(getattr(camera, 'camera_type', '') or '').lower()
        is_browser_camera = camera_type == 'browser'
        if is_browser_camera:
            # Browser/device cameras (phone/laptop) are often noisier and lower detail;
            # relax validation gates so detection remains practical in live sessions.
            conf_threshold = min(conf_threshold, 0.20)
            similarity_threshold = min(similarity_threshold, 0.43)
            blur_threshold = min(blur_threshold, 22.0)
            min_face_area = min(min_face_area, 2600)
            tilt_threshold = max(tilt_threshold, 0.45)

        frame_index = int(self._frame_index_by_camera.get(camera_key, 0)) + 1
        self._frame_index_by_camera[camera_key] = frame_index
        recognition_interval = max(1, int(cfg.get('RECOGNITION_INTERVAL_FRAMES', 3) or 3))
        if is_browser_camera:
            recognition_interval = max(recognition_interval, 4)
        has_recent_tracks = any(True for _ in self._iter_recent_tracks(now_local, camera_db_id, max_age_sec=2.2))
        run_full_recognition = (frame_index % recognition_interval) == 0 or not has_recent_tracks

        event_start = event_context.get('start_time') if event_context else None
        event_end = event_context.get('end_time') if event_context else None
        if not run_full_recognition:
            detections = self._fast_detect_bboxes(frame)
            self._update_tracks_from_fast_detections(detections, now_local, camera_db_id)
            active_overlay_count = self._draw_active_tracks_overlay(frame, now_local, camera_db_id)
            self._purge_pending_candidates(now_local)
            self._commit_if_needed(changed=False, force=False)
            stats = {
                'faces_detected': int(max(len(detections), active_overlay_count)),
                'staff_matches': 0,
                'new_visitors': 0,
                'known_visitors': int(active_overlay_count),
                'rejected_faces': 0,
            }
            if return_stats:
                return frame, stats
            return frame

        faces = self._detect_faces(frame)
        valid_db_ids = set()
        invalid_bboxes = []
        changed = False
        force_commit = False
        stats = {
            'faces_detected': int(len(faces)),
            'staff_matches': 0,
            'new_visitors': 0,
            'known_visitors': 0,
            'rejected_faces': 0,
        }

        for face in faces:
            box = face.bbox.astype(int)
            x1, y1, x2, y2 = map(int, box)
            h, w = frame.shape[:2]
            x1 = max(0, min(x1, w - 1))
            x2 = max(0, min(x2, w - 1))
            y1 = max(0, min(y1, h - 1))
            y2 = max(0, min(y2, h - 1))
            if x2 <= x1 or y2 <= y1:
                continue

            current_bbox = (x1, y1, x2, y2)
            score = float(getattr(face, 'det_score', 0.0))
            if score < conf_threshold:
                invalid_bboxes.append(current_bbox)
                stats['rejected_faces'] += 1
                self._draw_papp_style_box(
                    frame,
                    current_bbox,
                    "Low Conf",
                    (0, 165, 255),
                    thickness=1,
                    font_scale=0.5,
                    text_thickness=1,
                    y_offset=0,
                )
                continue

            face_area = (x2 - x1) * (y2 - y1)
            if face_area < min_face_area:
                invalid_bboxes.append(current_bbox)
                stats['rejected_faces'] += 1
                self._draw_papp_style_box(
                    frame,
                    current_bbox,
                    "Too Far",
                    (0, 0, 255),
                    thickness=1,
                    font_scale=0.5,
                    text_thickness=1,
                    y_offset=0,
                )
                continue

            try:
                gray = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
                blur_value = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            except Exception:
                blur_value = 0.0
            if blur_value < blur_threshold:
                invalid_bboxes.append(current_bbox)
                stats['rejected_faces'] += 1
                self._draw_papp_style_box(
                    frame,
                    current_bbox,
                    "Blurry",
                    (0, 0, 255),
                    thickness=1,
                    font_scale=0.5,
                    text_thickness=1,
                    y_offset=0,
                )
                continue

            has_pose, yaw_ratio, _ = self._tilt_metrics(face)
            if has_pose and yaw_ratio > tilt_threshold:
                invalid_bboxes.append(current_bbox)
                stats['rejected_faces'] += 1
                self._draw_papp_style_box(
                    frame,
                    current_bbox,
                    "Tilted",
                    (255, 0, 255),
                    thickness=1,
                    font_scale=0.55,
                    text_thickness=1,
                    y_offset=0,
                )
                continue

            emb = getattr(face, 'normed_embedding', None)
            if emb is None:
                emb = getattr(face, 'embedding', None)
            emb = self._norm(emb)
            if emb is None:
                invalid_bboxes.append(current_bbox)
                stats['rejected_faces'] += 1
                continue

            identity_type, identity_value, identity_score = self._resolve_identity(
                emb,
                current_bbox,
                now_local,
                camera_db_id,
                visitor_threshold=similarity_threshold,
                staff_threshold=staff_similarity_threshold,
            )

            if identity_type == 'staff':
                matched_staff = identity_value
                staff_score = identity_score
                self._clear_pending_for_bbox(current_bbox, camera_db_id=camera_db_id)
                stats['staff_matches'] += 1
                staff_role = (matched_staff.position or matched_staff.department or 'Staff').strip()
                label = f"{matched_staff.staff_id} [{staff_role}]"
                color = (255, 170, 0)
                self._draw_papp_style_box(frame, current_bbox, label, color, thickness=1, font_scale=0.55, text_thickness=1, y_offset=-10)
                continue

            matched_db_id = identity_value if identity_type == 'visitor' else None
            matched_score = identity_score
            label = "Unknown"
            color = (0, 255, 255)

            if matched_db_id is None:
                candidate = self._upsert_pending_candidate(current_bbox, emb, now_local, camera_db_id=camera_db_id)
                min_frames = max(1, int(cfg.get('UNKNOWN_FACE_MIN_FRAMES', 3)))
                if is_browser_camera:
                    min_frames = max(2, min_frames)
                if int(candidate.get('count', 0)) < min_frames:
                    color = (0, 200, 255)
                    self._draw_papp_style_box(frame, current_bbox, "Analyzing...", color, thickness=1, font_scale=0.55, text_thickness=1, y_offset=-10)
                    continue

                self._clear_specific_candidate(candidate)
                stable_embedding = candidate.get('embedding') if candidate.get('embedding') is not None else emb

                # One more identity check with the stabilized embedding before creating a new visitor.
                rescue_db_id, rescue_score = self._match_event_visitor(
                    stable_embedding,
                    max(0.35, similarity_threshold - 0.06),
                    camera_db_id=camera_db_id,
                )
                if rescue_db_id is None:
                    rescue_db_id, rescue_score = self._match_recent_active_track(
                        stable_embedding,
                        current_bbox,
                        now_local,
                        camera_db_id,
                        base_threshold=max(0.35, similarity_threshold - 0.06),
                    )

                if rescue_db_id is not None:
                    visitor = Visitor.query.get(rescue_db_id)
                    if visitor is not None:
                        self._clear_pending_for_bbox(current_bbox, camera_db_id=camera_db_id)
                        existing_track = self._active_tracks.get(visitor.id)
                        self._ensure_active_session(visitor, camera_db_id, now_local, event_start=event_start)
                        track = self._active_tracks.get(visitor.id)
                        if track is not None:
                            track['bbox'] = current_bbox
                            track['last_seen'] = now_local
                            track['embedding'] = stable_embedding
                        visitor.last_seen = now_local

                        if existing_track is None:
                            session_rel_path = self._save_primary_face_image(frame, current_bbox, visitor.visitor_id)
                            if session_rel_path:
                                visitor.primary_image_path = session_rel_path
                                db.session.add(VisitorImage(visitor_id=visitor.id, image_path=session_rel_path))
                                changed = True
                                force_commit = True

                        if rescue_score < 0.995:
                            updated = self._append_embedding_sample(visitor.id, stable_embedding, limit=5)
                            if updated is not None:
                                visitor.embedding = updated.astype(np.float32).tobytes()
                                changed = True
                        self._append_event_embedding_sample(visitor.id, stable_embedding, limit=5)
                        self._touch_recent_event_match(visitor.id)

                        event_display_id = self._get_or_assign_event_display_id(visitor.id)
                        label = f"{event_display_id} ({max(0.0, rescue_score):.2f})"
                        color = (0, 255, 0)
                        valid_db_ids.add(visitor.id)
                        stats['known_visitors'] += 1
                        self._draw_papp_style_box(frame, current_bbox, label, color, thickness=1, font_scale=0.55, text_thickness=1, y_offset=-10)
                        continue

                max_identities = int(cfg.get('MAX_VISITOR_IDENTITIES', 99999) or 99999)
                if max_identities > 0 and len(self._embeddings) >= max_identities:
                    label = f"Visitor cap reached ({max_identities})"
                    color = (0, 140, 255)
                    self._draw_papp_style_box(frame, current_bbox, label, color, thickness=1, font_scale=0.55, text_thickness=1, y_offset=-10)
                    continue

                visitor_code = self._get_next_visitor_id()
                image_rel_path = self._save_primary_face_image(frame, current_bbox, visitor_code)
                visitor = Visitor(
                    visitor_id=visitor_code,
                    primary_image_path=image_rel_path,
                    embedding=stable_embedding.astype(np.float32).tobytes(),
                    first_seen=max(now_local, event_start) if event_start else now_local,
                    last_seen=max(now_local, event_start) if event_start else now_local,
                    visit_count=1,
                )
                db.session.add(visitor)
                db.session.flush()

                if image_rel_path:
                    db.session.add(VisitorImage(visitor_id=visitor.id, image_path=image_rel_path))
                session = VisitorSession(
                    visitor_id=visitor.id,
                    camera_id=camera_db_id,
                    entry_time=max(now_local, event_start) if event_start else now_local,
                    is_active=True,
                )
                db.session.add(session)
                db.session.flush()

                self._embeddings[visitor.id] = stable_embedding
                self._embedding_history[visitor.id] = [stable_embedding]
                self._event_visitor_ids.add(visitor.id)
                self._event_embedding_history[visitor.id] = [stable_embedding]
                self._visitor_codes[visitor.id] = visitor_code
                self._touch_recent_event_match(visitor.id)
                self._active_tracks[visitor.id] = {
                    'last_seen': now_local,
                    'bbox': current_bbox,
                    'session_id': session.id,
                    'camera_id': camera_db_id,
                    'embedding': stable_embedding,
                }
                valid_db_ids.add(visitor.id)
                stats['new_visitors'] += 1
                event_display_id = self._get_or_assign_event_display_id(visitor.id)
                label = f"{event_display_id} (New)"
                color = (0, 255, 255)
                changed = True
                force_commit = True
            else:
                visitor = Visitor.query.get(matched_db_id)
                if visitor is None:
                    continue
                self._clear_pending_for_bbox(current_bbox, camera_db_id=camera_db_id)

                existing_track = self._active_tracks.get(visitor.id)
                self._ensure_active_session(visitor, camera_db_id, now_local, event_start=event_start)
                track = self._active_tracks.get(visitor.id)
                if track is not None:
                    track['bbox'] = current_bbox
                    track['last_seen'] = now_local
                    track['embedding'] = emb
                visitor.last_seen = now_local

                # Refresh snapshot when visitor re-enters a session so PDF gets a current face-to-shoulder source.
                if existing_track is None:
                    session_rel_path = self._save_primary_face_image(frame, current_bbox, visitor.visitor_id)
                    if session_rel_path:
                        visitor.primary_image_path = session_rel_path
                        db.session.add(VisitorImage(visitor_id=visitor.id, image_path=session_rel_path))
                        changed = True
                        force_commit = True

                # Ensure reports always have a usable source image for face-to-shoulder crop.
                if not self._visitor_has_usable_image(visitor):
                    fallback_rel_path = self._save_primary_face_image(frame, current_bbox, visitor.visitor_id)
                    if fallback_rel_path:
                        visitor.primary_image_path = fallback_rel_path
                        db.session.add(VisitorImage(visitor_id=visitor.id, image_path=fallback_rel_path))
                        changed = True
                        force_commit = True

                if matched_score < 0.995:
                    updated = self._append_embedding_sample(visitor.id, emb, limit=5)
                    if updated is not None:
                        visitor.embedding = updated.astype(np.float32).tobytes()
                        changed = True
                self._append_event_embedding_sample(visitor.id, emb, limit=5)
                self._touch_recent_event_match(visitor.id)
                event_display_id = self._get_or_assign_event_display_id(visitor.id)
                label = f"{event_display_id} ({max(0.0, matched_score):.2f})"
                color = (0, 255, 0)
                valid_db_ids.add(visitor.id)
                stats['known_visitors'] += 1

            self._draw_papp_style_box(frame, current_bbox, label, color, thickness=1, font_scale=0.55, text_thickness=1, y_offset=-10)

        if self._finalize_absent_sessions(
            valid_db_ids,
            invalid_bboxes,
            now_local,
            event_start=event_start,
            event_end=event_end,
            camera_db_id=camera_db_id,
        ):
            changed = True
            force_commit = True

        if not faces:
            fallback_count = self._draw_fallback_face_boxes(frame)
            stats['faces_detected'] = max(int(stats.get('faces_detected', 0)), int(fallback_count))

        self._purge_pending_candidates(now_local)

        self._commit_if_needed(changed=changed, force=force_commit)

        if return_stats:
            return frame, stats
        return frame

    def compare_faces(self, embedding1, embedding2, threshold=0.5):
        emb1 = self._norm(embedding1)
        emb2 = self._norm(embedding2)
        if emb1 is None or emb2 is None:
            return False
        return float(np.dot(emb1, emb2)) >= float(threshold)

    def find_matching_staff(self, target_embedding, db_session, threshold=None, with_score=False):
        from models.staff import Staff

        emb = self._norm(target_embedding)
        if emb is None:
            return (None, -1.0) if with_score else None

        if threshold is None:
            threshold = float(current_app.config.get('STAFF_SIMILARITY_THRESHOLD', 0.65))

        self._sync_staff_cache()
        best_staff_id = None
        best_score = -1.0
        for staff_db_id, stored in self._staff_embeddings:
            score = float(np.dot(emb, stored))
            if score > best_score:
                best_score = score
                best_staff_id = staff_db_id

        if best_staff_id is not None and best_score >= threshold:
            matched_staff = Staff.query.get(best_staff_id)
            if with_score:
                return matched_staff, best_score
            return matched_staff

        if with_score:
            return None, best_score
        return None
