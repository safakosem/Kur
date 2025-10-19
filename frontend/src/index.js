import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import { Toaster } from 'sonner';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
    <Toaster 
      position="top-left" 
      richColors 
      toastOptions={{
        style: {
          fontSize: '0.875rem',
          padding: '0.75rem 1rem',
        }
      }}
    />
  </React.StrictMode>
);