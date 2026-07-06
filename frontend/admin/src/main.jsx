import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import ErrorBoundary from './components/ErrorBoundary';

// Initialise the Telegram WebApp as early as possible. ready() tells Telegram
// the page has loaded (otherwise it keeps showing its dark loading screen), and
// expand() opens the WebApp to full height. No-ops outside Telegram.
const tg = window?.Telegram?.WebApp;
if (tg) {
  try {
    tg.ready();
    tg.expand();
  } catch {
    /* not in a Telegram context — ignore */
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
