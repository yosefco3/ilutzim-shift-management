import React from 'react';

/**
 * Ilutsim Alert — inline banner for form-level feedback. Soft-tinted, bordered,
 * RTL. Tones: error / success / warning / info.
 */
const TONES = {
  error:   { bg: 'var(--danger-soft)',  fg: 'var(--on-danger)',  bd: 'rgba(239,68,68,.3)' },
  success: { bg: 'var(--success-soft)', fg: 'var(--on-success)', bd: 'rgba(34,197,94,.3)' },
  warning: { bg: 'var(--warning-soft)', fg: 'var(--on-warning)', bd: 'rgba(245,158,11,.3)' },
  info:    { bg: 'var(--info-soft)',    fg: 'var(--on-info)',    bd: 'rgba(56,189,248,.3)' },
};

export function Alert({ children, tone = 'info', style = {}, ...rest }) {
  const t = TONES[tone] || TONES.info;
  return (
    <div
      role="alert"
      style={{
        padding: '0.7rem 0.9rem',
        borderRadius: 'var(--radius-sm)',
        fontSize: 'var(--fs-base)',
        fontFamily: 'var(--font-sans)',
        lineHeight: 'var(--lh-snug)',
        border: `1px solid ${t.bd}`,
        background: t.bg,
        color: t.fg,
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}
