import * as React from 'react';

/**
 * Pill status label — week lifecycle, guard activity, submission state, or
 * generic semantic tone.
 */
export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Semantic tone / state. */
  tone?:
    | 'open' | 'locked' | 'published' | 'closed'
    | 'active' | 'inactive'
    | 'submitted' | 'missing'
    | 'success' | 'warning' | 'danger' | 'info' | 'secondary';
  /** Optional leading emoji icon. */
  icon?: React.ReactNode;
  children?: React.ReactNode;
}

export function Badge(props: BadgeProps): JSX.Element;
