import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../src/hooks/useGuards', () => ({ useGuards: vi.fn() }));
vi.mock('../src/components/Toast', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }));

import { useGuards } from '../src/hooks/useGuards';
import GuardsPage from '../src/pages/GuardsPage';
import messages from '../src/utils/messages';

const guards = [
  { id: 1, first_name: 'בובי', last_name: 'ביטון', is_active: true, roles: [] },
  { id: 2, first_name: 'דנה', last_name: 'לוי', is_active: true, roles: [] },
];

describe('GuardsPage — search by name', () => {
  beforeEach(() => {
    useGuards.mockReset();
    useGuards.mockReturnValue({
      guards,
      loading: false,
      createGuard: vi.fn(),
      updateGuard: vi.fn(),
      toggleGuard: vi.fn(),
      deleteGuard: vi.fn(),
    });
  });

  it('filters the guard rows by name and shows a no-results notice', () => {
    render(<GuardsPage />);

    // Both guards visible before searching.
    expect(screen.getByText('בובי ביטון')).toBeInTheDocument();
    expect(screen.getByText('דנה לוי')).toBeInTheDocument();

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'דנה' } });
    expect(screen.getByText('דנה לוי')).toBeInTheDocument();
    expect(screen.queryByText('בובי ביטון')).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'רפאל' } });
    expect(screen.getByText(messages.common.noSearchResults)).toBeInTheDocument();
  });
});
