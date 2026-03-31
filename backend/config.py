import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


def _split_csv_env(raw_value, fallback):
    text = (raw_value or '').strip()
    if not text:
        return list(fallback)
    return [item.strip() for item in text.split(',') if item.strip()]


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
    FACE_CONFIDENCE_THRESHOLD = float(os.getenv('FACE_CONFIDENCE_THRESHOLD', 0.35))
    FACE_SIMILARITY_THRESHOLD = float(os.getenv('FACE_SIMILARITY_THRESHOLD', 0.5))
    STAFF_SIMILARITY_THRESHOLD = float(os.getenv('STAFF_SIMILARITY_THRESHOLD', 0.65))
    MIN_FACE_AREA = int(os.getenv('MIN_FACE_AREA', 11000))
    BLUR_THRESHOLD = float(os.getenv('BLUR_THRESHOLD', 50.0))
    TILT_THRESHOLD = float(os.getenv('TILT_THRESHOLD', 0.25))
    UNKNOWN_FACE_MIN_FRAMES = int(os.getenv('UNKNOWN_FACE_MIN_FRAMES', 3))
    SESSION_GRACE_PERIOD = float(os.getenv('SESSION_GRACE_PERIOD', 2.0))
    MAX_VISITOR_IDENTITIES = int(os.getenv('MAX_VISITOR_IDENTITIES', 99999))
    # Realtime performance tuning
    FACE_MODEL_NAME = os.getenv('FACE_MODEL_NAME', 'buffalo_s')
    FACE_DET_SIZE = int(os.getenv('FACE_DET_SIZE', 320))
    FACE_MODEL_ROOT = os.getenv('FACE_MODEL_ROOT', os.path.join(BASE_DIR, 'models', 'insightface'))
    FACE_OFFLINE_ONLY = os.getenv('FACE_OFFLINE_ONLY', '1').strip().lower() in ('1', 'true', 'yes', 'on')
    RECOGNITION_INTERVAL_FRAMES = int(os.getenv('RECOGNITION_INTERVAL_FRAMES', 5))
    DB_COMMIT_INTERVAL_MS = int(os.getenv('DB_COMMIT_INTERVAL_MS', 1200))
    MAX_EVENT_MATCH_CANDIDATES = int(os.getenv('MAX_EVENT_MATCH_CANDIDATES', 256))
    ASYNC_VISITOR_PDF = os.getenv('ASYNC_VISITOR_PDF', '1').strip().lower() in ('1', 'true', 'yes', 'on')
    ENFORCE_BACKEND_CAMERA_MODE = os.getenv('ENFORCE_BACKEND_CAMERA_MODE', '0').strip().lower() in ('1', 'true', 'yes', 'on')
    PERF_CAPTURE_WIDTH = int(os.getenv('PERF_CAPTURE_WIDTH', 512))
    PERF_CAPTURE_HEIGHT = int(os.getenv('PERF_CAPTURE_HEIGHT', 384))
    
    # CORS
    CORS_ORIGINS = _split_csv_env(
        os.getenv('CORS_ORIGINS'),
        [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost",
            "http://127.0.0.1",
            "http://192.168.4.1",
            "http://visitorpi.local",
        ],
    )
