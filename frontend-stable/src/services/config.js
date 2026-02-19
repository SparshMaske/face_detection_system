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

const API_BASE_URL =
  process.env.REACT_APP_API_URL ||
  process.env.VITE_API_URL ||
  resolveDefaultApiBaseUrl();

export default API_BASE_URL;
