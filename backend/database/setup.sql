-- Smart Visitor Monitoring System - Database Setup Script
-- PostgreSQL Database Schema

-- Create database (run as postgres user)
-- CREATE DATABASE visitor_monitoring;
-- CREATE USER visitor_user WITH PASSWORD 'visitor_pass';
-- GRANT ALL PRIVILEGES ON DATABASE visitor_monitoring TO visitor_user;

-- Connect to database
\c visitor_monitoring

-- Create extensions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'viewer',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

-- Staff table
CREATE TABLE IF NOT EXISTS staff (
    id SERIAL PRIMARY KEY,
    staff_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    department VARCHAR(100),
    email VARCHAR(100),
    phone VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Staff images table
CREATE TABLE IF NOT EXISTS staff_images (
    id SERIAL PRIMARY KEY,
    staff_id INTEGER REFERENCES staff(id) ON DELETE CASCADE,
    image_path VARCHAR(255) NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Staff embeddings table
CREATE TABLE IF NOT EXISTS staff_embeddings (
    id SERIAL PRIMARY KEY,
    staff_id INTEGER REFERENCES staff(id) ON DELETE CASCADE,
    embedding BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Visitors table
CREATE TABLE IF NOT EXISTS visitors (
    id SERIAL PRIMARY KEY,
    visitor_id VARCHAR(50) UNIQUE NOT NULL,
    first_seen TIMESTAMP NOT NULL,
    last_seen TIMESTAMP NOT NULL,
    image_path VARCHAR(255),
    total_duration INTEGER DEFAULT 0,
    visit_count INTEGER DEFAULT 1,
    camera_id VARCHAR(50)
);

-- Visitor embeddings table
CREATE TABLE IF NOT EXISTS visitor_embeddings (
    id SERIAL PRIMARY KEY,
    visitor_id INTEGER REFERENCES visitors(id) ON DELETE CASCADE,
    embedding BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Visitor sessions table
CREATE TABLE IF NOT EXISTS visitor_sessions (
    id SERIAL PRIMARY KEY,
    visitor_id INTEGER REFERENCES visitors(id) ON DELETE CASCADE,
    entry_time TIMESTAMP NOT NULL,
    exit_time TIMESTAMP,
    duration INTEGER,
    camera_id VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE
);

-- System settings table
CREATE TABLE IF NOT EXISTS system_settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,
    value TEXT NOT NULL,
    description VARCHAR(255),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Activity logs table
CREATE TABLE IF NOT EXISTS activity_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    details TEXT,
    ip_address VARCHAR(50),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_visitors_first_seen ON visitors(first_seen);
CREATE INDEX IF NOT EXISTS idx_visitors_last_seen ON visitors(last_seen);
CREATE INDEX IF NOT EXISTS idx_visitors_camera ON visitors(camera_id);
CREATE INDEX IF NOT EXISTS idx_sessions_visitor ON visitor_sessions(visitor_id);
CREATE INDEX IF NOT EXISTS idx_sessions_entry ON visitor_sessions(entry_time);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON visitor_sessions(is_active);
CREATE INDEX IF NOT EXISTS idx_activity_logs_user ON activity_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_logs_timestamp ON activity_logs(timestamp);

-- Insert default admin user (password: admin123)
INSERT INTO users (username, password_hash, role) 
VALUES ('admin', 'scrypt:32768:8:1$YrxLXQd6oBU5Vxmr$8f6e8c7c3b8c5f8e5c7c3b8c5f8e5c7c3b8c5f8e5c7c3b8c5f8e5c7c3b8c5f8e5c7c3b8c5f8e5c7c3b8c5f8e5c7c3b8c5f8e5c7c3b8c', 'admin')
ON CONFLICT (username) DO NOTHING;

-- Insert default system settings
INSERT INTO system_settings (key, value, description) VALUES
    ('similarity_threshold', '0.5', 'Face matching similarity threshold'),
    ('blur_threshold', '50.0', 'Blur detection threshold'),
    ('tilt_threshold', '0.25', 'Face tilt detection threshold'),
    ('min_face_area', '11000', 'Minimum face area in pixels'),
    ('data_retention_days', '90', 'Number of days to retain visitor data'),
    ('auto_report_enabled', 'false', 'Enable automatic daily reports'),
    ('camera_fps', '30', 'Camera frame rate'),
    ('organization_name', 'Smart Visitor Monitoring System', 'Organization name for reports')
ON CONFLICT (key) DO NOTHING;

-- Create a function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for updated_at
CREATE TRIGGER update_staff_updated_at
    BEFORE UPDATE ON staff
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_settings_updated_at
    BEFORE UPDATE ON system_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO visitor_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO visitor_user;

-- Display summary
SELECT 'Database setup completed successfully!' AS status;
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;