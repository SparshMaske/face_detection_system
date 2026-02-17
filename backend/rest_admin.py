# reset_admin.py
from app import create_app

# 1. Initialize the app FIRST
app = create_app()

# 2. Run the logic INSIDE the app context
with app.app_context():
    # Import db and User HERE so they grab the initialized version
    from models import db
    from models.user import User

    # Check for admin
    admin = User.query.filter_by(username='admin').first()

    if admin:
        print(f"Admin found. Resetting password to 'admin123'...")
        admin.set_password('admin123')
        db.session.commit()
        print("✅ Password reset successfully!")
    else:
        print("Admin not found. Creating new Admin user...")
        new_admin = User(username='admin', email='admin@example.com')
        new_admin.set_password('admin123')
        db.session.add(new_admin)
        db.session.commit()
        print("✅ Admin created with password 'admin123'!")
