from datetime import datetime
from models import db

# Matches SQL Table: visitors
class Visitor(db.Model):
    __tablename__ = 'visitors'
    
    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(db.String(50), unique=True, nullable=False) 
    primary_image_path = db.Column(db.String(255))
    embedding = db.Column(db.LargeBinary) 
    first_seen = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    visit_count = db.Column(db.Integer, default=1)
    
    # Relationships
    images = db.relationship('VisitorImage', backref='visitor', lazy=True, cascade="all, delete-orphan")
    sessions = db.relationship('VisitorSession', backref='visitor', lazy=True, order_by='VisitorSession.entry_time.desc()')

    def to_dict(self, include_sessions=False):
        data = {
            'id': self.id,
            'visitor_id': self.visitor_id,
            'primary_image_path': self.primary_image_path,
            'first_seen': self.first_seen.isoformat() if self.first_seen else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'visit_count': self.visit_count
        }
        if include_sessions:
            data['sessions'] = [s.to_dict() for s in self.sessions]
        return data

# Matches SQL Table: visitor_sessions
class VisitorSession(db.Model):
    __tablename__ = 'visitor_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(db.Integer, db.ForeignKey('visitors.id', ondelete='CASCADE'), nullable=False)
    camera_id = db.Column(db.Integer, db.ForeignKey('cameras.id', ondelete='SET NULL'))
    entry_time = db.Column(db.DateTime, default=datetime.utcnow)
    exit_time = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    
    def to_dict(self):
        duration = None
        duration_formatted = "Active"
        
        if self.exit_time:
            diff = self.exit_time - self.entry_time
            duration = diff.total_seconds()
        else:
            diff = datetime.utcnow() - self.entry_time
            duration = diff.total_seconds()

        if duration is not None:
            hours, remainder = divmod(duration, 3600)
            minutes, seconds = divmod(remainder, 60)
            duration_formatted = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
            
        return {
            'id': self.id,
            'visitor_id': self.visitor_id,
            'camera_id': self.camera_id,
            'entry_time': self.entry_time.isoformat() if self.entry_time else None,
            'exit_time': self.exit_time.isoformat() if self.exit_time else None,
            'duration_seconds': int(duration) if duration else 0,
            'duration_formatted': duration_formatted,
            'is_active': self.is_active
        }

# Matches SQL Table: visitor_images
class VisitorImage(db.Model):
    __tablename__ = 'visitor_images'
    
    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(db.Integer, db.ForeignKey('visitors.id', ondelete='CASCADE'), nullable=False)
    image_path = db.Column(db.String(255), nullable=False)
    captured_at = db.Column(db.DateTime, default=datetime.utcnow)