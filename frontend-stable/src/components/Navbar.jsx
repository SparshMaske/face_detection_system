import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';

export default function Navbar({ onToggleMenu }) {
  const { user, logout } = useAuth();
  const { isDark, toggleTheme } = useTheme();

  return (
    <nav className="app-navbar px-6 py-4">
      <div className="app-navbar__top flex justify-between items-center gap-3">
        <div className="app-navbar__identity">
          <div className="app-navbar__kicker">Visitor Monitoring System</div>
          <div className="app-navbar__title">Operations Console</div>
        </div>
        <button type="button" className="app-navbar__menu btn btn-secondary" onClick={onToggleMenu}>
          Menu
        </button>
      </div>
      <div className="app-navbar__actions flex items-center gap-4">
        <button onClick={toggleTheme} className="btn btn-secondary text-sm">
          {isDark ? 'Light Mode' : 'Dark Mode'}
        </button>
        <span className="app-navbar__welcome text-sm text-gray-600">
          Welcome, {user?.full_name || user?.username}
        </span>
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
