from datetime import datetime
from models import db

# Matches SQL Table: staff
class Staff(db.Model):
    __tablename__ = 'staff'
    
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.String(50), unique=True, nullable=False) 
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100))
    position = db.Column(db.String(100))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to staff_images
    images = db.relationship('StaffImage', backref='staff', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'staff_id': self.staff_id,
            'name': self.name,
            'department': self.department,
            'position': self.position,
            'email': self.email,
            'phone': self.phone,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'images': [img.to_dict() for img in self.images]
        }

# Matches SQL Table: staff_images
class StaffImage(db.Model):
    __tablename__ = 'staff_images'
    
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id', ondelete='CASCADE'), nullable=False)
    image_path = db.Column(db.String(255), nullable=False)
    # Maps SQL BYTEA to LargeBinary
    embedding = db.Column(db.LargeBinary) 
    is_primary = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'image_path': self.image_path,
            'is_primary': self.is_primary
        }