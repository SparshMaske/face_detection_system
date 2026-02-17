# Smart Visitor Monitoring System - Complete Deployment Guide

## Table of Contents
1. [System Requirements](#system-requirements)
2. [Quick Start Guide](#quick-start-guide)
3. [Detailed Installation](#detailed-installation)
4. [Configuration](#configuration)
5. [Running the Application](#running-the-application)
6. [Production Deployment](#production-deployment)
7. [Troubleshooting](#troubleshooting)

---

## System Requirements

### Hardware
- **CPU**: Intel i5 or better (i7+ recommended for face recognition)
- **RAM**: Minimum 8GB (16GB+ recommended)
- **Storage**: 50GB+ free space (for storing visitor images)
- **Camera**: USB webcam or IP camera with RTSP support
- **GPU** (Optional): NVIDIA GPU with CUDA for better performance

### Software
- **Operating System**: Linux (Ubuntu 20.04+), macOS, or Windows 10+
- **Python**: 3.8 or higher
- **Node.js**: 16.x or higher
- **PostgreSQL**: 12 or higher
- **Docker** (Optional): For containerized deployment

---

## Quick Start Guide

### Option 1: Docker Deployment (Recommended)

```bash
# Clone or extract the project
cd visitor-monitoring-system

# Start all services
docker-compose up -d

# Access the application
# Frontend: http://localhost:3000
# Backend API: http://localhost:5000
```

### Option 2: Manual Installation

```bash
# 1. Set up PostgreSQL
sudo apt-get install postgresql postgresql-contrib
sudo -u postgres createuser visitor_user
sudo -u postgres createdb visitor_monitoring
sudo -u postgres psql
ALTER USER visitor_user WITH PASSWORD 'visitor_pass';
GRANT ALL PRIVILEGES ON DATABASE visitor_monitoring TO visitor_user;
\q

# 2. Initialize database
psql -U visitor_user -d visitor_monitoring -f database/schema.sql

# 3. Set up backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your configuration

# Run backend
python app.py

# 4. Set up frontend (in new terminal)
cd frontend
npm install
npm run dev
```

**Default Login:**
- Username: `admin`
- Password: `admin123`
- ⚠️ **CHANGE THIS IMMEDIATELY IN PRODUCTION!**

---

## Detailed Installation

### 1. Database Setup

#### Install PostgreSQL

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib libpq-dev
```

**macOS:**
```bash
brew install postgresql
brew services start postgresql
```

**Windows:**
Download and install from [postgresql.org](https://www.postgresql.org/download/windows/)

#### Create Database

```bash
# Connect to PostgreSQL
sudo -u postgres psql

# Create user and database
CREATE USER visitor_user WITH PASSWORD 'visitor_pass';
CREATE DATABASE visitor_monitoring OWNER visitor_user;
GRANT ALL PRIVILEGES ON DATABASE visitor_monitoring TO visitor_user;
\q
```

#### Initialize Schema

```bash
cd visitor-monitoring-system
psql -U visitor_user -d visitor_monitoring -f database/schema.sql
```

### 2. Backend Setup

#### Install Python Dependencies

```bash
cd backend

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On Linux/Mac:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

#### Configure Environment Variables

Create `.env` file in `backend/` directory:

```env
# Database Configuration
DATABASE_URL=postgresql://visitor_user:visitor_pass@localhost:5432/visitor_monitoring

# Security
SECRET_KEY=your-very-secret-key-change-in-production
JWT_SECRET_KEY=your-jwt-secret-key-change-in-production

# Flask Configuration
FLASK_ENV=development
FLASK_DEBUG=True

# CORS (comma-separated origins)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Organization Details
ORGANIZATION_NAME=Your Organization Name
# ORGANIZATION_LOGO=/path/to/logo.png

# Face Recognition Settings
FACE_CONFIDENCE_THRESHOLD=0.5
FACE_SIMILARITY_THRESHOLD=0.5
MIN_FACE_AREA=11000
BLUR_THRESHOLD=50.0
TILT_THRESHOLD=0.25

# Camera Settings
DEFAULT_CAMERA_URL=0

# Data Retention (days)
DATA_RETENTION_DAYS=90
```

#### Download Face Recognition Models

The InsightFace library will automatically download required models on first run. Ensure you have internet connection during first startup.

### 3. Frontend Setup

#### Install Node.js

**Ubuntu/Debian:**
```bash
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs
```

**macOS:**
```bash
brew install node
```

**Windows:**
Download from [nodejs.org](https://nodejs.org/)

#### Install Frontend Dependencies

```bash
cd frontend
npm install
```

#### Configure Frontend

Create `.env` file in `frontend/` directory:

```env
VITE_API_URL=http://localhost:5000/api
VITE_WS_URL=http://localhost:5000
```

### 4. Create Required Directories

```bash
cd backend
mkdir -p static/uploads/staff
mkdir -p static/uploads/visitors
mkdir -p reports
```

---

## Configuration

### Face Recognition Parameters

Edit these in `backend/config.py`:

```python
# Face Detection Confidence (0.0 - 1.0)
FACE_CONFIDENCE_THRESHOLD = 0.5

# Face Matching Similarity (0.0 - 1.0)
FACE_SIMILARITY_THRESHOLD = 0.5

# Minimum face area in pixels
MIN_FACE_AREA = 11000

# Blur detection threshold
BLUR_THRESHOLD = 50.0

# Face tilt threshold
TILT_THRESHOLD = 0.25

# Session grace period (seconds before ending session)
SESSION_GRACE_PERIOD = 2.0
```

### Camera Configuration

Add cameras via Settings UI or directly in database:

```sql
INSERT INTO cameras (camera_id, name, location, stream_url, camera_type)
VALUES ('CAM001', 'Main Entrance', 'Building A - Entrance', '0', 'webcam');

-- For RTSP cameras:
INSERT INTO cameras (camera_id, name, location, stream_url, camera_type)
VALUES ('CAM002', 'Lobby', 'Building A - Lobby', 'rtsp://username:password@192.168.1.100:554/stream', 'rtsp');
```

---

## Running the Application

### Development Mode

#### Terminal 1: Backend
```bash
cd backend
source venv/bin/activate
python app.py
```

Backend will run on `http://localhost:5000`

#### Terminal 2: Frontend
```bash
cd frontend
npm run dev
```

Frontend will run on `http://localhost:3000` or `http://localhost:5173`

### Production Mode

#### Using Gunicorn (Backend)

```bash
cd backend
source venv/bin/activate
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

#### Build Frontend

```bash
cd frontend
npm run build
```

Serve the `dist/` folder using Nginx or Apache.

### Using Docker

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

---

## Production Deployment

### Security Checklist

- [ ] Change default admin password
- [ ] Generate strong SECRET_KEY and JWT_SECRET_KEY
- [ ] Enable HTTPS (SSL/TLS)
- [ ] Configure firewall (allow only necessary ports)
- [ ] Set up database backups
- [ ] Configure CORS properly (no wildcards)
- [ ] Enable rate limiting
- [ ] Set up monitoring and logging
- [ ] Regular security updates

### Nginx Configuration

```nginx
# Frontend
server {
    listen 80;
    server_name yourdomain.com;
    
    location / {
        root /path/to/visitor-monitoring-system/frontend/dist;
        try_files $uri $uri/ /index.html;
    }
    
    location /api {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Systemd Service (Backend)

Create `/etc/systemd/system/visitor-monitor.service`:

```ini
[Unit]
Description=Visitor Monitoring Backend
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/visitor-monitoring-system/backend
Environment="PATH=/path/to/visitor-monitoring-system/backend/venv/bin"
ExecStart=/path/to/visitor-monitoring-system/backend/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable visitor-monitor
sudo systemctl start visitor-monitor
sudo systemctl status visitor-monitor
```

### Database Backups

```bash
# Create backup
pg_dump -U visitor_user visitor_monitoring > backup_$(date +%Y%m%d).sql

# Restore backup
psql -U visitor_user visitor_monitoring < backup_20240101.sql

# Automated daily backups (crontab)
0 2 * * * pg_dump -U visitor_user visitor_monitoring > /backups/visitor_$(date +\%Y\%m\%d).sql
```

---

## Troubleshooting

### Common Issues

#### 1. Face Recognition Models Not Loading

**Problem:** InsightFace models fail to download

**Solution:**
```bash
# Manually download models
cd ~/.insightface/models
wget https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip
unzip buffalo_l.zip
```

#### 2. Database Connection Errors

**Problem:** Cannot connect to PostgreSQL

**Solution:**
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Check connection
psql -U visitor_user -d visitor_monitoring -h localhost

# Edit pg_hba.conf if needed
sudo nano /etc/postgresql/*/main/pg_hba.conf
# Add: host visitor_monitoring visitor_user 127.0.0.1/32 md5
sudo systemctl restart postgresql
```

#### 3. Camera Not Working

**Problem:** Camera feed not displaying

**Solution:**
- Check camera permissions: `ls -l /dev/video*`
- Add user to video group: `sudo usermod -a -G video $USER`
- Test camera: `ffplay /dev/video0`
- For RTSP: Test stream with VLC or ffmpeg

#### 4. Port Already in Use

**Problem:** Port 5000 or 3000 already in use

**Solution:**
```bash
# Find process using port
sudo lsof -i :5000
sudo lsof -i :3000

# Kill process
kill -9 <PID>

# Or change port in configuration
```

#### 5. CORS Errors

**Problem:** Frontend cannot connect to backend

**Solution:**
- Check `CORS_ORIGINS` in backend `.env`
- Ensure frontend URL is in allowed origins
- Clear browser cache
- Check browser console for detailed error

### Performance Optimization

#### 1. Slow Face Recognition

- Use GPU if available (install `onnxruntime-gpu`)
- Reduce camera resolution
- Increase detection interval
- Use buffalo_s model instead of buffalo_l

#### 2. High Memory Usage

- Limit active sessions
- Implement data retention policy
- Use pagination for large queries
- Optimize image storage (compress images)

#### 3. Database Slow Queries

```sql
-- Add indexes
CREATE INDEX idx_visitors_first_seen ON visitors(first_seen);
CREATE INDEX idx_visitor_sessions_entry ON visitor_sessions(entry_time);
CREATE INDEX idx_visitor_sessions_active ON visitor_sessions(is_active) WHERE is_active = true;

-- Analyze and vacuum
VACUUM ANALYZE;
```

### Logging

#### Enable Debug Logging

Backend (`backend/app.py`):
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Frontend (browser console):
```javascript
localStorage.setItem('debug', 'true');
```

#### Log Files

```bash
# Backend logs
tail -f backend/app.log

# System logs
journalctl -u visitor-monitor -f

# Nginx logs
tail -f /var/log/nginx/error.log
```

---

## Support

For issues, questions, or contributions:

1. Check documentation
2. Review troubleshooting guide
3. Search existing issues
4. Contact development team

---

## License

Proprietary - All rights reserved

## Version

Version 1.0.0 - February 2026
