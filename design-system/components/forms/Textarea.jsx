import React, { useState } from 'react';

/** Ilutsim textarea — dark field, vertical resize, indigo focus ring. */
export function Textarea({ style = {}, onFocus, onBlur, ...rest }) {
  const [focused, setFocused] = useState(false);
  return (
    <textarea
      style={{
        width: '100%',
        minHeight: 70,
        padding: '0.55rem 0.75rem',
        background: 'var(--surface-2)',
        color: 'var(--text)',
        border: `1px solid ${focused ? 'var(--primary)' : 'var(--border-strong)'}`,
        borderRadius: 'var(--radius-sm)',
        fontSize: 'var(--fs-md)',
        fontFamily: 'var(--font-sans)',
        direction: 'rtl',
        resize: 'vertical',
        outline: 'none',
        boxShadow: focused ? '0 0 0 3px var(--primary-soft)' : 'none',
        transition: 'border-color var(--t-fast), box-shadow var(--t-fast)',
        ...style,
      }}
      onFocus={(e) => { setFocused(true); onFocus && onFocus(e); }}
      onBlur={(e) => { setFocused(false); onBlur && onBlur(e); }}
      {...rest}
    />
  );
}
