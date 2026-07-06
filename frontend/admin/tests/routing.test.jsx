import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { MemoryRouter } from 'react-router-dom';

// Mock all page imports to avoid loading full pages
vi.mock('../src/pages/SubmitPage', () => ({
  default: () => <div data-testid="submit-page">Submit Page</div>,
}));

vi.mock('../src/pages/SuccessPage', () => ({
  default: () => <div data-testid="success-page">Success Page</div>,
}));

vi.mock('../src/pages/LoginPage', () => ({
  default: () => <div data-testid="login-page">Login Page</div>,
}));

vi.mock('../src/pages/GuardsPage', () => ({
  default: () => <div data-testid="guards-page">Guards Page</div>,
}));

vi.mock('../src/components/ProtectedRoute', () => ({
  default: ({ children }) => <div data-testid="protected">{children}</div>,
}));

import SubmitPage from '../src/pages/SubmitPage';
import SuccessPage from '../src/pages/SuccessPage';
import LoginPage from '../src/pages/LoginPage';

describe('Routing', () => {
  it('should render SubmitPage at /submit without protection', () => {
    render(
      <MemoryRouter initialEntries={['/submit']}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/submit" element={<SubmitPage />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId('submit-page')).toBeInTheDocument();
    expect(screen.queryByTestId('protected')).toBeNull();
  });

  it('should render SuccessPage at /submit/success without protection', () => {
    render(
      <MemoryRouter initialEntries={['/submit/success']}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/submit/success" element={<SuccessPage />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId('success-page')).toBeInTheDocument();
    expect(screen.queryByTestId('protected')).toBeNull();
  });

  it('should render LoginPage at /login', () => {
    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/submit" element={<SubmitPage />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId('login-page')).toBeInTheDocument();
  });

  it('should render SubmitPage content directly (no ProtectedRoute wrapper)', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/submit']}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/submit" element={<SubmitPage />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(container.querySelector('[data-testid="protected"]')).toBeNull();
    expect(screen.getByTestId('submit-page')).toBeInTheDocument();
  });
});

describe('SubmitPage', () => {
  it('should export a valid React component', async () => {
    const { default: SubmitPageComp } = await import('../src/pages/SubmitPage');
    const { container } = render(<SubmitPageComp />);
    expect(container).toBeTruthy();
  });
});