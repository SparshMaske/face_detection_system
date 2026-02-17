import os
from datetime import timedelta
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import exc as sa_exc


# Import Configuration
from config import Config
from models import db

# Initialize Extensions (Global scope)
migrate = None
jwt = None
socketio = None
limiter = None

KNOWN_BAD_ADMIN_HASH = (
    "scrypt:32768:8:1$gJtLp8lZ1JqWvJqZ$"
    "WvJqZvJqZvJqZvJqZvJqZvJqZvJqZvJqZvJqZvJqZvJqZvJqZvJqZvJqZvJq"
)


def ensure_default_admin(app):
    """
    Create default admin if missing and repair the known bad seed hash.
    """
    username = os.getenv('DEFAULT_ADMIN_USERNAME', 'admin')
    password = os.getenv('DEFAULT_ADMIN_PASSWORD', 'admin123')
    email = os.getenv('DEFAULT_ADMIN_EMAIL', 'admin@example.com')
    full_name = os.getenv('DEFAULT_ADMIN_FULL_NAME', 'System Administrator')

    try:
        from models.user import User

        with app.app_context():
            admin = User.query.filter_by(username=username).first()

            if not admin:
                admin = User(username=username, email=email, role='admin', full_name=full_name)
                admin.set_password(password)
                db.session.add(admin)
                db.session.commit()
                app.logger.info("Default admin created: %s", username)
                return

            if admin.password_hash == KNOWN_BAD_ADMIN_HASH:
                admin.set_password(password)
                if not admin.role:
                    admin.role = 'admin'
                if not admin.full_name:
                    admin.full_name = full_name
                db.session.commit()
                app.logger.info("Default admin password repaired for: %s", username)
    except Exception as exc:
        try:
            with app.app_context():
                db.session.rollback()
        except Exception:
            pass
        app.logger.warning("Skipped default admin bootstrap: %s", exc)

def create_app(config_class=Config):
    """
    Application Factory Pattern.
    Initializes Database, Blueprints, and Error Handlers.
    """
    global migrate, jwt, socketio, limiter

    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure required folders exist
    for folder in (
        app.config.get('UPLOAD_FOLDER'),
        app.config.get('STAFF_UPLOAD_FOLDER'),
        app.config.get('VISITOR_UPLOAD_FOLDER'),
        app.config.get('REPORTS_FOLDER'),
    ):
        if folder:
            os.makedirs(folder, exist_ok=True)

    # Initialize Database (single shared instance from models)
    db.init_app(app)
    
    # Initialize Migrations (Handles database schema versioning)
    migrate = Migrate(app, db)
    
    # Initialize JWT
    jwt = JWTManager(app)
    
    # Initialize SocketIO (Real-time communication)
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', logger=False, engineio_logger=False)
    
    # Initialize Rate Limiter
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://"
    )

    # Configure CORS based on SQL defined origins or Env Var
    cors_origins = app.config.get('CORS_ORIGINS', ["http://localhost:3000", "http://127.0.0.1:3000"])
    CORS(app, resources={r"/api/*": {"origins": cors_origins}})
    # --- Register Blueprints ---
    # Ensure routes are imported AFTER db initialization to avoid circular dependencies
    from routes import (
        auth_bp, dashboard_bp, staff_bp, visitors_bp, 
        reports_bp, analytics_bp, settings_bp, camera_bp, events_bp
    )

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
    app.register_blueprint(staff_bp, url_prefix='/api/staff')
    app.register_blueprint(visitors_bp, url_prefix='/api/visitors')
    app.register_blueprint(reports_bp, url_prefix='/api/reports')
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    app.register_blueprint(settings_bp, url_prefix='/api/settings')
    app.register_blueprint(camera_bp, url_prefix='/api/camera')
    app.register_blueprint(events_bp, url_prefix='/api/events')
    ensure_default_admin(app)

    # --- JWT Configuration ---
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
    app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=30)

    # --- Global Error Handlers (API Standard) ---
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({"error": "Invalid input parameters"}), 400

    @app.errorhandler(401)
    def unauthorized(error):
        return jsonify({"error": "Missing or invalid authentication token"}), 401

    @app.errorhandler(403)
    def forbidden(error):
        return jsonify({"error": "Insufficient permissions"}), 403

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Resource not found"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return jsonify({"error": "Internal server error message"}), 500
    
    @app.errorhandler(sa_exc.SQLAlchemyError)
    def handle_database_error(error):
        db.session.rollback()
        return jsonify({"error": "Database operation failed"}), 500

    # --- Shell Context ---
    # Allows us to use `flask shell` and access models directly
    @app.shell_context_processor
    def make_shell_context():
        from models.user import User
        from models.staff import Staff, StaffImage
        from models.visitor import Visitor, VisitorSession, VisitorImage
        from models.camera import Camera, SystemSettings
        return {
            'db': db, 'User': User, 'Staff': Staff, 
            'Visitor': Visitor, 'Camera': Camera
        }

    return app

app = create_app()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
