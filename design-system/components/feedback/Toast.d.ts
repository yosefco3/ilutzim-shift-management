import * as React from 'react';

/**
 * Transient in-app notification (replaces native alert()). Presentational —
 * render inside a fixed top-center stack and manage dismissal yourself.
 */
export interface ToastProps {
  /** Tone — sets accent border + icon chip. */
  variant?: 'success' | 'error' | 'warning' | 'info';
  /** Optional close handler — renders the × button when provided. */
  onClose?: () => void;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}

export function Toast(props: ToastProps): JSX.Element;
