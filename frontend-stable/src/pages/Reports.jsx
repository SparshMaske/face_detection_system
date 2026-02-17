import { useState } from 'react';
import { generateReport } from '../services/reportService';
import Card from '../components/Card';

export default function Reports() {
  const [dates, setDates] = useState({
    start_date: new Date().toISOString().split('T')[0],
    end_date: new Date().toISOString().split('T')[0],
    report_type: 'daily'
  });

  const handleGenerate = async () => {
    try {
      const response = await generateReport(dates);
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'visitor_report.pdf');
      document.body.appendChild(link);
      link.click();
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
            <label className="block text-sm mb-1">Start Date</label>
            <input type="date" className="input"
              value={dates.start_date} onChange={e => setDates({...dates, start_date: e.target.value})} />
          </div>
          <div>
            <label className="block text-sm mb-1">End Date</label>
            <input type="date" className="input"
              value={dates.end_date} onChange={e => setDates({...dates, end_date: e.target.value})} />
          </div>
          <div>
            <label className="block text-sm mb-1">Type</label>
            <select className="input"
              value={dates.report_type} onChange={e => setDates({...dates, report_type: e.target.value})}>
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
