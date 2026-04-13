import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Card from '../components/Card';
import api from '../services/api';
import { getCurrentEvent, scheduleEvent, startEvent, stopEvent } from '../services/eventService';
import {
  formatDateTime12h,
  localDateInputValue,
  localTimeInputValue,
  toDateTimeLocalInput,
} from '../utils/formatters';

const DAY_OPTIONS = [
  { value: 0, label: 'Sun' },
  { value: 1, label: 'Mon' },
  { value: 2, label: 'Tue' },
  { value: 3, label: 'Wed' },
  { value: 4, label: 'Thu' },
  { value: 5, label: 'Fri' },
  { value: 6, label: 'Sat' },
];

const HOUR_12_OPTIONS = Array.from({ length: 12 }, (_, index) => String(index + 1).padStart(2, '0'));
const MINUTE_OPTIONS = Array.from({ length: 60 }, (_, index) => String(index).padStart(2, '0'));

function splitDateTime12(value) {
  const fallback = toDateTimeLocalInput(new Date());
  const normalized = String(value || fallback);
  const [datePartRaw, timePartRaw] = normalized.split('T');
  const datePart = datePartRaw || localDateInputValue(new Date());
  const [hourPart = '00', minutePart = '00'] = String(timePartRaw || '00:00').split(':');

  let hour24 = Number.parseInt(hourPart, 10);
  let minute = Number.parseInt(minutePart, 10);
  if (Number.isNaN(hour24)) hour24 = 0;
  if (Number.isNaN(minute)) minute = 0;
  hour24 = Math.min(23, Math.max(0, hour24));
  minute = Math.min(59, Math.max(0, minute));

  return {
    date: datePart,
    hour12: String(hour24 % 12 || 12).padStart(2, '0'),
    minute: String(minute).padStart(2, '0'),
    meridiem: hour24 >= 12 ? 'PM' : 'AM',
  };
}

