import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Base Security
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key')
    
    # Database Integration
    # Matches the 'db' service in docker-compose or local postgres
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL', 
        'postgresql://visitor_user:visitor_pass@localhost:5432/visitor_monitoring'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # JWT Settings
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    
    # File Paths
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    STAFF_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, 'staff')
    VISITOR_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, 'visitors')
    REPORTS_FOLDER = os.path.join(BASE_DIR, 'reports')
    
    # Face Recognition Thresholds (Used in Services)
    FACE_CONFIDENCE_THRESHOLD = float(os.getenv('FACE_CONFIDENCE_THRESHOLD', 0.5))
    FACE_SIMILARITY_THRESHOLD = float(os.getenv('FACE_SIMILARITY_THRESHOLD', 0.5))
    STAFF_SIMILARITY_THRESHOLD = float(os.getenv('STAFF_SIMILARITY_THRESHOLD', 0.65))
    MIN_FACE_AREA = int(os.getenv('MIN_FACE_AREA', 11000))
    BLUR_THRESHOLD = float(os.getenv('BLUR_THRESHOLD', 50.0))
    TILT_THRESHOLD = float(os.getenv('TILT_THRESHOLD', 0.25))
    UNKNOWN_FACE_MIN_FRAMES = int(os.getenv('UNKNOWN_FACE_MIN_FRAMES', 3))
    SESSION_GRACE_PERIOD = float(os.getenv('SESSION_GRACE_PERIOD', 2.0))
    
    # CORS
    CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
