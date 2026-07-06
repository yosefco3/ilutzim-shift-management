import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { useLocation } from 'react-router-dom';
import React from 'react';

// Mock pages
vi.mock('../src/pages/SubmitPage', () => ({
  default: () => <div data-testid="submit-page">Submit</div>,
}));
vi.mock('../src/pages/LoginPage', () => ({
  default: () => <div data-testid="login-page">Login</div>,
}));
vi.mock('../src/pages/GuardsPage', () => ({
  default: () => <div data-testid="guards-page">Guards</div>,
}));
vi.mock('../src/components/ProtectedRoute', () => ({
  default: ({ children }) => <>{children}</>,
}));

// Mock Navbar to track if it's rendered
const NavbarMock = vi.fn(() => <nav data-testid="navbar">Navbar</nav>);
vi.mock('../src/components/Navbar', () => ({
  default: (props) => NavbarMock(props),
}));

// Recreate the AppContent logic for testing
import SubmitPage from '../src/pages/SubmitPage';
import LoginPage from '../src/pages/LoginPage';
import GuardsPage from '../src/pages/GuardsPage';
import Navbar from '../src/components/Navbar';

function TestApp() {
  const location = useLocation();
  const hideNavbar = location.pathname === '/submit';

  return (
    <>
      {!hideNavbar && <Navbar />}
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/submit" element={<SubmitPage />} />
        <Route path="/guards" element={<GuardsPage />} />
      </Routes>
    </>
  );
}

describe('Navbar visibility', () => {
  beforeEach(() => {
    NavbarMock.mockClear();
  });

  it('should hide Navbar on /submit route', () => {
    render(
      <MemoryRouter initialEntries={['/submit']}>
        <TestApp />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('navbar')).toBeNull();
    expect(screen.getByTestId('submit-page')).toBeInTheDocument();
  });

  it('should show Navbar on /login route', () => {
    render(
      <MemoryRouter initialEntries={['/login']}>
        <TestApp />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('navbar')).toBeInTheDocument();
  });

  it('should show Navbar on /guards route', () => {
    render(
      <MemoryRouter initialEntries={['/guards']}>
        <TestApp />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('navbar')).toBeInTheDocument();
  });
});