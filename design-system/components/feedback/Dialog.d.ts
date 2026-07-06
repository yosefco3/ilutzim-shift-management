import * as React from 'react';

/**
 * Centered confirm modal over a blurred dark scrim. Used for destructive
 * confirmations (delete guard / delete week). Click the scrim to cancel.
 */
export interface DialogProps {
  title?: React.ReactNode;
  message?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Button variant for the confirm action (default 'danger'). */
  confirmVariant?: 'primary' | 'danger' | 'success';
  onConfirm?: () => void;
  onCancel?: () => void;
  children?: React.ReactNode;
}

export function Dialog(props: DialogProps): JSX.Element;
