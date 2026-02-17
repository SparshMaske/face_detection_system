import { BrowserRouter as Router, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';

// Pages
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import LiveView from './pages/LiveView';
import StaffManagement from './pages/StaffManagement';
import VisitorLogs from './pages/VisitorLogs';
import VisitorDetail from './pages/VisitorDetail';
import Reports from './pages/Reports';
import Analytics from './pages/Analytics';
import Settings from './pages/Settings';
import EventScheduler from './pages/EventScheduler';

// Protected Route Wrapper
const ProtectedRoute = () => {
  const { user } = useAuth();
  return user ? <Outlet /> : <Navigate to="/login" replace />;
};

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <Router>
          <Routes>
            <Route path="/login" element={<Login />} />
            
            <Route element={<ProtectedRoute />}>
              <Route path="/" element={<Layout />}>
                <Route index element={<Navigate to="/event-scheduler" replace />} />
                <Route path="event-scheduler" element={<EventScheduler />} />
                <Route path="dashboard" element={<Dashboard />} />
                <Route path="live" element={<LiveView />} />
                <Route path="staff" element={<StaffManagement />} />
                <Route path="visitors" element={<VisitorLogs />} />
                <Route path="visitors/:id" element={<VisitorDetail />} />
                <Route path="reports" element={<Reports />} />
                <Route path="analytics" element={<Analytics />} />
                <Route path="settings" element={<Settings />} />
              </Route>
            </Route>
          </Routes>
        </Router>
      </AuthProvider>
    </ThemeProvider>
  );
}

// Main Layout with Navbar and Sidebar
function Layout() {
  return (
    <div className="app-shell flex h-screen bg-gray-50">
      <Sidebar />
      <div className="app-content flex-1 flex flex-col overflow-hidden">
        <Navbar />
        <main className="app-main flex-1 overflow-x-hidden overflow-y-auto bg-gray-50 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default App;
