import os
import uuid
import datetime
import numpy as np
import cv2
from flask import current_app
from models import db
from models.visitor import Visitor, VisitorSession, VisitorImage
from services.face_recognition import FaceRecognitionService

class VisitorManager:
    def __init__(self):
        self.fr_service = FaceRecognitionService()

    def process_detected_face(self, frame, camera_id, bbox):
        """Called when a face is detected."""
        x1, y1, x2, y2 = map(int, bbox)
        face_img = frame[y1:y2, x1:x2]
        
        embedding = self.fr_service.get_embedding(face_img)
        if embedding is None:
            return None 

        # 1. Check Staff
        matched_staff = self.fr_service.find_matching_staff(embedding, db.session)
        if matched_staff:
            return {'status': 'staff', 'data': matched_staff}

        # 2. Check Known Visitor
        known_visitor = Visitor.query.filter(Visitor.embedding.isnot(None)).all()
        best_match = None
        best_score = -1
        
        for v in known_visitor:
            v_emb = np.frombuffer(v.embedding, dtype=np.float32)
            score = np.dot(embedding, v_emb)
            if score > current_app.config['FACE_SIMILARITY_THRESHOLD'] and score > best_score:
                best_match = v
                best_score = score
        
        visitor = best_match

        if not visitor:
            # 3. New Visitor
            filename = f"V_{uuid.uuid4().hex}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
            rel_path = f"visitors/{filename}"
            full_path = os.path.join(current_app.config['VISITOR_UPLOAD_FOLDER'], filename)
            
            os.makedirs(current_app.config['VISITOR_UPLOAD_FOLDER'], exist_ok=True)
            cv2.imwrite(full_path, face_img)

            last_visitor = Visitor.query.order_by(Visitor.id.desc()).first()
            next_id_num = (int(last_visitor.visitor_id[1:]) + 1) if last_visitor else 1
            visitor_id_str = f"V{str(next_id_num).zfill(6)}"

            visitor = Visitor(
                visitor_id=visitor_id_str,
                primary_image_path=rel_path,
                embedding=embedding.tobytes()
            )
            db.session.add(visitor)
            db.session.flush() 
            
            v_img = VisitorImage(visitor_id=visitor.id, image_path=rel_path)
            db.session.add(v_img)
            
            session = VisitorSession(visitor_id=visitor.id, camera_id=camera_id, is_active=True)
            db.session.add(session)
            
            db.session.commit()
            
            from app import socketio
            socketio.emit('visitor_detected', {
                'event': 'visitor_detected',
                'data': {
                    'visitor_id': visitor.visitor_id,
                    'timestamp': datetime.datetime.utcnow().isoformat(),
                    'camera_id': camera_id,
                    'is_new': True
                }
            })
            
            return {'status': 'new_visitor', 'data': visitor}

        else:
            # Known Visitor - Session Logic
            active_session = VisitorSession.query.filter_by(
                visitor_id=visitor.id, 
                is_active=True
            ).first()
            
            if not active_session:
                active_session = VisitorSession(
                    visitor_id=visitor.id, 
                    camera_id=camera_id, 
                    is_active=True
                )
                db.session.add(active_session)
                
                from app import socketio
                socketio.emit('visitor_detected', {
                    'event': 'visitor_detected',
                    'data': {
                        'visitor_id': visitor.visitor_id,
                        'timestamp': datetime.datetime.utcnow().isoformat(),
                        'camera_id': camera_id,
                        'is_new': False
                    }
                })
            else:
                pass
                
            visitor.last_seen = datetime.datetime.utcnow()
            visitor.visit_count += 1
            db.session.commit()
            
            return {'status': 'returning_visitor', 'data': visitor}
