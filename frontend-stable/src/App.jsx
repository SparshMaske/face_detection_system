import {
  BrowserRouter,
  HashRouter,
  Routes,
  Route,
  Navigate,
  Outlet,
  useLocation,
} from 'react-router-dom';
import { useEffect, useState } from 'react';
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
import EventManagement from './pages/EventManagement';

// Protected Route Wrapper
const ProtectedRoute = () => {
  const { user } = useAuth();
  return user ? <Outlet /> : <Navigate to="/login" replace />;
};

function App() {
  const isEmbeddedProtocol =
    typeof window !== 'undefined' &&
    ['about:', 'data:', 'blob:'].includes(window.location.protocol);
  const Router = isEmbeddedProtocol ? HashRouter : BrowserRouter;

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
                <Route path="event-management" element={<EventManagement />} />
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
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  return (
    <div className="app-shell flex h-screen bg-gray-50">
      <Sidebar
        mobileOpen={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
        onNavigate={() => setMobileNavOpen(false)}
      />
      <div className="app-content flex-1 flex flex-col overflow-hidden">
        <Navbar onToggleMenu={() => setMobileNavOpen((prev) => !prev)} />
        <main className="app-main flex-1 overflow-x-hidden overflow-y-auto bg-gray-50 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default App;
