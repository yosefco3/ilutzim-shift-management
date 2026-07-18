import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

// Regression for the `hideNavbar` predicate: it must hide the navbar ONLY on the
// guard reading page `/procedure/:procedureId` and NOT on the ADMIN routes
// `/procedures` or `/procedures/:id`. An earlier `startsWith('/procedure')`
// (no trailing slash) swallowed both admin pages. We render the real App with
// the procedures flag ON so the admin routes actually register (otherwise
// /procedures redirects to /guards and the bug would be masked).

vi.mock('../src/components/Navbar', () => ({
  default: () => <nav data-testid="navbar">Navbar</nav>,
}));
vi.mock('../src/components/ProtectedRoute', () => ({
  default: ({ children }) => <>{children}</>,
}));
vi.mock('../src/components/Toast', () => ({
  ToastProvider: ({ children }) => <>{children}</>,
}));
vi.mock('../src/pages/ProceduresPage', () => ({
  default: () => <div data-testid="procedures-page">List</div>,
}));
vi.mock('../src/pages/ProcedureDetailPage', () => ({
  default: () => <div data-testid="procedure-detail">Detail</div>,
}));
vi.mock('../src/pages/ProcedureViewPage', () => ({
  default: () => <div data-testid="procedure-view">Guard view</div>,
}));
vi.mock('../src/pages/GuardsPage', () => ({
  default: () => <div data-testid="guards-page">Guards</div>,
}));

let App;

describe('navbar visibility: /procedure (guard) vs /procedures (admin)', () => {
  beforeAll(async () => {
    // Flip the procedures flag ON and re-import App so the admin /procedures
    // routes register (the module reads the flag at load time).
    vi.stubEnv('VITE_PROCEDURES_ENABLED', 'true');
    vi.resetModules();
    ({ default: App } = await import('../src/App'));
  });

  beforeEach(() => {
    cleanup();
  });

  it('hides the navbar on the guard reading page /procedure/<uuid>', () => {
    window.history.pushState({}, '', '/procedure/abc-123');
    render(<App />);
    expect(screen.queryByTestId('navbar')).toBeNull();
    expect(screen.getByTestId('procedure-view')).toBeInTheDocument();
  });

  it('shows the navbar on the admin /procedures list (regression: /procedures must NOT match /procedure)', () => {
    window.history.pushState({}, '', '/procedures');
    render(<App />);
    expect(screen.getByTestId('navbar')).toBeInTheDocument();
    expect(screen.getByTestId('procedures-page')).toBeInTheDocument();
  });

  it('shows the navbar on the admin /procedures/:id detail', () => {
    window.history.pushState({}, '', '/procedures/some-id');
    render(<App />);
    expect(screen.getByTestId('navbar')).toBeInTheDocument();
    expect(screen.getByTestId('procedure-detail')).toBeInTheDocument();
  });
});
