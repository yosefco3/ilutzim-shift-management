import React from 'react';

/**
 * Ilutsim Card — the base surface panel used for forms, week cards, settings
 * rows and login. Dark layered surface with a hairline border and soft shadow.
 * Optionally interactive (hover lift), as used by the week cards.
 */
export function Card({ children, interactive = false, style = {}, ...rest }) {
  const [hovered, setHovered] = React.useState(false);
  return (
    <div
      onMouseEnter={() => interactive && setHovered(true)}
      onMouseLeave={() => interactive && setHovered(false)}
      style={{
        background: 'var(--surface)',
        border: `1px solid ${hovered ? 'var(--border-strong)' : 'var(--border)'}`,
        borderRadius: 'var(--radius)',
        padding: 'var(--space-5)',
        boxShadow: hovered ? 'var(--shadow-md)' : 'var(--shadow)',
        color: 'var(--text)',
        fontFamily: 'var(--font-sans)',
        transition: 'border-color var(--t-fast), box-shadow var(--t-fast)',
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}
