# API Documentation

## Base URL
```
http://localhost:5000/api
```

## Authentication

All protected endpoints require a JWT token in the Authorization header:
```
Authorization: Bearer <access_token>
```

---

## Authentication Endpoints

### POST /api/auth/login
Login to get access token

**Request Body:**
```json
{
  "username": "admin",
  "password": "admin123"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "role": "admin",
    "full_name": "System Administrator"
  }
}
```

### POST /api/auth/refresh
Refresh access token

**Headers:**
```
Authorization: Bearer <refresh_token>
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

### GET /api/auth/me
Get current user information

**Response:**
```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "role": "admin",
  "full_name": "System Administrator",
  "created_at": "2026-01-01T00:00:00",
  "last_login": "2026-02-04T10:30:00"
}
```

---

## Dashboard Endpoints

### GET /api/dashboard/stats
Get dashboard statistics

**Response:**
```json
{
  "today_visitors": 25,
  "active_visitors": 5,
  "total_visitors": 1543,
  "total_staff": 42,
  "recent_visitors": [...]
}
```

### GET /api/dashboard/recent-activity
Get recent visitor activity

**Response:**
```json
[
  {
    "id": 123,
    "visitor_id": 45,
    "entry_time": "2026-02-04T14:30:00",
    "exit_time": "2026-02-04T15:45:00",
    "duration_seconds": 4500,
    "duration_formatted": "1h 15m 0s",
    "is_active": false
  }
]
```

---

## Staff Management Endpoints

### GET /api/staff
Get all staff members

**Response:**
```json
[
  {
    "id": 1,
    "staff_id": "EMP001",
    "name": "John Doe",
    "department": "Engineering",
    "position": "Senior Engineer",
    "email": "john@example.com",
    "phone": "+1234567890",
    "is_active": true,
    "created_at": "2026-01-15T09:00:00",
    "images": [
      {
        "id": 1,
        "image_path": "staff/EMP001/photo1.jpg",
        "is_primary": true
      }
    ]
  }
]
```

### POST /api/staff
Create new staff member

**Request (multipart/form-data):**
```
staff_id: EMP002
name: Jane Smith
department: HR
position: HR Manager
email: jane@example.com
phone: +1234567891
images: [file1, file2, ...]
```

**Response:**
```json
{
  "id": 2,
  "staff_id": "EMP002",
  "name": "Jane Smith",
  ...
}
```

### GET /api/staff/<id>
Get specific staff member

### PUT /api/staff/<id>
Update staff member

### DELETE /api/staff/<id>
Delete staff member

---

## Visitor Logs Endpoints

### GET /api/visitors
Get visitor logs with pagination and filtering

**Query Parameters:**
- `page` (int): Page number (default: 1)
- `per_page` (int): Items per page (default: 50)
- `start_date` (ISO date): Filter by start date
- `end_date` (ISO date): Filter by end date

**Response:**
```json
{
  "visitors": [
    {
      "id": 1,
      "visitor_id": "V000001",
      "primary_image_path": "visitors/V000001/V000001_20260204_143022.jpg",
      "first_seen": "2026-02-04T14:30:22",
      "last_seen": "2026-02-04T15:45:10",
      "visit_count": 1
    }
  ],
  "total": 150,
  "pages": 3,
  "current_page": 1
}
```

### GET /api/visitors/<id>
Get detailed visitor information including all sessions

**Response:**
```json
{
  "id": 1,
  "visitor_id": "V000001",
  "primary_image_path": "visitors/V000001/V000001_20260204_143022.jpg",
  "first_seen": "2026-02-04T14:30:22",
  "last_seen": "2026-02-04T15:45:10",
  "visit_count": 1,
  "sessions": [
    {
      "id": 1,
      "entry_time": "2026-02-04T14:30:22",
      "exit_time": "2026-02-04T15:45:10",
      "duration_seconds": 4488,
      "duration_formatted": "1h 14m 48s",
      "camera_id": 1,
      "is_active": false
    }
  ]
}
```

---

## Reports Endpoints

### POST /api/reports/generate
Generate visitor report

**Request Body:**
```json
{
  "start_date": "2026-02-01T00:00:00",
  "end_date": "2026-02-04T23:59:59",
  "report_type": "daily"
}
```

**Response:** PDF file download

### GET /api/reports/list
List all generated reports

**Response:**
```json
[
  {
    "filename": "Visitor_Report_daily_20260204_153022.pdf",
    "size": 2458624,
    "created": "2026-02-04T15:30:22"
  }
]
```

### GET /api/reports/download/<filename>
Download specific report

**Response:** PDF file

---

## Analytics Endpoints

### GET /api/analytics/footfall-trends
Get visitor footfall trends

**Query Parameters:**
- `days` (int): Number of days (default: 7)

**Response:**
```json
[
  {
    "date": "2026-02-01",
    "count": 45
  },
  {
    "date": "2026-02-02",
    "count": 52
  }
]
```

### GET /api/analytics/peak-hours
Get peak visiting hours

**Query Parameters:**
- `days` (int): Number of days (default: 7)

**Response:**
```json
[
  {
    "hour": 9,
    "count": 25
  },
  {
    "hour": 10,
    "count": 42
  }
]
```

### GET /api/analytics/average-duration
Get average visit duration

**Response:**
```json
{
  "average_seconds": 3600,
  "average_minutes": 60.0
}
```

### GET /api/analytics/summary
Get comprehensive analytics summary

**Query Parameters:**
- `days` (int): Number of days (default: 30)

**Response:**
```json
{
  "total_visitors": 1250,
  "total_sessions": 1450,
  "average_duration_seconds": 3600,
  "average_visits_per_day": 41.67,
  "peak_day": {
    "date": "2026-02-03",
    "count": 68
  }
}
```

---

## Camera Endpoints

### GET /api/camera
Get all cameras

**Response:**
```json
[
  {
    "id": 1,
    "camera_id": "CAM001",
    "name": "Main Entrance",
    "location": "Building A - Entrance",
    "stream_url": "0",
    "camera_type": "webcam",
    "is_active": true,
    "is_online": true,
    "fps_limit": 30,
    "resolution": {
      "width": 1920,
      "height": 1080
    }
  }
]
```

### POST /api/camera
Create new camera

**Request Body:**
```json
{
  "camera_id": "CAM002",
  "name": "Lobby Camera",
  "location": "Building A - Lobby",
  "stream_url": "rtsp://username:password@192.168.1.100:554/stream",
  "camera_type": "rtsp"
}
```

### GET /api/camera/feed/<camera_id>
Stream live camera feed with face detection

**Response:** MJPEG video stream

---

## Settings Endpoints

### GET /api/settings
Get all system settings

**Response:**
```json
[
  {
    "key": "face_threshold",
    "value": 0.5,
    "value_type": "float",
    "description": "Face recognition similarity threshold"
  }
]
```

### GET /api/settings/<key>
Get specific setting

### POST /api/settings
Update multiple settings

**Request Body:**
```json
{
  "face_threshold": 0.6,
  "blur_threshold": 60.0
}
```

**Response:**
```json
{
  "updated": ["face_threshold", "blur_threshold"]
}
```

---

## Error Responses

All endpoints may return the following error responses:

### 400 Bad Request
```json
{
  "error": "Invalid input parameters"
}
```

### 401 Unauthorized
```json
{
  "error": "Missing or invalid authentication token"
}
```

### 403 Forbidden
```json
{
  "error": "Insufficient permissions"
}
```

### 404 Not Found
```json
{
  "error": "Resource not found"
}
```

### 500 Internal Server Error
```json
{
  "error": "Internal server error message"
}
```

---

## Rate Limiting

API endpoints are rate-limited to prevent abuse:
- Authentication endpoints: 10 requests per minute
- All other endpoints: 100 requests per minute

Rate limit headers are included in responses:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1707062400
```

---

## WebSocket Events

The system supports real-time updates via WebSocket connection at `ws://localhost:5000`:

### Events

**visitor_detected**
```json
{
  "event": "visitor_detected",
  "data": {
    "visitor_id": "V000123",
    "timestamp": "2026-02-04T14:30:22",
    "camera_id": 1,
    "is_new": true
  }
}
```

**visitor_exited**
```json
{
  "event": "visitor_exited",
  "data": {
    "visitor_id": "V000123",
    "exit_time": "2026-02-04T15:45:10",
    "duration_seconds": 4488
  }
}
```

**stats_updated**
```json
{
  "event": "stats_updated",
  "data": {
    "active_visitors": 5,
    "today_visitors": 25
  }
}
```

---

## Postman Collection

Import the provided Postman collection for easy API testing:
- File: `docs/Visitor_Monitoring_API.postman_collection.json`
