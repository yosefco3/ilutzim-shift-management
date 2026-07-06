import React from 'react';

/**
 * Ilutsim Field — label + control wrapper with optional hint, matching the
 * app's .form-group. Compose with TextInput / Select / Textarea.
 */
export function Field({ label, hint, htmlFor, children, style = {}, ...rest }) {
  return (
    <div style={{ marginBottom: 'var(--space-4)', ...style }} {...rest}>
      {label && (
        <label
          htmlFor={htmlFor}
          style={{
            display: 'block',
            fontWeight: 'var(--fw-control)',
            marginBottom: '0.35rem',
            fontSize: 'var(--fs-base)',
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          {label}
        </label>
      )}
      {children}
      {hint && (
        <p style={{ margin: '0.35rem 0 0', fontSize: 'var(--fs-sm)', color: 'var(--text-dim)', fontFamily: 'var(--font-sans)' }}>
          {hint}
        </p>
      )}
    </div>
  );
}
