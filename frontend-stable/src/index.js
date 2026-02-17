import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App'; // Make sure you have App.js or App.jsx in this folder

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);