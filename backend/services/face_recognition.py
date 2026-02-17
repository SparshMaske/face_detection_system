import datetime
import os
import re
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from flask import current_app
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
        self.app = FaceAnalysis(
            name='buffalo_l',
            providers=['CPUExecutionProvider'],
            allowed_modules=['detection', 'recognition'],
        )
        self.app.prepare(ctx_id=0, det_size=(640, 640))
        print("InsightFace model loaded.")

        self._embeddings: Dict[int, np.ndarray] = {}
        self._visitor_codes: Dict[int, str] = {}
        self._staff_embeddings: List[Tuple[int, np.ndarray]] = []
        self._active_tracks: Dict[int, Dict] = {}
        self._pending_candidates: List[Dict] = []
        self._next_visitor_num: Optional[int] = None
        self._last_cache_sync = datetime.datetime.min
        self._last_staff_cache_sync = datetime.datetime.min

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
        dy = float(right_eye[1] - left_eye[1])
        eye_distance = abs(dx)
        if eye_distance == 0:
            return False, 0.0, 0.0
        eyes_mid_x = (float(left_eye[0]) + float(right_eye[0])) / 2.0
        yaw_ratio = abs(float(nose[0]) - eyes_mid_x) / eye_distance
        roll_angle_deg = abs(float(np.degrees(np.arctan2(dy, dx))))
        return True, yaw_ratio, roll_angle_deg

    def _sync_embedding_cache(self, force=False):
        now = datetime.datetime.now()
        if not force and (now - self._last_cache_sync).total_seconds() < 15:
            return

        visitors = Visitor.query.filter(Visitor.embedding.isnot(None)).all()
        cache_embeddings = {}
        cache_codes = {}
        for visitor in visitors:
            emb = np.frombuffer(visitor.embedding, dtype=np.float32)
            normed = self._norm(emb)
            if normed is not None:
                cache_embeddings[visitor.id] = normed
                cache_codes[visitor.id] = visitor.visitor_id
        self._embeddings = cache_embeddings
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
        if self._next_visitor_num is None:
            max_num = 0
            for value in db.session.query(Visitor.visitor_id).all():
                visitor_id = value[0] or ''
                match = re.match(r'^ID(\d+)$', visitor_id)
                if match:
                    max_num = max(max_num, int(match.group(1)))
            self._next_visitor_num = max_num + 1

        visitor_code = f"ID{self._next_visitor_num}"
        self._next_visitor_num += 1
        return visitor_code

    def _upsert_pending_candidate(self, bbox, embedding, now_local):
        best_idx = None
        best_iou = 0.0
        for idx, cand in enumerate(self._pending_candidates):
            iou = self._iou(cand.get('bbox'), bbox)
            if iou > 0.45 and iou > best_iou:
                best_iou = iou
                best_idx = idx

        if best_idx is None:
            candidate = {
                'bbox': bbox,
                'embedding': embedding,
                'count': 1,
                'first_seen': now_local,
                'last_seen': now_local,
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

    def _clear_pending_for_bbox(self, bbox):
        self._pending_candidates = [
            cand for cand in self._pending_candidates
            if self._iou(cand.get('bbox'), bbox) <= 0.30
        ]

    def _clear_specific_candidate(self, candidate):
        self._pending_candidates = [cand for cand in self._pending_candidates if cand is not candidate]

    def _purge_pending_candidates(self, now_local):
        self._pending_candidates = [
            cand for cand in self._pending_candidates
            if (now_local - cand.get('last_seen', now_local)).total_seconds() <= 2.5
        ]

    def _save_primary_face_image(self, frame, bbox, visitor_code) -> str:
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
        filename = f"{visitor_code}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        rel_path = os.path.join('visitors', filename)
        abs_path = os.path.join(current_app.config['UPLOAD_FOLDER'], rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        cv2.imwrite(abs_path, crop)
        return rel_path

    def _match_visitor(self, embedding: np.ndarray, threshold: float):
        best_db_id = None
        best_score = -1.0
        for db_id, known_embedding in self._embeddings.items():
            score = float(np.dot(embedding, known_embedding))
            if score > best_score:
                best_score = score
                best_db_id = db_id
        if best_db_id is not None and best_score >= threshold:
            return best_db_id, best_score
        return None, best_score

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
        }
        return active_session.id

    def _generate_visitor_pdf(
        self,
        visitor_db_id: int,
        event_start: Optional[datetime.datetime] = None,
        event_end: Optional[datetime.datetime] = None,
    ):
        try:
            from services.report_generator import ReportGenerator
            visitor = Visitor.query.get(visitor_db_id)
            if visitor:
                ReportGenerator().generate_visitor_pdf(
                    visitor,
                    event_start=event_start,
                    event_end=event_end,
                )
        except Exception as exc:
            current_app.logger.warning("Visitor PDF generation failed for visitor_id=%s: %s", visitor_db_id, exc)

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

    def process_frame_for_stream(self, frame, camera=None, event_context=None):
        now_local = datetime.datetime.now()
        self._sync_embedding_cache()
        self._sync_staff_cache()

        cfg = current_app.config
        conf_threshold = float(cfg.get('FACE_CONFIDENCE_THRESHOLD', 0.5))
        similarity_threshold = float(cfg.get('FACE_SIMILARITY_THRESHOLD', 0.5))
        staff_similarity_threshold = float(cfg.get('STAFF_SIMILARITY_THRESHOLD', 0.65))
        blur_threshold = float(cfg.get('BLUR_THRESHOLD', 50.0))
        tilt_threshold = float(cfg.get('TILT_THRESHOLD', 0.25))
        min_face_area = int(cfg.get('MIN_FACE_AREA', 11000))

        camera_db_id = getattr(camera, 'id', None)
        event_start = event_context.get('start_time') if event_context else None
        event_end = event_context.get('end_time') if event_context else None
        faces = self.app.get(frame)
        valid_db_ids = set()
        invalid_bboxes = []
        changed = False

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
                cv2.rectangle(frame, (x1, y1), (x2, y2), (80, 80, 255), 1)
                cv2.putText(frame, "Low Conf", (x1, max(20, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (80, 80, 255), 2)
                continue

            face_area = (x2 - x1) * (y2 - y1)
            if face_area < min_face_area:
                invalid_bboxes.append(current_bbox)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 1)
                cv2.putText(frame, "Too Far", (x1, max(20, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
                continue

            try:
                gray = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
                blur_value = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            except Exception:
                blur_value = 0.0
            if blur_value < blur_threshold:
                invalid_bboxes.append(current_bbox)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (30, 30, 255), 1)
                cv2.putText(frame, "Blurry", (x1, max(20, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (30, 30, 255), 2)
                continue

            has_pose, yaw_ratio, roll_angle_deg = self._tilt_metrics(face)
            max_roll = max(5.0, tilt_threshold * 45.0)
            if has_pose and (yaw_ratio > tilt_threshold or roll_angle_deg > max_roll):
                invalid_bboxes.append(current_bbox)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 60, 255), 2)
                cv2.putText(frame, "Tilted", (x1, max(20, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 60, 255), 2)
                continue

            emb = getattr(face, 'normed_embedding', None)
            if emb is None:
                emb = getattr(face, 'embedding', None)
            emb = self._norm(emb)
            if emb is None:
                invalid_bboxes.append(current_bbox)
                continue

            matched_staff, staff_score = self.find_matching_staff(
                emb,
                db.session,
                threshold=staff_similarity_threshold,
                with_score=True,
            )
            if matched_staff is not None:
                self._clear_pending_for_bbox(current_bbox)
                staff_role = (matched_staff.position or matched_staff.department or 'Staff').strip()
                label = f"{matched_staff.staff_id} | {matched_staff.name} [{staff_role}] ({staff_score:.2f})"
                color = (255, 170, 0)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(
                    frame,
                    label,
                    (x1, max(20, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.56,
                    color,
                    2,
                )
                continue

            matched_db_id, matched_score = self._match_visitor(emb, similarity_threshold)
            label = "Unknown"
            color = (0, 255, 255)

            if matched_db_id is None:
                candidate = self._upsert_pending_candidate(current_bbox, emb, now_local)
                min_frames = max(1, int(cfg.get('UNKNOWN_FACE_MIN_FRAMES', 3)))
                if int(candidate.get('count', 0)) < min_frames:
                    color = (0, 200, 255)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(
                        frame,
                        "Analyzing...",
                        (x1, max(20, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.56,
                        color,
                        2,
                    )
                    continue

                self._clear_specific_candidate(candidate)
                stable_embedding = candidate.get('embedding') if candidate.get('embedding') is not None else emb
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
                self._visitor_codes[visitor.id] = visitor_code
                self._active_tracks[visitor.id] = {
                    'last_seen': now_local,
                    'bbox': current_bbox,
                    'session_id': session.id,
                    'camera_id': camera_db_id,
                }
                valid_db_ids.add(visitor.id)
                label = f"{visitor_code} (New)"
                color = (0, 255, 255)
                changed = True
            else:
                visitor = Visitor.query.get(matched_db_id)
                if visitor is None:
                    continue
                self._clear_pending_for_bbox(current_bbox)

                self._ensure_active_session(visitor, camera_db_id, now_local, event_start=event_start)
                track = self._active_tracks.get(visitor.id)
                if track is not None:
                    track['bbox'] = current_bbox
                    track['last_seen'] = now_local
                visitor.last_seen = now_local

                if matched_score < 0.98:
                    updated = self._norm((self._embeddings[visitor.id] * 0.85) + (emb * 0.15))
                    if updated is not None:
                        self._embeddings[visitor.id] = updated
                        visitor.embedding = updated.astype(np.float32).tobytes()
                label = f"{visitor.visitor_id} ({matched_score:.2f})"
                color = (0, 255, 0)
                valid_db_ids.add(visitor.id)
                changed = True

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                frame,
                label,
                (x1, max(20, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.60,
                color,
                2,
            )

        if self._finalize_absent_sessions(
            valid_db_ids,
            invalid_bboxes,
            now_local,
            event_start=event_start,
            event_end=event_end,
            camera_db_id=camera_db_id,
        ):
            changed = True

        self._purge_pending_candidates(now_local)

        if changed:
            try:
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                current_app.logger.warning("Failed to persist recognition update: %s", exc)

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
