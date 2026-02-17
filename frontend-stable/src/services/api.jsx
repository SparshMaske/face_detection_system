import axios from 'axios';
import authService from './authService';
import API_BASE_URL from './config';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

const isAuthFailure = (error) => {
  const status = error?.response?.status;
  if (status === 401) return true;
  if (status !== 422) return false;
  const payload = error?.response?.data;
  const msg = String(payload?.msg || payload?.error || '').toLowerCase();
  return msg.includes('token') || msg.includes('jwt') || msg.includes('subject');
};

// Add JWT token to every request
api.interceptors.request.use(
  (config) => {
    const token = authService.getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // Let the browser set multipart boundaries automatically.
    if (config.data instanceof FormData) {
      delete config.headers['Content-Type'];
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Handle 401 errors globally
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (!isAuthFailure(error)) {
      return Promise.reject(error);
    }

    const originalRequest = error.config || {};
    if (originalRequest._retry) {
      authService.logout();
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
      return Promise.reject(error);
    }

    originalRequest._retry = true;
    const refreshedToken = await authService.refreshAccessToken();
    if (refreshedToken) {
      originalRequest.headers = originalRequest.headers || {};
      originalRequest.headers.Authorization = `Bearer ${refreshedToken}`;
      return api(originalRequest);
    }

    authService.logout();
    if (window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
