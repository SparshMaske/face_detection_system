import api from './api';

export const getStaff = async () => {
  return api.get('/staff/');
};

export const createStaff = async (data) => {
  return api.post('/staff/', data, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

export const deleteStaff = async (id) => {
  return api.delete(`/staff/${id}`);
};
