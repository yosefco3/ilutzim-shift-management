import * as React from 'react';

/** Dark dropdown — same field treatment as TextInput. */
export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  children?: React.ReactNode;
}

export function Select(props: SelectProps): JSX.Element;
