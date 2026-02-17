-- Insert Default Admin User
-- Username: admin
-- Password: admin123
INSERT INTO users (username, email, password_hash, role, full_name) VALUES 
('admin', 'admin@example.com', 'scrypt:32768:8:1$7Wfve0Lgm8AtasUe$d2678d80a51bcc547525e58af82068b71415b94ea3a1dd6b785b84a932da598ac8316f1c7a87195604f67f0d004d094a91b7eb91373a00c94455d985f0a18de5', 'admin', 'System Administrator');

-- Insert Default System Settings
INSERT INTO system_settings (key, value, value_type, description) VALUES 
('similarity_threshold', '0.5', 'float', 'Face recognition similarity threshold'),
('face_threshold', '0.5', 'float', 'Legacy alias for similarity threshold'),
('blur_threshold', '50.0', 'float', 'Blur detection threshold'),
('tilt_threshold', '0.25', 'float', 'Nose/eye alignment tilt threshold'),
('min_face_area', '11000', 'int', 'Minimum face area in pixels'),
('data_retention_days', '90', 'int', 'Days to keep logs before auto-delete'),
('organization_name', 'My Organization', 'string', 'Organization name for reports');

-- Insert Sample Camera (Webcam)
INSERT INTO cameras (camera_id, name, location, stream_url, camera_type, is_active) VALUES 
('CAM001', 'Main Entrance', 'Building A - Entrance', '0', 'webcam', TRUE);

-- Insert Sample IP Camera (Placeholder)
INSERT INTO cameras (camera_id, name, location, stream_url, camera_type, is_active) VALUES 
('CAM002', 'Lobby', 'Building A - Lobby', 'rtsp://192.168.1.100:554/stream', 'rtsp', FALSE);
