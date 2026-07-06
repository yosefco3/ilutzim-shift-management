import * as React from 'react';

/**
 * Inline feedback banner — form errors, success notices, soft constraint warnings.
 */
export interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Semantic tone. */
  tone?: 'error' | 'success' | 'warning' | 'info';
  children?: React.ReactNode;
}

export function Alert(props: AlertProps): JSX.Element;
