import api from './api';

export const getCurrentEvent = async () => api.get('/events/current');

export const scheduleEvent = async (payload) => api.post('/events/schedule', payload);

export const startEvent = async () => api.post('/events/start');

export const stopEvent = async () => api.post('/events/stop');
