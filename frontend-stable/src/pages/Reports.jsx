import { useEffect, useState } from 'react';
import { generateReport, getEventsOnDate } from '../services/reportService';
import Card from '../components/Card';

export default function Reports() {
  const [form, setForm] = useState({
    date: new Date().toISOString().split('T')[0],
    event_id: '',
    event_name: '',
    report_type: 'daily',
  });
  const [events, setEvents] = useState([]);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [eventsError, setEventsError] = useState('');

  useEffect(() => {
    let cancelled = false;

    const loadEvents = async () => {
      setEventsLoading(true);
      setEventsError('');
      try {
        const res = await getEventsOnDate(form.date);
        if (cancelled) return;
        const nextEvents = res?.data?.events || [];
        setEvents(nextEvents);
        setForm((prev) => {
          const stillExists = nextEvents.some((item) => item.event_id === prev.event_id);
          if (stillExists) return prev;
          return {
            ...prev,
            event_id: '',
            event_name: '',
          };
        });
      } catch (err) {
        if (cancelled) return;
        setEvents([]);
        setForm((prev) => ({ ...prev, event_id: '', event_name: '' }));
        setEventsError('Failed to load events for selected date');
      } finally {
        if (!cancelled) {
          setEventsLoading(false);
        }
      }
    };

    loadEvents();
    return () => {
      cancelled = true;
    };
  }, [form.date]);

  const handleGenerate = async () => {
    if (!form.event_id) {
      alert('Please select an event name for the selected date.');
      return;
    }
    try {
      const response = await generateReport({
        start_date: form.date,
        end_date: form.date,
        report_type: form.report_type,
        event_id: form.event_id,
        event_name: form.event_name,
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${form.event_name || 'visitor'}_report.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      let message = 'Error generating report';
      try {
        const raw = await err?.response?.data?.text?.();
        if (raw) {
          const parsed = JSON.parse(raw);
          message = parsed?.error || message;
        }
      } catch (_) {
        // Keep default fallback message.
      }
      alert(message);
    }
  };

  return (
    <div className="space-y-6 max-w-lg">
      <h1 className="text-2xl font-bold">Generate Reports</h1>
      <Card>
        <div className="space-y-4">
          <div>
            <label className="block text-sm mb-1">Date</label>
            <input type="date" className="input"
              value={form.date}
              onChange={e => setForm({ ...form, date: e.target.value })} />
          </div>
          <div>
            <label className="block text-sm mb-1">Event Name</label>
            <select
              className="input"
              value={form.event_id}
              onChange={(e) => {
                const selected = events.find((item) => item.event_id === e.target.value);
                setForm({
                  ...form,
                  event_id: e.target.value,
                  event_name: selected?.event_name || '',
                });
              }}
              disabled={eventsLoading}
            >
              <option value="">{eventsLoading ? 'Loading events...' : 'Select event'}</option>
              {events.map((eventItem) => (
                <option key={eventItem.event_id} value={eventItem.event_id}>
                  {eventItem.label}
                </option>
              ))}
            </select>
            {eventsError && <div className="text-red-600 text-sm mt-1">{eventsError}</div>}
            {!eventsLoading && !eventsError && events.length === 0 && (
              <div className="text-sm mt-1">No events found on this date.</div>
            )}
          </div>
          <div>
            <label className="block text-sm mb-1">Type</label>
            <select className="input"
              value={form.report_type}
              onChange={e => setForm({...form, report_type: e.target.value})}>
              <option value="daily">Daily Summary</option>
              <option value="weekly">Weekly Summary</option>
            </select>
          </div>
          <button onClick={handleGenerate} className="btn btn-primary w-full">Download PDF</button>
        </div>
      </Card>
    </div>
  );
}
