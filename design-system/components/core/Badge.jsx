import React from 'react';

/**
 * Ilutsim Badge — pill status label. Covers week lifecycle (open/locked/
 * published/closed), guard activity (active/inactive), submission state
 * (submitted/missing) and generic semantic tones. Soft-tinted on dark.
 */

const TONES = {
  open:      { bg: 'var(--info-soft)',    fg: 'var(--on-info)',    bd: 'rgba(56,189,248,.25)' },
  locked:    { bg: 'var(--warning-soft)', fg: 'var(--on-warning)', bd: 'rgba(245,158,11,.25)' },
  published: { bg: 'var(--success-soft)', fg: 'var(--on-success)', bd: 'rgba(34,197,94,.25)' },
  closed:    { bg: 'var(--surface-3)',    fg: 'var(--text-dim)',   bd: 'var(--border-strong)' },
  active:    { bg: 'var(--success-soft)', fg: 'var(--on-success)', bd: 'rgba(34,197,94,.25)' },
  inactive:  { bg: 'var(--surface-3)',    fg: 'var(--text-dim)',   bd: 'var(--border-strong)' },
  submitted: { bg: 'var(--success-soft)', fg: 'var(--on-success)', bd: 'rgba(34,197,94,.25)' },
  missing:   { bg: 'var(--danger-soft)',  fg: 'var(--on-danger)',  bd: 'rgba(239,68,68,.25)' },
  success:   { bg: 'var(--success-soft)', fg: 'var(--on-success)', bd: 'rgba(34,197,94,.25)' },
  warning:   { bg: 'var(--warning-soft)', fg: 'var(--on-warning)', bd: 'rgba(245,158,11,.25)' },
  danger:    { bg: 'var(--danger-soft)',  fg: 'var(--on-danger)',  bd: 'rgba(239,68,68,.25)' },
  info:      { bg: 'var(--info-soft)',    fg: 'var(--on-info)',    bd: 'rgba(56,189,248,.25)' },
  secondary: { bg: 'var(--surface-3)',    fg: 'var(--text-muted)', bd: 'var(--border-strong)' },
};

export function Badge({ children, tone = 'secondary', icon = null, style = {}, ...rest }) {
  const t = TONES[tone] || TONES.secondary;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.3rem',
        padding: '0.2rem 0.6rem',
        borderRadius: 'var(--radius-pill)',
        fontSize: 'var(--fs-xs)',
        fontWeight: 'var(--fw-semibold)',
        fontFamily: 'var(--font-sans)',
        lineHeight: 'var(--lh-tight)',
        border: `1px solid ${t.bd}`,
        background: t.bg,
        color: t.fg,
        ...style,
      }}
      {...rest}
    >
      {icon && <span aria-hidden="true">{icon}</span>}
      {children}
    </span>
  );
}
