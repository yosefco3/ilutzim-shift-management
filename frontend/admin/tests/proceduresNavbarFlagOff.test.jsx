import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Authenticated navbar (default env → VITE_PROCEDURES_ENABLED is unset → flag OFF).
vi.mock('../src/api/adminApiClient', () => ({
  isLoggedIn: () => true,
  adminLogout: vi.fn(),
}));

import Navbar from '../src/components/Navbar';
import messages from '../src/utils/messages';

describe('Procedures navbar entry (default flag OFF)', () => {
  it('hides the נהלים nav link when the flag is off', () => {
    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>,
    );
    const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href'));
    expect(hrefs).not.toContain('/procedures');
    expect(screen.queryByRole('link', { name: messages.procedures.nav })).toBeNull();
  });

  it('keeps settings last (procedures link does not insert before logout)', () => {
    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>,
    );
    const links = screen.getAllByRole('link');
    expect(links[links.length - 1]).toHaveAttribute('href', '/settings');
  });
});
