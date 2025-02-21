import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css'; // Ensure that it includes the TailwindCSS setup
import App from './App';
import reportWebVitals from './reportWebVitals';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// Optionally log performance metrics
reportWebVitals();
