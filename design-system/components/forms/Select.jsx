import React, { useState } from 'react';

const baseControl = (focused) => ({
  width: '100%',
  padding: '0.55rem 0.75rem',
  background: 'var(--surface-2)',
  color: 'var(--text)',
  border: `1px solid ${focused ? 'var(--primary)' : 'var(--border-strong)'}`,
  borderRadius: 'var(--radius-sm)',
  fontSize: 'var(--fs-md)',
  fontFamily: 'var(--font-sans)',
  direction: 'rtl',
  outline: 'none',
  boxShadow: focused ? '0 0 0 3px var(--primary-soft)' : 'none',
  transition: 'border-color var(--t-fast), box-shadow var(--t-fast)',
});

/** Ilutsim select — same field treatment as TextInput. */
export function Select({ children, style = {}, onFocus, onBlur, ...rest }) {
  const [focused, setFocused] = useState(false);
  return (
    <select
      style={{ ...baseControl(focused), cursor: 'pointer', ...style }}
      onFocus={(e) => { setFocused(true); onFocus && onFocus(e); }}
      onBlur={(e) => { setFocused(false); onBlur && onBlur(e); }}
      {...rest}
    >
      {children}
    </select>
  );
}
