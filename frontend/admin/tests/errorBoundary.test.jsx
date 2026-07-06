import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import ErrorBoundary from '../src/components/ErrorBoundary';

function Boom() {
  throw new Error('boom');
}

describe('ErrorBoundary', () => {
  afterEach(() => vi.restoreAllMocks());

  it('renders children when there is no error', () => {
    render(
      <ErrorBoundary>
        <p>תוכן תקין</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText('תוכן תקין')).toBeInTheDocument();
  });

  it('shows a readable fallback instead of a blank screen when a child throws', () => {
    // Boundaries log the error; silence it to keep test output clean.
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText('אירעה שגיאה בטעינת המסך')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'רענן' })).toBeInTheDocument();
  });
});
