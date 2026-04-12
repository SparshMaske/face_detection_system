import { useEffect, useState } from 'react';
import { getVisitors } from '../services/visitorService';
import Card from '../components/Card';
import { formatDateOnly, formatDateTime12h } from '../utils/formatters';

export default function VisitorLogs() {
  const [visitors, setVisitors] = useState([]);
  const [page, setPage] = useState(1);
  const [error, setError] = useState('');

  const fetchVisitors = async (p = 1) => {
    try {
      const res = await getVisitors({ page: p, per_page: 20 });
      setError('');
      setVisitors(res.data.visitors || []);
      setPage(res.data.current_page || p);
    } catch (err) {
      setError('Failed to load visitor logs');
    }
  };

  useEffect(() => {
    fetchVisitors(page);
    const timer = setInterval(() => fetchVisitors(page), 5000);
    return () => clearInterval(timer);
  }, [page]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Visitor Logs</h1>
      {error && <div className="text-red-600">{error}</div>}
      
      <Card>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>First Seen</th>
                <th>Last Seen</th>
                <th>Duration</th>
                <th>Visits</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {visitors.map(v => (
                <tr key={v.id}>
                  <td>{v.event_display_id || v.visitor_id}</td>
                  <td>{formatDateOnly(v.first_seen, '-')}</td>
                  <td>{formatDateTime12h(v.last_seen, '-')}</td>
                  <td>{v.event_duration_formatted || '-'}</td>
                  <td>{v.visit_count}</td>
                  <td>
                    <span className="badge badge-green">Logged</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="table-pagination flex justify-between mt-4">
          <button disabled={page === 1} onClick={() => fetchVisitors(page - 1)} className="btn btn-secondary">Previous</button>
          <span>Page {page}</span>
          <button onClick={() => fetchVisitors(page + 1)} className="btn btn-secondary">Next</button>
        </div>
      </Card>
    </div>
  );
}
