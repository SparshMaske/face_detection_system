import { useCallback, useEffect, useMemo, useState } from 'react';
import Card from '../components/Card';
import {
  deleteScheduledEvent,
  downloadCompletedEventExcel,
  getEventManagement,
} from '../services/eventService';
import { formatDateTime12h } from '../utils/formatters';

function fmtDateTime(value) {
  return formatDateTime12h(value, 'N/A');
}

function fmtWindow(eventItem) {
  if (!eventItem?.start_time || !eventItem?.end_time) return 'N/A';
  return `${fmtDateTime(eventItem.start_time)} - ${fmtDateTime(eventItem.end_time)}`;
}

export default function EventManagement() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [scheduledEvents, setScheduledEvents] = useState([]);
  const [activeEvents, setActiveEvents] = useState([]);
  const [completedEvents, setCompletedEvents] = useState([]);
  const [busyDeleteId, setBusyDeleteId] = useState('');
  const [busyDownloadId, setBusyDownloadId] = useState('');
  const [completedSearch, setCompletedSearch] = useState('');

  const fetchManagement = useCallback(async () => {
    try {
      const res = await getEventManagement();
      const data = res?.data || {};
      setScheduledEvents(Array.isArray(data.scheduled_events) ? data.scheduled_events : []);
      setActiveEvents(Array.isArray(data.active_events) ? data.active_events : []);
      setCompletedEvents(Array.isArray(data.completed_events) ? data.completed_events : []);
      setError('');
    } catch (err) {
      setError(err?.response?.data?.error || 'Failed to load event management data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchManagement();
  }, [fetchManagement]);

  useEffect(() => {
    const timer = setInterval(fetchManagement, 7000);
    return () => clearInterval(timer);
  }, [fetchManagement]);

  const schedulingLocked = useMemo(() => activeEvents.length > 0, [activeEvents.length]);
  const filteredCompletedEvents = useMemo(() => {
    const query = String(completedSearch || '').trim().toLowerCase();
    if (!query) {
      return completedEvents;
    }
    return completedEvents.filter((item) => {
      const eventName = String(item?.event_name || '').toLowerCase();
      const eventId = String(item?.event_id || '').toLowerCase();
      const cameraId = String(item?.selected_camera_id || '').toLowerCase();
      return eventName.includes(query) || eventId.includes(query) || cameraId.includes(query);
    });
  }, [completedEvents, completedSearch]);

  const handleDeleteScheduled = async (eventId) => {
    if (!eventId) return;
    const confirmed = window.confirm('Delete this scheduled event?');
    if (!confirmed) return;

    try {
      setBusyDeleteId(eventId);
      setError('');
      await deleteScheduledEvent(eventId);
      await fetchManagement();
    } catch (err) {
      setError(err?.response?.data?.error || 'Unable to delete scheduled event');
    } finally {
      setBusyDeleteId('');
    }
  };

  const handleDownloadExcel = async (eventItem) => {
    const eventId = eventItem?.event_id;
    if (!eventId) return;

    try {
      setBusyDownloadId(eventId);
      setError('');
      const res = await downloadCompletedEventExcel(eventId);
      const blob = new Blob(
        [res.data],
        { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
      );
      const safeName = String(eventItem.event_name || 'event').trim().replace(/\s+/g, '_');
      const href = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = href;
      link.download = `${safeName}_${eventId}_results.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(href);
    } catch (err) {
      setError(err?.response?.data?.error || 'Unable to download Excel for completed event');
    } finally {
      setBusyDownloadId('');
    }
  };

  if (loading) {
    return <div className="p-6">Loading event management...</div>;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Event Management</h1>
      {error && <div className="text-red-600 text-sm">{error}</div>}

      <Card title="Scheduled Events">
        {schedulingLocked && (
          <div className="text-amber-600 text-sm mb-3">
            Scheduling is locked while an event is active.
          </div>
        )}
        {scheduledEvents.length === 0 ? (
          <div className="text-sm text-gray-600">No scheduled events.</div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Window</th>
                  <th>Camera</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {scheduledEvents.map((eventItem) => (
                  <tr key={eventItem.event_id}>
                    <td>{eventItem.event_name || 'Untitled Event'}</td>
                    <td>{fmtWindow(eventItem)}</td>
                    <td>{eventItem.selected_camera_id || 'N/A'}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-danger-outline"
                        onClick={() => handleDeleteScheduled(eventItem.event_id)}
                        disabled={busyDeleteId === eventItem.event_id}
                      >
                        {busyDeleteId === eventItem.event_id ? 'Deleting...' : 'Delete'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Active Events">
        {activeEvents.length === 0 ? (
          <div className="text-sm text-gray-600">No active event.</div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Window</th>
                  <th>Camera</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {activeEvents.map((eventItem) => (
                  <tr key={eventItem.event_id}>
                    <td>{eventItem.event_name || 'Untitled Event'}</td>
                    <td>{fmtWindow(eventItem)}</td>
                    <td>{eventItem.selected_camera_id || 'N/A'}</td>
                    <td><span className="badge badge-green">Active</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Completed Events">
        <div className="mb-3">
          <input
            type="text"
            className="input"
            placeholder="Search completed event by name, event ID, or camera ID"
            value={completedSearch}
            onChange={(e) => setCompletedSearch(e.target.value)}
          />
        </div>
        {completedEvents.length === 0 ? (
          <div className="text-sm text-gray-600">No completed events yet.</div>
        ) : filteredCompletedEvents.length === 0 ? (
          <div className="text-sm text-gray-600">No completed events match your search.</div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Window</th>
                  <th>Completed At</th>
                  <th>Excel</th>
                </tr>
              </thead>
              <tbody>
                {filteredCompletedEvents.map((eventItem) => (
                  <tr key={eventItem.event_id}>
                    <td>{eventItem.event_name || 'Untitled Event'}</td>
                    <td>{fmtWindow(eventItem)}</td>
                    <td>{fmtDateTime(eventItem.completed_at || eventItem.end_time)}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => handleDownloadExcel(eventItem)}
                        disabled={busyDownloadId === eventItem.event_id}
                      >
                        {busyDownloadId === eventItem.event_id ? 'Preparing...' : 'Download Excel'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
