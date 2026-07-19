import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../src/hooks/useGuards', () => ({ useGuards: vi.fn() }));
vi.mock('../src/components/Toast', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }));

import { useGuards } from '../src/hooks/useGuards';
import GuardsPage from '../src/pages/GuardsPage';

const guards = [
  { id: 1, first_name: 'בובי', last_name: 'ביטון', is_active: true, roles: [] },
  { id: 2, first_name: 'דנה', last_name: 'לוי', is_active: false, roles: [] },
  { id: 3, first_name: 'רפאל', last_name: 'כהן', is_active: true, roles: [] },
];

function mockGuards(list) {
  useGuards.mockReturnValue({
    guards: list,
    loading: false,
    createGuard: vi.fn(),
    updateGuard: vi.fn(),
    toggleGuard: vi.fn(),
    deleteGuard: vi.fn(),
  });
}

describe('GuardsPage — header count summary + row numbers', () => {
  beforeEach(() => {
    useGuards.mockReset();
  });

  it('shows total and deactivated counts above the table', () => {
    mockGuards(guards);
    render(<GuardsPage />);
    expect(screen.getByText('סה"כ 3 מאבטחים · 1 מושבתים')).toBeInTheDocument();
  });

  it('omits the deactivated part when all guards are active', () => {
    mockGuards(guards.map((g) => ({ ...g, is_active: true })));
    render(<GuardsPage />);
    expect(screen.getByText('סה"כ 3 מאבטחים')).toBeInTheDocument();
  });

  it('numbers the rows sequentially in display order', () => {
    mockGuards(guards);
    render(<GuardsPage />);
    const rows = screen.getAllByRole('row').slice(1); // skip header row
    const numbers = rows.map((r) => r.cells[0].textContent);
    expect(numbers).toEqual(['1', '2', '3']);
  });

  it('keeps the summary on ALL guards while numbering follows the filtered view', () => {
    mockGuards(guards);
    render(<GuardsPage />);
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'דנה' } });
    // Summary unchanged — it describes the whole roster, not the search hits.
    expect(screen.getByText('סה"כ 3 מאבטחים · 1 מושבתים')).toBeInTheDocument();
    const rows = screen.getAllByRole('row').slice(1);
    expect(rows).toHaveLength(1);
    expect(rows[0].cells[0].textContent).toBe('1');
  });
});
