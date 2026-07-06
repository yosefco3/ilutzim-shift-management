import React from 'react';
import { Button } from '../core/Button.jsx';

/**
 * Ilutsim Dialog — centered confirm modal over a blurred dark scrim. Used for
 * destructive confirmations (delete guard / delete week).
 */
export function Dialog({
  title,
  message,
  children,
  confirmLabel = 'אישור',
  cancelLabel = 'ביטול',
  confirmVariant = 'danger',
  onConfirm,
  onCancel,
}) {
  return (
    <div
      onClick={onCancel}
      style={{
        position: 'fixed', inset: 0, zIndex: 200,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(5,7,12,.65)', backdropFilter: 'blur(2px)',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-8)',
          maxWidth: 400, width: '90%',
          textAlign: 'center',
          boxShadow: 'var(--shadow-lg)',
          color: 'var(--text)',
          fontFamily: 'var(--font-sans)',
        }}
      >
        {title && <h3 style={{ margin: '0 0 0.75rem', fontSize: 'var(--fs-lg)', fontWeight: 'var(--fw-heading)' }}>{title}</h3>}
        {message && <p style={{ marginBottom: 'var(--space-6)', fontSize: 'var(--fs-lg)', lineHeight: 'var(--lh-snug)' }}>{message}</p>}
        {children}
        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
          {onConfirm && <Button variant={confirmVariant} onClick={onConfirm}>{confirmLabel}</Button>}
          {onCancel && <Button variant="secondary" onClick={onCancel}>{cancelLabel}</Button>}
        </div>
      </div>
    </div>
  );
}
