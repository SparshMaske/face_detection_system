import axios from 'axios';
import API_BASE_URL from './config';

const API_URL = `${API_BASE_URL}/auth`;
const TOKEN_KEY = 'token';
const REFRESH_TOKEN_KEY = 'refresh_token';
const USER_KEY = 'user';

const getStoredUser = () => {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    return null;
  }
};

const isAuthError = (error) => {
  const status = error?.response?.status;
  if (status === 401) return true;
  if (status !== 422) return false;
  const payload = error?.response?.data;
  const msg = String(payload?.msg || payload?.error || '').toLowerCase();
  return msg.includes('token') || msg.includes('jwt') || msg.includes('subject');
};

const login = async (username, password) => {
  const response = await axios.post(`${API_URL}/login`, {
    username,
    password,
  });

  const payload = response.data || {};
  if (payload.access_token) {
    localStorage.setItem(TOKEN_KEY, payload.access_token);
  }
  if (payload.refresh_token) {
    localStorage.setItem(REFRESH_TOKEN_KEY, payload.refresh_token);
  }
  if (payload.user) {
    localStorage.setItem(USER_KEY, JSON.stringify(payload.user));
  }

  return payload.user || null;
};

const getUser = async () => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) return null;

  try {
    const response = await axios.get(`${API_URL}/me`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    localStorage.setItem(USER_KEY, JSON.stringify(response.data));
    return response.data;
  } catch (error) {
    if (isAuthError(error)) {
      try {
        const refreshed = await refreshAccessToken();
        if (!refreshed) {
          logout();
          return null;
        }
        const response = await axios.get(`${API_URL}/me`, {
          headers: { Authorization: `Bearer ${refreshed}` }
        });
        localStorage.setItem(USER_KEY, JSON.stringify(response.data));
        return response.data;
      } catch (_) {
        logout();
        return null;
      }
    }
    // Do not destroy session on transient backend/network errors during refresh.
    return getStoredUser();
  }
};

const refreshAccessToken = async () => {
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) return null;

  try {
    const response = await axios.post(
      `${API_URL}/refresh`,
      {},
      { headers: { Authorization: `Bearer ${refreshToken}` } }
    );
    const newToken = response?.data?.access_token;
    if (newToken) {
      localStorage.setItem(TOKEN_KEY, newToken);
      return newToken;
    }
  } catch (_) {
    // caller handles logout decisions
  }
  return null;
};

const logout = () => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
};

const getToken = () => {
  return localStorage.getItem(TOKEN_KEY);
};

const getRefreshToken = () => {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
};

// Wrap in object and export as default
const authService = {
  login,
  getUser,
  logout,
  getToken,
  getRefreshToken,
  refreshAccessToken,
  getStoredUser
};

export default authService;
