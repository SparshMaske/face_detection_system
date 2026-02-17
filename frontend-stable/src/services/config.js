const API_BASE_URL =
  process.env.REACT_APP_API_URL ||
  process.env.VITE_API_URL ||
  'http://127.0.0.1:5000/api';

export default API_BASE_URL;
