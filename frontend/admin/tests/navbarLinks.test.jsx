import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Control auth state per-test
const isLoggedIn = vi.fn();
vi.mock('../src/api/adminApiClient', () => ({
  isLoggedIn: () => isLoggedIn(),
  adminLogout: vi.fn(),
}));

import Navbar from '../src/components/Navbar';
import messages from '../src/utils/messages';

function renderNavbar() {
  render(
    <MemoryRouter>
      <Navbar />
    </MemoryRouter>,
  );
}

describe('Navbar links', () => {
  beforeEach(() => {
    isLoggedIn.mockReset();
  });

  it('shows the weeks link when authenticated', () => {
    isLoggedIn.mockReturnValue(true);
    renderNavbar();
    const link = screen.getByRole('link', { name: messages.nav.weeks });
    expect(link).toHaveAttribute('href', '/weeks');
  });

  it('has no submissions / export / publish-preview links — all moved to the week cards', () => {
    isLoggedIn.mockReturnValue(true);
    renderNavbar();
    const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href'));
    expect(hrefs).not.toContain('/submissions');
    expect(hrefs).not.toContain('/export');
    expect(hrefs).not.toContain('/publish-preview');
  });

  it('places settings last, right before the logout button', () => {
    isLoggedIn.mockReturnValue(true);
    renderNavbar();
    const links = screen.getAllByRole('link');
    expect(links[links.length - 1]).toHaveAttribute('href', '/settings');
  });

  it('hides app links when not authenticated', () => {
    isLoggedIn.mockReturnValue(false);
    renderNavbar();
    expect(screen.queryByRole('link', { name: messages.nav.weeks })).toBeNull();
    expect(screen.getByRole('link', { name: messages.nav.login })).toBeInTheDocument();
  });
});
