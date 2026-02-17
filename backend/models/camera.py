from models import db

# Matches SQL Table: cameras
class Camera(db.Model):
    __tablename__ = 'cameras'
    
    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(200))
    stream_url = db.Column(db.String(255)) 
    camera_type = db.Column(db.String(20)) 
    is_active = db.Column(db.Boolean, default=True)
    is_online = db.Column(db.Boolean, default=False)
    fps_limit = db.Column(db.Integer, default=30)
    # SQL columns are separate integers
    resolution_width = db.Column(db.Integer, default=1920)
    resolution_height = db.Column(db.Integer, default=1080)

    def to_dict(self):
        return {
            'id': self.id,
            'camera_id': self.camera_id,
            'name': self.name,
            'location': self.location,
            'stream_url': self.stream_url,
            'camera_type': self.camera_type,
            'is_active': self.is_active,
            'is_online': self.is_online,
            'fps_limit': self.fps_limit,
            'resolution': {
                'width': self.resolution_width,
                'height': self.resolution_height
            }
        }

# Matches SQL Table: system_settings
class SystemSettings(db.Model):
    __tablename__ = 'system_settings'
    
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text)
    value_type = db.Column(db.String(20)) 
    description = db.Column(db.String(255))

    def to_dict(self):
        return {
            'key': self.key,
            'value': self.value,
            'value_type': self.value_type,
            'description': self.description
        }