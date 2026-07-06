import React, { useState } from 'react';

/**
 * Ilutsim Button — the dark-indigo action button used across the admin app.
 * Variants map 1:1 to the live app's .btn-* classes; styling is driven by the
 * design-system CSS custom properties so it renders correctly anywhere
 * styles.css is linked. RTL by default.
 */

const SIZES = {
  md: { padding: '0.5rem 1rem', fontSize: 'var(--fs-base)' },
  sm: { padding: '0.3rem 0.65rem', fontSize: 'var(--fs-sm)' },
};

function variantStyle(variant, hovered) {
  switch (variant) {
    case 'primary':
      return { background: hovered ? 'var(--primary-hover)' : 'var(--primary)', color: '#fff', borderColor: 'transparent' };
    case 'danger':
      return { background: hovered ? 'var(--danger-hover)' : 'var(--danger)', color: '#fff', borderColor: 'transparent' };
    case 'success':
      return { background: hovered ? '#2dd46a' : 'var(--success)', color: '#0a2e16', borderColor: 'transparent' };
    case 'secondary':
      return { background: hovered ? 'var(--border-strong)' : 'var(--surface-3)', color: 'var(--text)', borderColor: 'var(--border-strong)' };
    case 'outline':
      return { background: hovered ? 'rgba(255,255,255,.03)' : 'transparent', color: hovered ? 'var(--text)' : 'var(--text-muted)', borderColor: hovered ? 'var(--text-dim)' : 'var(--border-strong)' };
    case 'ghost':
      return { background: hovered ? 'rgba(255,255,255,.05)' : 'transparent', color: hovered ? 'var(--text)' : 'var(--text-muted)', borderColor: 'transparent' };
    default:
      return { background: 'var(--primary)', color: '#fff', borderColor: 'transparent' };
  }
}

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  block = false,
  disabled = false,
  icon = null,
  style = {},
  ...rest
}) {
  const [hovered, setHovered] = useState(false);
  const [pressed, setPressed] = useState(false);

  const base = {
    display: block ? 'flex' : 'inline-flex',
    width: block ? '100%' : undefined,
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.45rem',
    border: '1px solid transparent',
    borderRadius: 'var(--radius-sm)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontWeight: 'var(--fw-control)',
    fontFamily: 'var(--font-sans)',
    lineHeight: 'var(--lh-tight)',
    opacity: disabled ? 0.45 : 1,
    transform: pressed && !disabled ? 'translateY(1px)' : 'none',
    transition: 'background var(--t-fast), border-color var(--t-fast), color var(--t-fast), transform var(--t-press)',
    ...SIZES[size],
    ...variantStyle(variant, hovered && !disabled),
    ...style,
  };

  return (
    <button
      type="button"
      disabled={disabled}
      style={base}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => { setHovered(false); setPressed(false); }}
      onMouseDown={() => setPressed(true)}
      onMouseUp={() => setPressed(false)}
      {...rest}
    >
      {icon && <span aria-hidden="true">{icon}</span>}
      {children}
    </button>
  );
}
