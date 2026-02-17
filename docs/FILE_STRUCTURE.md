# Smart Visitor Monitoring System - File Structure

```
visitor-monitoring-system/
│
├── backend/                          # Flask Backend
│   ├── app.py                        # Main Flask application
│   ├── config.py                     # Configuration settings
│   ├── requirements.txt              # Python dependencies
│   │
│   ├── models/                       # Database Models
│   │   ├── __init__.py
│   │   ├── user.py                   # User model
│   │   ├── staff.py                  # Staff model
│   │   ├── visitor.py                # Visitor model
│   │   └── camera.py                 # Camera model
│   │
│   ├── routes/                       # API Routes
│   │   ├── __init__.py
│   │   ├── auth.py                   # Authentication routes
│   │   ├── dashboard.py              # Dashboard routes
│   │   ├── staff.py                  # Staff management routes
│   │   ├── visitors.py               # Visitor logs routes
│   │   ├── reports.py                # Report generation routes
│   │   ├── analytics.py              # Analytics routes
│   │   ├── settings.py               # Settings routes
│   │   └── camera.py                 # Camera feed routes
│   │
│   ├── services/                     # Business Logic
│   │   ├── __init__.py
│   │   ├── face_recognition.py       # Face recognition service
│   │   ├── visitor_manager.py        # Visitor tracking logic
│   │   ├── staff_manager.py          # Staff management logic
│   │   ├── report_generator.py       # PDF report generation
│   │   └── analytics_service.py      # Analytics calculations
│   │
│   ├── utils/                        # Utility functions
│   │   ├── __init__.py
│   │   ├── auth.py                   # JWT helpers
│   │   ├── validators.py             # Input validation
│   │   └── image_processor.py        # Image processing utilities
│   │
│   ├── static/                       # Static files
│   │   └── uploads/                  # Uploaded images
│   │       ├── staff/                # Staff images
│   │       └── visitors/             # Visitor images
│   │
│   └── reports/                      # Generated reports
│
├── frontend/                         # React Frontend
│   ├── package.json                  # Node dependencies
│   ├── package-lock.json
│   ├── .gitignore
│   │
│   ├── public/                       # Public assets
│   │   ├── index.html
│   │   ├── favicon.ico
│   │   └── logo.png
│   │
│   └── src/                          # Source code
│       ├── index.js                  # Entry point
│       ├── App.js                    # Main App component
│       ├── index.css                 # Global styles
│       │
│       ├── components/               # Reusable components
│       │   ├── Navbar.js
│       │   ├── Sidebar.js
│       │   ├── Card.js
│       │   ├── Table.js
│       │   ├── Modal.js
│       │   ├── Loading.js
│       │   ├── DateRangePicker.js
│       │   └── ConfirmDialog.js
│       │
│       ├── pages/                    # Page components
│       │   ├── Login.js              # Login page
│       │   ├── Dashboard.js          # Dashboard
│       │   ├── LiveView.js           # Live camera view
│       │   ├── StaffManagement.js    # Staff management
│       │   ├── VisitorLogs.js        # Visitor logs
│       │   ├── VisitorDetail.js      # Visitor detail view
│       │   ├── Reports.js            # Report generation
│       │   ├── Analytics.js          # Analytics & insights
│       │   └── Settings.js           # System settings
│       │
│       ├── services/                 # API services
│       │   ├── api.js                # Axios configuration
│       │   ├── authService.js        # Authentication API
│       │   ├── dashboardService.js   # Dashboard API
│       │   ├── staffService.js       # Staff API
│       │   ├── visitorService.js     # Visitor API
│       │   ├── reportService.js      # Report API
│       │   ├── analyticsService.js   # Analytics API
│       │   └── settingsService.js    # Settings API
│       │
│       ├── context/                  # React Context
│       │   ├── AuthContext.js        # Authentication context
│       │   └── ThemeContext.js       # Dark mode context
│       │
│       ├── hooks/                    # Custom hooks
│       │   ├── useAuth.js
│       │   ├── useTheme.js
│       │   └── useWebSocket.js
│       │
│       └── utils/                    # Utility functions
│           ├── constants.js
│           ├── formatters.js
│           └── validators.js
│
├── database/                         # Database scripts
│   ├── schema.sql                    # Database schema
│   ├── seed.sql                      # Sample data
│   └── migrations/                   # Migration scripts
│
├── docker/                           # Docker configuration
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── docker-compose.yml
│
├── docs/                             # Documentation
│   ├── API.md                        # API documentation
│   ├── DEPLOYMENT.md                 # Deployment guide
│   └── USER_GUIDE.md                 # User manual
│
├── .env.example                      # Environment variables template
├── .gitignore
└── README.md                         # Project overview
```

## Key Directories Explained

### Backend (`/backend`)
- **models/**: SQLAlchemy ORM models for database tables
- **routes/**: Flask blueprints for different API endpoints
- **services/**: Core business logic separated from routes
- **utils/**: Helper functions and utilities
- **static/uploads/**: Stores uploaded staff and visitor images
- **reports/**: Generated PDF reports

### Frontend (`/frontend/src`)
- **components/**: Reusable UI components (buttons, cards, modals, etc.)
- **pages/**: Full page components matching routes
- **services/**: API communication layer
- **context/**: Global state management using React Context
- **hooks/**: Custom React hooks for common functionality

### Database (`/database`)
- SQL scripts for schema creation and seeding data
- Migration scripts for schema updates

### Docker (`/docker`)
- Containerization configuration for easy deployment
- docker-compose for orchestrating all services

## Technology Stack

### Backend
- **Framework**: Flask
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Authentication**: JWT (PyJWT)
- **Face Recognition**: InsightFace
- **Computer Vision**: OpenCV
- **PDF Generation**: FPDF / ReportLab
- **Real-time**: Flask-SocketIO (for live updates)

### Frontend
- **Framework**: React 18
- **Routing**: React Router v6
- **State Management**: Context API + Custom Hooks
- **HTTP Client**: Axios
- **UI Components**: Custom components with Tailwind CSS
- **Real-time**: Socket.IO Client
- **Charts**: Recharts / Chart.js
- **Date Handling**: date-fns
- **Form Handling**: React Hook Form

### DevOps
- **Containerization**: Docker
- **Database**: PostgreSQL 15
- **Reverse Proxy**: Nginx (optional)
- **Process Manager**: Gunicorn (production)
