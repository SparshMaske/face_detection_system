const resolveDefaultApiBaseUrl = () => {
  if (typeof window === 'undefined') {
    return 'http://127.0.0.1:5000/api';
  }

  const host = window.location.hostname;
  const isLocalHost = host === 'localhost' || host === '127.0.0.1';

  if (isLocalHost) {
    return 'http://127.0.0.1:5000/api';
  }

  // For ngrok/public access, keep API same-origin to avoid CORS/mixed-content issues.
  return `${window.location.origin}/api`;
};

const envApiBaseUrl = process.env.REACT_APP_API_URL || process.env.VITE_API_URL;

const API_BASE_URL =
  typeof window !== 'undefined' &&
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') &&
  (envApiBaseUrl === '/api' || envApiBaseUrl === 'api')
    ? 'http://127.0.0.1:5000/api'
    : envApiBaseUrl || resolveDefaultApiBaseUrl();

export default API_BASE_URL;
