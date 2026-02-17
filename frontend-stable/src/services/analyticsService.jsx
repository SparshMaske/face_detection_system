import api from './api';

export const getFootfallTrends = async (days = 7) =>
  api.get('/analytics/footfall-trends', { params: { days } });

export const getPeakHours = async (days = 7) =>
  api.get('/analytics/peak-hours', { params: { days } });

export const getAverageDuration = async () => api.get('/analytics/average-duration');

export const getSummary = async (days = 30) =>
  api.get('/analytics/summary', { params: { days } });
