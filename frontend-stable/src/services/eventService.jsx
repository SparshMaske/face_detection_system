import api from './api';

export const getCurrentEvent = async () => api.get('/events/current');

export const scheduleEvent = async (payload) => api.post('/events/schedule', payload);

export const startEvent = async (eventId) =>
  api.post('/events/start', eventId ? { event_id: eventId } : {});

export const stopEvent = async (eventId) =>
  api.post('/events/stop', eventId ? { event_id: eventId } : {});

export const getEventManagement = async () => api.get('/events/management');

export const deleteScheduledEvent = async (eventId) =>
  api.delete(`/events/scheduled/${encodeURIComponent(eventId)}`);

export const downloadCompletedEventExcel = async (eventId) =>
  api.get(`/events/completed/${encodeURIComponent(eventId)}/export-excel`, {
    responseType: 'blob',
  });

export const finalizeCompletedEvent = async (eventId) =>
  api.post(`/events/completed/${encodeURIComponent(eventId)}/finalize`);

export const finalizeAndDeleteCompletedEventData = async (eventId) =>
  api.post(`/events/completed/${encodeURIComponent(eventId)}/finalize-delete`);

export const getCompletedEventTempStatus = async (eventId) =>
  api.get(`/events/completed/${encodeURIComponent(eventId)}/temp-status`);
