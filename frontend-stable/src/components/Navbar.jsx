import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';

export default function Navbar() {
  const { user, logout } = useAuth();
  const { isDark, toggleTheme } = useTheme();

  return (
    <nav className="app-navbar px-6 py-4 flex justify-between items-center">
      <div>
        <div className="app-navbar__kicker">Visitor Monitoring System</div>
        <div className="app-navbar__title">Operations Console</div>
      </div>
      <div className="flex items-center gap-4">
        <button onClick={toggleTheme} className="btn btn-secondary text-sm">
          {isDark ? 'Light Mode' : 'Dark Mode'}
        </button>
        <span className="text-sm text-gray-600">Welcome, {user?.full_name || user?.username}</span>
        <button 
          onClick={logout}
          className="btn btn-danger-outline text-sm flex items-center gap-1"
        >
          <span>Logout</span>
        </button>
      </div>
    </nav>
  );
}
