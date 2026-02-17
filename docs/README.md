# Smart Visitor Monitoring & Verification System

A comprehensive AI-powered visitor monitoring system with face recognition, real-time tracking, and automated reporting.

## Features

- **Real-time Face Recognition**: AI-powered face detection and recognition using InsightFace
- **Staff Exclusion**: Automatically exclude registered staff from visitor logs
- **Live Monitoring**: Real-time camera feeds with face detection overlays
- **Session Tracking**: Accurate entry/exit time logging with duration tracking
- **Comprehensive Reports**: PDF reports with visitor thumbnails and timestamps
- **Analytics Dashboard**: Visualize visitor trends, peak hours, and footfall data
- **Multi-camera Support**: Manage multiple camera feeds simultaneously
- **Role-based Access**: Admin and viewer roles with appropriate permissions
- **Dark Mode**: Eye-friendly interface for control room environments

## Technology Stack

### Backend
- Flask (Python web framework)
- PostgreSQL (Database)
- InsightFace (Face recognition)
- OpenCV (Image processing)
- ReportLab (PDF generation)
- JWT (Authentication)
- SocketIO (Real-time updates)

### Frontend
- React 18
- React Router
- Axios (HTTP client)
- Recharts (Data visualization)
- Tailwind CSS (Styling)
- Socket.IO Client (Real-time)

## Installation

### Prerequisites
- Python 3.8+
- Node.js 16+
- PostgreSQL 12+
- Webcam or RTSP camera

### Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set up database
createdb visitor_monitoring
psql visitor_monitoring < ../database/schema.sql

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run backend
python app.py
```

### Frontend Setup

```bash
cd frontend-stable
npm install
npm start
```

## Configuration

### Environment Variables

Create `.env` file in backend directory:

```
DATABASE_URL=postgresql://visitor_user:visitor_pass@localhost:5432/visitor_monitoring
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret
FLASK_ENV=development
```

### Default Credentials

- **Username**: admin
- **Password**: admin123
- ⚠️ Change immediately in production!

## Usage

1. **Login**: Access the system at `http://localhost:3000`
2. **Add Staff**: Navigate to Staff Management and upload staff photos
3. **Configure Cameras**: Set up camera streams in Settings
4. **Start Monitoring**: View live feed and track visitors
5. **Generate Reports**: Create PDF reports for any date range

## API Documentation

See [docs/API.md](docs/API.md) for complete API documentation.

## Docker Deployment

```bash
docker compose up --build -d
```

## Streamlit Shareable Deployment

Use this if you want a Streamlit share link while keeping the same React UI/UX:

1. Build frontend in this repo (`frontend-stable/build`).
2. Deploy backend publicly.
3. Deploy this repo on Streamlit with app file `streamlit_app.py`.
4. Optional: set `BACKEND_API_URL` in Streamlit Secrets if backend is not on `/api`.

Detailed steps:
- `docs/LOCAL_AND_STREAMLIT_DEPLOY.md`

## Project Structure

See [FILE_STRUCTURE.md](FILE_STRUCTURE.md) for detailed project organization.

## License

Proprietary - All rights reserved

## Support

For issues and questions, please contact the development team.
