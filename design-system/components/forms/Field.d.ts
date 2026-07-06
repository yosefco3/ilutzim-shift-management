import * as React from 'react';

/** Label + control wrapper with optional hint (the app's .form-group). */
export interface FieldProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Field label text. */
  label?: React.ReactNode;
  /** Muted hint line under the control. */
  hint?: React.ReactNode;
  /** id of the control, wired to the label's htmlFor. */
  htmlFor?: string;
  children?: React.ReactNode;
}

export function Field(props: FieldProps): JSX.Element;
