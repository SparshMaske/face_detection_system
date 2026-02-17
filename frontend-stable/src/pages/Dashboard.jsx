import { useEffect, useState } from 'react';
import { getStats, getRecentActivity } from '../services/dashboardService';
import Card from '../components/Card';

export default function Dashboard() {
  const [stats, setStats] = useState({});
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;

    const fetchData = async () => {
      try {
        const [statsRes, actRes] = await Promise.all([getStats(), getRecentActivity()]);
        if (!mounted) return;
        setError('');
        setStats(statsRes.data || {});
        setActivity(actRes.data || []);
      } catch (err) {
        if (!mounted) return;
        setError('Failed to load dashboard data');
      } finally {
        if (mounted) setLoading(false);
      }
    };

    fetchData();
    const timer = setInterval(fetchData, 5000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);

  if (loading) return <div className="p-6">Loading Dashboard...</div>;
  if (error) return <div className="p-6 text-red-600">{error}</div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <Card title="Event Visitors" className="text-center">
          <div className="text-4xl font-bold text-blue-600">{stats.today_visitors || 0}</div>
        </Card>
        <Card title="Active Now" className="text-center">
          <div className="text-4xl font-bold text-green-600">{stats.active_visitors || 0}</div>
        </Card>
        <Card title="Total Staff" className="text-center">
          <div className="text-4xl font-bold text-gray-600">{stats.total_staff || 0}</div>
        </Card>
        <Card title="Total Visitors" className="text-center">
          <div className="text-4xl font-bold text-gray-600">{stats.total_visitors || 0}</div>
        </Card>
      </div>

      <Card title="Recent Activity">
        <table className="table">
          <thead>
            <tr>
              <th>Visitor ID</th>
              <th>Entry Time</th>
              <th>Exit Time</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {activity.map((act) => (
              <tr key={act.id}>
                <td>{act.visitor_id}</td>
                <td>{new Date(act.entry_time).toLocaleString()}</td>
                <td>{act.exit_time ? new Date(act.exit_time).toLocaleString() : '-'}</td>
                <td>
                  <span className={`badge ${act.is_active ? 'badge-green' : 'badge-red'}`}>
                    {act.is_active ? 'Active' : 'Left'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
