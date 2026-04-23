import { useCallback, useEffect, useMemo, useState } from 'react';
import Card from '../components/Card';
import {
  deleteScheduledEvent,
  downloadCompletedEventExcel,
  finalizeAndDeleteCompletedEventData,
  finalizeCompletedEvent,
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
  const [busyFinalizeKey, setBusyFinalizeKey] = useState('');
  const [completedSearch, setCompletedSearch] = useState('');
  const [notice, setNotice] = useState('');

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

  const handleFinalizeEvent = async (eventItem, deleteTempData = false) => {
    const eventId = eventItem?.event_id;
    if (!eventId) return;

    if (deleteTempData) {
      const confirmed = window.confirm(
        'Finalize this event and delete temporary captured embeddings/images for this event?',
      );
      if (!confirmed) return;
    }

    const busyKey = `${eventId}:${deleteTempData ? 'delete' : 'finalize'}`;
    try {
      setBusyFinalizeKey(busyKey);
      setNotice('');
      setError('');
      const res = deleteTempData
        ? await finalizeAndDeleteCompletedEventData(eventId)
        : await finalizeCompletedEvent(eventId);
      const summary = res?.data?.summary || {};
      const message = res?.data?.message || 'Event finalized.';
      const eventTitle = eventItem?.event_name || eventId;
      const captureCount = Number(summary?.captured_faces || 0);
      const clusterCount = Number(summary?.visitor_clusters || 0);
      const staffCount = Number(summary?.staff_matches || 0);
      setNotice(
        `${eventTitle}: ${message} Captures: ${captureCount}, Visitors: ${clusterCount}, Staff filtered: ${staffCount}.`,
      );
      await fetchManagement();
    } catch (err) {
      setError(err?.response?.data?.error || 'Unable to finalize completed event');
    } finally {
      setBusyFinalizeKey('');
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
      {notice && <div className="text-green-600 text-sm">{notice}</div>}

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
                  <th>Finalization</th>
                  <th>Actions</th>
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
                      {eventItem.finalized_at ? (
                        <div className="flex flex-col gap-1">
                          <span className="badge badge-green">Finalized</span>
                          <span className="text-xs text-gray-500">
                            {fmtDateTime(eventItem.finalized_at)}
                          </span>
                          {eventItem.temp_data_deleted && (
                            <span className="text-xs text-gray-500">Temp data deleted</span>
                          )}
                        </div>
                      ) : (
                        <span className="badge">Pending</span>
                      )}
                    </td>
                    <td>
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          className="btn btn-secondary"
                          onClick={() => handleFinalizeEvent(eventItem, false)}
                          disabled={
                            !!eventItem.finalized_at ||
                            busyFinalizeKey === `${eventItem.event_id}:finalize` ||
                            busyFinalizeKey === `${eventItem.event_id}:delete`
                          }
                        >
                          {busyFinalizeKey === `${eventItem.event_id}:finalize` ? 'Finalizing...' : 'Finalize'}
                        </button>
                        <button
                          type="button"
                          className="btn btn-danger-outline"
                          onClick={() => handleFinalizeEvent(eventItem, true)}
                          disabled={
                            !!eventItem.temp_data_deleted ||
                            busyFinalizeKey === `${eventItem.event_id}:finalize` ||
                            busyFinalizeKey === `${eventItem.event_id}:delete`
                          }
                        >
                          {busyFinalizeKey === `${eventItem.event_id}:delete`
                            ? 'Finalizing...'
                            : 'Finalize & Delete'}
                        </button>
                      </div>
                    </td>
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
