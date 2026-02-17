import { NavLink } from 'react-router-dom';

export default function Sidebar() {
  const navItems = [
    { path: '/event-scheduler', label: 'Event Scheduler', code: 'EV' },
    { path: '/dashboard', label: 'Dashboard', code: 'DB' },
    { path: '/live', label: 'Live View', code: 'LV' },
    { path: '/staff', label: 'Staff Management', code: 'ST' },
    { path: '/visitors', label: 'Visitor Logs', code: 'VL' },
    { path: '/reports', label: 'Reports', code: 'RP' },
    { path: '/analytics', label: 'Analytics', code: 'AN' },
    { path: '/settings', label: 'Settings', code: 'SE' },
  ];

  return (
    <aside className="app-sidebar w-64 text-white flex flex-col">
      <div className="app-sidebar__brand border-b">
        <div className="app-sidebar__title">Visitor Monitor</div>
        <div className="app-sidebar__subtitle">Control Panel</div>
      </div>
      <nav className="app-sidebar__nav flex-1 p-4 space-y-2">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `app-sidebar__link ${isActive ? 'is-active' : ''}`
            }
          >
            <span className="app-sidebar__code">{item.code}</span>
            <span className="app-sidebar__label">{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
