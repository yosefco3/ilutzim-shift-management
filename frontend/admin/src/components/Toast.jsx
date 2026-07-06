/**
 * Lightweight in-app toast notifications (replaces native alert()).
 * Wrap the app in <ToastProvider> and call useToast() to get
 * { success, error, info, warning }. Toasts auto-dismiss and can be
 * clicked to close. RTL/dark styled via .toast-* classes in admin.css.
 */
import { createContext, useContext, useState, useCallback, useRef, useMemo } from 'react';

const ToastContext = createContext(null);

const ICONS = { success: '✓', error: '✕', warning: '!', info: 'i' };

let seq = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timers = useRef({});

  const remove = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id));
    const timer = timers.current[id];
    if (timer) { clearTimeout(timer); delete timers.current[id]; }
  }, []);

  const push = useCallback((message, type, duration) => {
    const id = ++seq;
    setToasts((list) => [...list, { id, message, type }]);
    timers.current[id] = setTimeout(() => remove(id), duration);
    return id;
  }, [remove]);

  const toast = useMemo(() => ({
    success: (m, d = 3500) => push(m, 'success', d),
    error:   (m, d = 5000) => push(m, 'error', d),
    warning: (m, d = 4000) => push(m, 'warning', d),
    info:    (m, d = 3500) => push(m, 'info', d),
  }), [push]);

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className="toast-container" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`} onClick={() => remove(t.id)}>
            <span className="toast-icon">{ICONS[t.type]}</span>
            <span className="toast-msg">{t.message}</span>
            <button
              type="button"
              className="toast-close"
              aria-label="סגור"
              onClick={(e) => { e.stopPropagation(); remove(t.id); }}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within a ToastProvider');
  return ctx;
}