function composeDateTime12(parts) {
  const datePart = String(parts?.date || localDateInputValue(new Date()));
  let hour12 = Number.parseInt(String(parts?.hour12 || '12'), 10);
  let minute = Number.parseInt(String(parts?.minute || '00'), 10);
  const meridiem = String(parts?.meridiem || 'AM').toUpperCase() === 'PM' ? 'PM' : 'AM';

  if (Number.isNaN(hour12) || hour12 < 1) hour12 = 12;
  if (hour12 > 12) hour12 = 12;
  if (Number.isNaN(minute) || minute < 0) minute = 0;
  if (minute > 59) minute = 59;

  let hour24 = hour12 % 12;
  if (meridiem === 'PM') hour24 += 12;

  return `${datePart}T${String(hour24).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

function splitTime12(value) {
  const normalized = String(value || '00:00');
  const [hourPart = '00', minutePart = '00'] = normalized.split(':');

  let hour24 = Number.parseInt(hourPart, 10);
  let minute = Number.parseInt(minutePart, 10);
  if (Number.isNaN(hour24)) hour24 = 0;
  if (Number.isNaN(minute)) minute = 0;
  hour24 = Math.min(23, Math.max(0, hour24));
  minute = Math.min(59, Math.max(0, minute));

  return {
    hour12: String(hour24 % 12 || 12).padStart(2, '0'),
    minute: String(minute).padStart(2, '0'),
    meridiem: hour24 >= 12 ? 'PM' : 'AM',
  };
}

function composeTime12(parts) {
  let hour12 = Number.parseInt(String(parts?.hour12 || '12'), 10);
  let minute = Number.parseInt(String(parts?.minute || '00'), 10);
  const meridiem = String(parts?.meridiem || 'AM').toUpperCase() === 'PM' ? 'PM' : 'AM';

  if (Number.isNaN(hour12) || hour12 < 1) hour12 = 12;
  if (hour12 > 12) hour12 = 12;
  if (Number.isNaN(minute) || minute < 0) minute = 0;
  if (minute > 59) minute = 59;

  let hour24 = hour12 % 12;
  if (meridiem === 'PM') hour24 += 12;

  return `${String(hour24).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

function DateTime12Field({ value, onChange, required = false }) {
  const parts = splitDateTime12(value);
  const update = (patch) => onChange(composeDateTime12({ ...parts, ...patch }));

  return (
    <div className="event-grid-three">
      <input
        type="date"
        className="input"
        value={parts.date}
        onChange={(e) => update({ date: e.target.value })}
        required={required}
      />
      <select
        className="input"
        value={parts.hour12}
        onChange={(e) => update({ hour12: e.target.value })}
      >
        {HOUR_12_OPTIONS.map((hour) => (
          <option key={hour} value={hour}>{hour}</option>
        ))}
      </select>
      <div className="event-grid-two">
        <select
          className="input"
          value={parts.minute}
          onChange={(e) => update({ minute: e.target.value })}
        >
          {MINUTE_OPTIONS.map((minute) => (
            <option key={minute} value={minute}>{minute}</option>
          ))}
        </select>
        <select
          className="input"
          value={parts.meridiem}
          onChange={(e) => update({ meridiem: e.target.value })}
        >
          <option value="AM">AM</option>
          <option value="PM">PM</option>
        </select>
      </div>
    </div>
  );
}

function Time12Field({ value, onChange, required = false }) {
  const parts = splitTime12(value);
  const update = (patch) => onChange(composeTime12({ ...parts, ...patch }));

  return (
    <div className="event-grid-three">
      <select
        className="input"
        value={parts.hour12}
        onChange={(e) => update({ hour12: e.target.value })}
        required={required}
      >
        {HOUR_12_OPTIONS.map((hour) => (
          <option key={hour} value={hour}>{hour}</option>
        ))}
      </select>
      <select
        className="input"
        value={parts.minute}
        onChange={(e) => update({ minute: e.target.value })}
        required={required}
      >
        {MINUTE_OPTIONS.map((minute) => (
          <option key={minute} value={minute}>{minute}</option>
        ))}
      </select>
      <select
        className="input"
        value={parts.meridiem}
        onChange={(e) => update({ meridiem: e.target.value })}
      >
        <option value="AM">AM</option>
        <option value="PM">PM</option>
      </select>
    </div>
  );
}

function defaultStart() {
  const now = new Date();
  now.setMinutes(now.getMinutes() + 1);
  now.setSeconds(0, 0);
  return toDateTimeLocalInput(now);
}

function defaultEnd() {
  const end = new Date();
  end.setHours(end.getHours() + 1);
  end.setSeconds(0, 0);
  return toDateTimeLocalInput(end);
}

function defaultRangeStart() {
  return localDateInputValue(new Date());
}

function defaultRangeEnd() {
  const end = new Date();
  end.setDate(end.getDate() + 9);
  return localDateInputValue(end);
}

function defaultDayStart() {
  const now = new Date();
  now.setHours(9, 0, 0, 0);
  return localTimeInputValue(now);
}

function defaultDayEnd() {
  const now = new Date();
  now.setHours(18, 0, 0, 0);
  return localTimeInputValue(now);
}

export default function EventScheduler() {
  const navigate = useNavigate();
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [eventState, setEventState] = useState(null);
  const [form, setForm] = useState({
    event_name: '',
    schedule_mode: 'single',
    start_time: defaultStart(),
    end_time: defaultEnd(),
    range_start_date: defaultRangeStart(),
    range_end_date: defaultRangeEnd(),
    day_start_time: defaultDayStart(),
    day_end_time: defaultDayEnd(),
    day_selection: 'weekdays',
    custom_days: [1, 2, 3, 4, 5],
    repeat_every_days: 1,
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
        setNotice('');
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
            schedule_mode: 'single',
            start_time: toDateTimeLocalInput(currentEvent.start_time) || prev.start_time,
            end_time: toDateTimeLocalInput(currentEvent.end_time) || prev.end_time,
            camera_mode: currentEvent.camera_mode || prev.camera_mode,
            camera_id: currentEvent.selected_camera_id || prev.camera_id,
            rtsp_url: currentEvent.rtsp_url || prev.rtsp_url,
          }));
        } else if (list.length > 0) {
          setForm((prev) => ({ ...prev, camera_id: prev.camera_id || list[0].camera_id }));
        }

        const errorMessages = [];
        if (cameraRes.status === 'rejected') errorMessages.push('camera list');
        if (eventRes.status === 'rejected') errorMessages.push('event status');
        if (errorMessages.length > 0) {
          setError(`Failed to load ${errorMessages.join(' and ')}. Check backend/API token.`);
        }
      } catch (_) {
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
        if (data.status === 'active') navigate('/live', { replace: true });
      } catch (_) {
        // silent poll
      }
    }, 5000);
    return () => clearInterval(timer);
  }, [navigate]);

  const eventWindowLabel = useMemo(() => {
    if (!eventState?.start_time || !eventState?.end_time) return '';
    return `${formatDateTime12h(eventState.start_time)} - ${formatDateTime12h(eventState.end_time)}`;
  }, [eventState]);

  const handleChange = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const toggleCustomDay = (dayValue) => {
    setForm((prev) => {
      const current = new Set(prev.custom_days || []);
      if (current.has(dayValue)) current.delete(dayValue);
      else current.add(dayValue);
      return { ...prev, custom_days: Array.from(current).sort((a, b) => a - b) };
    });
  };

  const getSelectedDays = () => {
    const daySelection = form.day_selection;
    if (daySelection === 'everyday') return [0, 1, 2, 3, 4, 5, 6];
    if (daySelection === 'weekdays') return [1, 2, 3, 4, 5];
    if (daySelection === 'weekends') return [0, 6];
    return (form.custom_days || []).slice().sort((a, b) => a - b);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      setSaving(true);
      setError('');
      setNotice('');

      const tzName = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
      const tzOffsetMin = new Date().getTimezoneOffset();
      const payload = {
        event_name: form.event_name.trim(),
        camera_mode: form.camera_mode,
        schedule_mode: form.schedule_mode,
        client_tz_offset_minutes: tzOffsetMin,
        client_timezone: tzName,
        client_now_iso: new Date().toISOString(),
      };

      if (form.schedule_mode === 'single') {
        payload.start_time = form.start_time;
        payload.end_time = form.end_time;
      } else {
        const selectedDays = getSelectedDays();
        payload.range_start_date = form.range_start_date;
        payload.range_end_date = form.range_end_date;
        payload.day_start_time = form.day_start_time;
        payload.day_end_time = form.day_end_time;
        payload.days_of_week = selectedDays;
        payload.repeat_every_days = Number(form.repeat_every_days || 1);
      }

      if (form.camera_mode === 'rtsp') payload.rtsp_url = form.rtsp_url.trim();
      if (form.camera_mode === 'existing') payload.camera_id = form.camera_id;

      const res = await scheduleEvent(payload);
      setEventState(res.data || null);
      if (res.data?.status === 'active') navigate('/live', { replace: true });
      if (res?.data?.created_count > 1) {
        setNotice(`Scheduled ${res.data.created_count} event windows successfully.`);
      }
    } catch (err) {
      setError(err?.response?.data?.error || 'Failed to schedule event');
    } finally {
      setSaving(false);
    }
  };

  const handleStartNow = async () => {
    try {
      setError('');
      setNotice('');
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
      setNotice('');
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

          <div>
            <label className="block text-sm font-medium mb-2">Schedule Pattern</label>
            <select
              className="input"
              value={form.schedule_mode}
              onChange={(e) => handleChange('schedule_mode', e.target.value)}
            >
              <option value="single">One-Time Event</option>
              <option value="daytime_window">Date Range + Daytime Window</option>
            </select>
          </div>

          {form.schedule_mode === 'single' ? (
            <div className="event-grid-two">
              <div className="w-full">
                <label className="block text-sm font-medium mb-1">Start Time</label>
                <DateTime12Field
                  value={form.start_time}
                  onChange={(nextValue) => handleChange('start_time', nextValue)}
                  required
                />
              </div>
              <div className="w-full">
                <label className="block text-sm font-medium mb-1">End Time</label>
                <DateTime12Field
                  value={form.end_time}
                  onChange={(nextValue) => handleChange('end_time', nextValue)}
                  required
                />
              </div>
            </div>
          ) : (
            <div className="space-y-4 rounded-lg border border-[var(--border)] p-3">
              <div className="event-grid-two">
                <div>
                  <label className="block text-sm font-medium mb-1">Range Start Date</label>
                  <input
                    type="date"
                    className="input"
                    value={form.range_start_date}
                    onChange={(e) => handleChange('range_start_date', e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Range End Date</label>
                  <input
                    type="date"
                    className="input"
                    value={form.range_end_date}
                    onChange={(e) => handleChange('range_end_date', e.target.value)}
                    required
                  />
                </div>
              </div>
              <div className="event-grid-two">
                <div>
                  <label className="block text-sm font-medium mb-1">Daily Start Time</label>
                  <Time12Field
                    value={form.day_start_time}
                    onChange={(nextValue) => handleChange('day_start_time', nextValue)}
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Daily End Time</label>
                  <Time12Field
                    value={form.day_end_time}
                    onChange={(nextValue) => handleChange('day_end_time', nextValue)}
                    required
                  />
                </div>
              </div>
              <div className="event-grid-two">
                <div>
                  <label className="block text-sm font-medium mb-1">Day Filter</label>
                  <select
                    className="input"
                    value={form.day_selection}
                    onChange={(e) => handleChange('day_selection', e.target.value)}
                  >
                    <option value="everyday">Every day</option>
                    <option value="weekdays">Weekdays</option>
                    <option value="weekends">Weekends</option>
                    <option value="custom">Custom</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Repeat Every (days)</label>
                  <input
                    type="number"
                    min="1"
                    max="30"
                    className="input"
                    value={form.repeat_every_days}
                    onChange={(e) => handleChange('repeat_every_days', e.target.value)}
                  />
                </div>
              </div>
              {form.day_selection === 'custom' && (
                <div>
                  <label className="block text-sm font-medium mb-1">Custom Days</label>
                  <div className="flex flex-wrap gap-3">
                    {DAY_OPTIONS.map((opt) => (
                      <label key={opt.value} className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={(form.custom_days || []).includes(opt.value)}
                          onChange={() => toggleCustomDay(opt.value)}
                        />
                        <span>{opt.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

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
                <span>Default Camera (Auto Raspberry/Existing camera, fallback device camera)</span>
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
          {!error && notice && <div className="text-green-600 text-sm">{notice}</div>}

          <div className="event-actions">
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
