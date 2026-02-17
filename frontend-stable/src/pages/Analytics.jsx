import { useEffect, useState } from 'react';
import { getFootfallTrends, getPeakHours, getSummary } from '../services/analyticsService';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export default function Analytics() {
  const [trends, setTrends] = useState([]);
  const [peakHours, setPeakHours] = useState([]);
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      try {
        setError('');
        const [t, p, s] = await Promise.all([
          getFootfallTrends(7),
          getPeakHours(7),
          getSummary(30),
        ]);

        setTrends(t.data || []);
        setPeakHours(p.data || []);
        setSummary(s.data || {});
      } catch (err) {
        setError('Failed to load analytics data');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) return <div className="p-6">Loading Analytics...</div>;
  if (error) return <div className="p-6 text-red-600">{error}</div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Analytics</h1>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="card p-6 text-center">
          <div className="text-gray-500 text-sm">Total Visitors (30d)</div>
          <div className="text-2xl font-bold">{summary.total_visitors || 0}</div>
        </div>
        <div className="card p-6 text-center">
          <div className="text-gray-500 text-sm">Avg Duration</div>
          <div className="text-2xl font-bold">{Math.round((summary.average_duration_seconds || 0) / 60)}m</div>
        </div>
        <div className="card p-6 text-center">
          <div className="text-gray-500 text-sm">Peak Day</div>
          <div className="text-2xl font-bold">{summary.peak_day?.count || 0}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card p-6">
          <h3 className="font-bold mb-4">Trends (7 Days)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={trends}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{fontSize: 10}} />
              <YAxis />
              <Tooltip />
              <Bar dataKey="count" fill="#2563eb" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-6">
          <h3 className="font-bold mb-4">Peak Hours</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={peakHours}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="hour" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="count" fill="#16a34a" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
