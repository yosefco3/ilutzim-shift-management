import { describe, it, expect, vi, beforeAll } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

// Render the real App and verify the /procedures routes are GATED OUT when the
// flag is off (default env — VITE_PROCEDURES_ENABLED is unset). Mock the pages
// so we can inspect which one renders, plus Navbar (null) / ProtectedRoute
// (pass-through) / Toast (provider) so App mounts cleanly.
vi.mock('../src/components/Navbar', () => ({ default: () => null }));
vi.mock('../src/components/ProtectedRoute', () => ({ default: ({ children }) => <>{children}</> }));
vi.mock('../src/components/Toast', () => ({ ToastProvider: ({ children }) => <>{children}</> }));
vi.mock('../src/pages/ProceduresPage', () => ({
  default: () => <div data-testid="procedures-page">Procedures</div>,
}));
vi.mock('../src/pages/ProcedureDetailPage', () => ({
  default: () => <div data-testid="procedure-detail">Detail</div>,
}));
vi.mock('../src/pages/GuardsPage', () => ({
  default: () => <div data-testid="guards-page">Guards</div>,
}));

import App from '../src/App';

describe('Procedures route gating (default flag OFF)', () => {
  beforeAll(() => {
    // App mounts its own BrowserRouter, which reads window.location on mount —
    // so set the URL to /procedures before rendering.
    window.history.pushState({}, '', '/procedures');
  });

  it('redirects /procedures → /guards (route is not registered)', async () => {
    render(<App />);
    // The unregistered /procedures path falls through to the `*` catch-all,
    // which redirects to /guards. The procedures pages never render.
    await waitFor(() => expect(screen.getByTestId('guards-page')).toBeInTheDocument());
    expect(screen.queryByTestId('procedures-page')).toBeNull();
    expect(screen.queryByTestId('procedure-detail')).toBeNull();
  });

  it('redirects a procedure detail path too (/procedures/:id)', async () => {
    window.history.pushState({}, '', '/procedures/some-id');
    render(<App />);
    await waitFor(() => expect(screen.getByTestId('guards-page')).toBeInTheDocument());
    expect(screen.queryByTestId('procedure-detail')).toBeNull();
  });
});
