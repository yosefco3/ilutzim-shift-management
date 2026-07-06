import * as React from 'react';

/**
 * Base surface panel — forms, week cards, settings rows, login.
 */
export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Enable hover lift (border + shadow), as used by week cards. */
  interactive?: boolean;
  children?: React.ReactNode;
}

export function Card(props: CardProps): JSX.Element;
