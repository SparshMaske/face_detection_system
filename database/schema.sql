-- Turn off echo to avoid cluttering logs during creation
SET client_encoding = 'UTF8';

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'viewer', -- admin, viewer
    full_name VARCHAR(120),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP WITHOUT TIME ZONE
);

-- 2. Activity Logs
CREATE TABLE IF NOT EXISTS activity_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100),
    details TEXT,
    ip_address VARCHAR(50),
    timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Staff Table
CREATE TABLE IF NOT EXISTS staff (
    id SERIAL PRIMARY KEY,
    staff_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    department VARCHAR(100),
    position VARCHAR(100),
    email VARCHAR(120),
    phone VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Staff Images
CREATE TABLE IF NOT EXISTS staff_images (
    id SERIAL PRIMARY KEY,
    staff_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
    image_path VARCHAR(255) NOT NULL,
    embedding BYTEA, -- Stores numpy array bytes
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Visitors Table
CREATE TABLE IF NOT EXISTS visitors (
    id SERIAL PRIMARY KEY,
    visitor_id VARCHAR(50) UNIQUE NOT NULL,
    primary_image_path VARCHAR(255),
    embedding BYTEA, -- Average embedding for re-identification
    first_seen TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    visit_count INTEGER DEFAULT 1
);

-- 6. Visitor Sessions
CREATE TABLE IF NOT EXISTS visitor_sessions (
    id SERIAL PRIMARY KEY,
    visitor_id INTEGER NOT NULL REFERENCES visitors(id) ON DELETE CASCADE,
    camera_id INTEGER REFERENCES cameras(id) ON DELETE SET NULL,
    entry_time TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    exit_time TIMESTAMP WITHOUT TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE
);

-- 7. Visitor Images (Multiple captures per visit)
CREATE TABLE IF NOT EXISTS visitor_images (
    id SERIAL PRIMARY KEY,
    visitor_id INTEGER NOT NULL REFERENCES visitors(id) ON DELETE CASCADE,
    image_path VARCHAR(255) NOT NULL,
    captured_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 8. Cameras Table
CREATE TABLE IF NOT EXISTS cameras (
    id SERIAL PRIMARY KEY,
    camera_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    location VARCHAR(200),
    stream_url VARCHAR(255),
    camera_type VARCHAR(20), -- webcam, rtsp
    is_active BOOLEAN DEFAULT TRUE,
    is_online BOOLEAN DEFAULT FALSE,
    fps_limit INTEGER DEFAULT 30,
    resolution_width INTEGER DEFAULT 1920,
    resolution_height INTEGER DEFAULT 1080
);

-- 9. System Settings
CREATE TABLE IF NOT EXISTS system_settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT,
    value_type VARCHAR(20), -- string, int, float, bool
    description VARCHAR(255)
);

-- Performance Indexes
CREATE INDEX idx_visitors_first_seen ON visitors(first_seen);
CREATE INDEX idx_visitor_sessions_entry ON visitor_sessions(entry_time);
CREATE INDEX idx_visitor_sessions_active ON visitor_sessions(is_active) WHERE is_active = true;
CREATE INDEX idx_staff_images_staff ON staff_images(staff_id);