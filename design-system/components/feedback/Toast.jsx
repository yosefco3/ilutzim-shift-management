import React from 'react';

const ICONS = { success: '✓', error: '✕', warning: '!', info: 'i' };
const ACCENT = {
  success: 'var(--success)', error: 'var(--danger)',
  warning: 'var(--warning)', info: 'var(--info)',
};
const ICON_TINT = {
  success: { bg: 'var(--success-soft)', fg: 'var(--on-success)' },
  error:   { bg: 'var(--danger-soft)',  fg: 'var(--on-danger)' },
  warning: { bg: 'var(--warning-soft)', fg: 'var(--on-warning)' },
  info:    { bg: 'var(--info-soft)',    fg: 'var(--on-info)' },
};

/**
 * Ilutsim Toast — transient in-app notification (replaces native alert()).
 * Presentational: render inside a fixed top-center container. Variant sets the
 * leading accent border + icon chip.
 */
export function Toast({ children, variant = 'info', onClose, style = {} }) {
  const tint = ICON_TINT[variant] || ICON_TINT.info;
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.65rem',
        minWidth: 260,
        maxWidth: 440,
        padding: '0.7rem 0.85rem',
        background: 'var(--surface-3)',
        color: 'var(--text)',
        border: '1px solid var(--border-strong)',
        borderInlineStart: `3px solid ${ACCENT[variant] || 'var(--text-dim)'}`,
        borderRadius: 'var(--radius)',
        boxShadow: 'var(--shadow-lg)',
        fontSize: 'var(--fs-md)',
        fontFamily: 'var(--font-sans)',
        ...style,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 22, height: 22, borderRadius: 'var(--radius-pill)',
          fontSize: '0.8rem', fontWeight: 'var(--fw-bold)', flexShrink: 0,
          background: tint.bg, color: tint.fg,
        }}
      >
        {ICONS[variant]}
      </span>
      <span style={{ flex: 1, lineHeight: 'var(--lh-snug)' }}>{children}</span>
      {onClose && (
        <button
          type="button"
          aria-label="סגור"
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: 'var(--text-dim)', fontSize: '1.15rem', lineHeight: 1, cursor: 'pointer', padding: '0 0.15rem', flexShrink: 0 }}
        >
          ×
        </button>
      )}
    </div>
  );
}
