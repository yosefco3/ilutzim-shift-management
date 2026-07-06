import * as React from 'react';

/**
 * Ilutsim dark-indigo action button.
 */
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Visual style. */
  variant?: 'primary' | 'danger' | 'success' | 'secondary' | 'outline' | 'ghost';
  /** Size preset. */
  size?: 'md' | 'sm';
  /** Stretch to full container width. */
  block?: boolean;
  /** Leading icon (an emoji string or node — the brand uses emoji icons). */
  icon?: React.ReactNode;
  children?: React.ReactNode;
}

export function Button(props: ButtonProps): JSX.Element;
