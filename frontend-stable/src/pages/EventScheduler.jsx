import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Card from '../components/Card';
import api from '../services/api';
import { getCurrentEvent, scheduleEvent, startEvent, stopEvent } from '../services/eventService';

function toDateTimeLocal(value) {
  if (!value) return '';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return '';
  const yyyy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, '0');
  const dd = String(dt.getDate()).padStart(2, '0');
  const hh = String(dt.getHours()).padStart(2, '0');
  const mi = String(dt.getMinutes()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}`;
}

function defaultStart() {
  const now = new Date();
  now.setMinutes(now.getMinutes() + 1);
  now.setSeconds(0, 0);
  return toDateTimeLocal(now.toISOString());
}

function defaultEnd() {
  const end = new Date();
  end.setHours(end.getHours() + 1);
  end.setSeconds(0, 0);
  return toDateTimeLocal(end.toISOString());
}

export default function EventScheduler() {
  const navigate = useNavigate();
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [eventState, setEventState] = useState(null);
  const [form, setForm] = useState({
    event_name: '',
    start_time: defaultStart(),
    end_time: defaultEnd(),
    camera_mode: 'default',
    rtsp_url: '',
    camera_id: '',
  });

  const activeStatus = eventState?.status || 'idle';
  const canStartNow = activeStatus === 'scheduled' || activeStatus === 'idle';

  useEffect(() => {
    let mounted = true;
    const bootstrap = async () => {
      try {
        setError('');
        const [cameraRes, eventRes] = await Promise.allSettled([
          api.get('/camera/'),
          getCurrentEvent(),
        ]);
        if (!mounted) return;
        const list = cameraRes.status === 'fulfilled' && Array.isArray(cameraRes.value?.data)
          ? cameraRes.value.data
          : [];
        setCameras(list);
        const currentEvent = eventRes.status === 'fulfilled' ? (eventRes.value?.data || null) : null;
        setEventState(currentEvent);

        if (currentEvent?.event_name) {
          setForm((prev) => ({
            ...prev,
            event_name: currentEvent.event_name || prev.event_name,
            start_time: toDateTimeLocal(currentEvent.start_time) || prev.start_time,
            end_time: toDateTimeLocal(currentEvent.end_time) || prev.end_time,
            camera_mode: currentEvent.camera_mode || prev.camera_mode,
            camera_id: currentEvent.selected_camera_id || prev.camera_id,
            rtsp_url: currentEvent.rtsp_url || prev.rtsp_url,
          }));
        } else if (list.length > 0) {
          setForm((prev) => ({ ...prev, camera_id: prev.camera_id || list[0].camera_id }));
        }

        const errorMessages = [];
        if (cameraRes.status === 'rejected') {
          errorMessages.push('camera list');
        }
        if (eventRes.status === 'rejected') {
          errorMessages.push('event status');
        }
        if (errorMessages.length > 0) {
          setError(`Failed to load ${errorMessages.join(' and ')}. Check backend/API token.`);
        }
      } catch (err) {
        if (!mounted) return;
        setError('Failed to initialize event scheduler.');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    bootstrap();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        const res = await getCurrentEvent();
        const data = res.data || {};
        setEventState(data);
        if (data.status === 'active') {
          navigate('/live', { replace: true });
        }
      } catch (_) {
        // Keep polling silent to avoid disruptive alerts.
      }
    }, 5000);
    return () => clearInterval(timer);
  }, [navigate]);

  const eventWindowLabel = useMemo(() => {
    if (!eventState?.start_time || !eventState?.end_time) return '';
    const start = new Date(eventState.start_time).toLocaleString();
    const end = new Date(eventState.end_time).toLocaleString();
    return `${start} - ${end}`;
  }, [eventState]);

  const handleChange = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      setSaving(true);
      setError('');
      const payload = {
        event_name: form.event_name.trim(),
        start_time: form.start_time,
        end_time: form.end_time,
        camera_mode: form.camera_mode,
      };
      if (form.camera_mode === 'rtsp') payload.rtsp_url = form.rtsp_url.trim();
      if (form.camera_mode === 'existing') payload.camera_id = form.camera_id;
      const res = await scheduleEvent(payload);
      setEventState(res.data || null);
      if (res.data?.status === 'active') navigate('/live', { replace: true });
    } catch (err) {
      setError(err?.response?.data?.error || 'Failed to schedule event');
    } finally {
      setSaving(false);
    }
  };

  const handleStartNow = async () => {
    try {
      setError('');
      const res = await startEvent();
      setEventState(res.data || null);
      navigate('/live', { replace: true });
    } catch (err) {
      setError(err?.response?.data?.error || 'Unable to start event');
    }
  };

  const handleStop = async () => {
    try {
      setError('');
      const res = await stopEvent();
      setEventState(res.data || null);
    } catch (err) {
      setError(err?.response?.data?.error || 'Unable to stop event');
    }
  };

  if (loading) return <div className="p-6">Loading event scheduler...</div>;

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-bold">Event Scheduler</h1>
      <Card title="Schedule Event">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Event Name</label>
            <input
              className="input"
              placeholder="e.g. Annual Meeting Security"
              value={form.event_name}
              onChange={(e) => handleChange('event_name', e.target.value)}
              required
            />
          </div>

          <div className="flex gap-4">
            <div className="w-full">
              <label className="block text-sm font-medium mb-1">Start Time</label>
              <input
                type="datetime-local"
                className="input"
                value={form.start_time}
                onChange={(e) => handleChange('start_time', e.target.value)}
                required
              />
            </div>
            <div className="w-full">
              <label className="block text-sm font-medium mb-1">End Time</label>
              <input
                type="datetime-local"
                className="input"
                value={form.end_time}
                onChange={(e) => handleChange('end_time', e.target.value)}
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Camera Source</label>
            <div className="space-y-2">
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  name="camera_mode"
                  checked={form.camera_mode === 'default'}
                  onChange={() => handleChange('camera_mode', 'default')}
                />
                <span>Default Device Camera</span>
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  name="camera_mode"
                  checked={form.camera_mode === 'rtsp'}
                  onChange={() => handleChange('camera_mode', 'rtsp')}
                />
                <span>RTSP URL</span>
              </label>
              {form.camera_mode === 'rtsp' && (
                <input
                  className="input"
                  placeholder="rtsp://username:password@ip:port/path"
                  value={form.rtsp_url}
                  onChange={(e) => handleChange('rtsp_url', e.target.value)}
                  required
                />
              )}
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  name="camera_mode"
                  checked={form.camera_mode === 'existing'}
                  onChange={() => handleChange('camera_mode', 'existing')}
                />
                <span>Existing Camera</span>
              </label>
              {form.camera_mode === 'existing' && (
                <select
                  className="input"
                  value={form.camera_id}
                  onChange={(e) => handleChange('camera_id', e.target.value)}
                  required
                >
                  {cameras.length === 0 && <option value="">No cameras found</option>}
                  {cameras.map((cam) => (
                    <option key={cam.id} value={cam.camera_id}>
                      {cam.name} ({cam.camera_id})
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>

          {error && <div className="text-red-600 text-sm">{error}</div>}

          <div className="flex gap-2">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Scheduling...' : 'Save Event'}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleStartNow}
              disabled={!canStartNow}
            >
              Start Now
            </button>
            <button type="button" className="btn btn-danger" onClick={handleStop}>
              Stop Event
            </button>
          </div>
        </form>
      </Card>

      <Card title="Current Event State">
        <div className="space-y-2 text-sm">
          <div><strong>Status:</strong> {activeStatus}</div>
          <div><strong>Event:</strong> {eventState?.event_name || 'N/A'}</div>
          <div><strong>Window:</strong> {eventWindowLabel || 'N/A'}</div>
          <div><strong>Camera Mode:</strong> {eventState?.camera_mode || 'N/A'}</div>
          <div><strong>Selected Camera:</strong> {eventState?.selected_camera_id || 'N/A'}</div>
          <div><strong>Workflow Active:</strong> {eventState?.workflow_active ? 'Yes' : 'No'}</div>
        </div>
      </Card>
    </div>
  );
}
