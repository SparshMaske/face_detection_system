import api from './api';

export const getSettings = async () => {
  return api.get('/settings/');
};

export const updateSettings = async (data) => {
  return api.post('/settings/', data);
};
