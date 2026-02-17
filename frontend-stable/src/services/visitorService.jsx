import api from './api';

export const getVisitors = async (params = {}) => api.get('/visitors/', { params });

export const checkIn = async (data) => api.post('/visitors/check-in', data);

export const checkOut = async (id) => api.post(`/visitors/${id}/check-out`, {});
