import api from './api';

export const generateReport = (data) => api.post('/reports/generate', data, {
  responseType: 'blob' // Important for file download
});

export const listReports = () => api.get('/reports/list');