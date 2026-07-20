import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ProfileMatrix from '../src/components/positions/ProfileMatrix';
import messages from '../src/utils/messages';
import { DAY_NAMES_SHORT as DAY_NAMES } from '../src/utils/guardMessages.js';

// Accessible name of a matrix cell (matches the component's aria-label).
const cellName = (posName, dayIdx, active) =>
  `${posName}, ${DAY_NAMES[dayIdx]}, ${active ? messages.positions.active : messages.positions.matrixOff}`;

// positions arrive from listPositions() in display_order; day_schedules is a
// string-keyed map { "<dayIndex>": { start, end } }.
const POSITION = (overrides = {}) => ({
  id: 'pos1',
  name: 'ארנונה',
  day_schedules: { 0: { start: '07:30', end: '15:00' } },
  is_event: false,
  event_required_count: null,
  ...overrides,
});

describe('ProfileMatrix', () => {
  it('renders a row per position and all 7 day columns', () => {
    render(<ProfileMatrix positions={[POSITION()]} profile={{ day_labels: {} }} />);
    expect(screen.getByText('ארנונה')).toBeInTheDocument();
    ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת'].forEach((d) => {
      expect(screen.getByText(d)).toBeInTheDocument();
    });
  });

  it('shows the hours text on an active day and ✕ on inactive days', () => {
    render(<ProfileMatrix positions={[POSITION()]} profile={{ day_labels: {} }} />);
    // Active Sunday cell → "07:30–15:00" (computed via messages to match the en-dash).
    const hours = messages.positions.matrixHours('07:30', '15:00');
    expect(screen.getByText(hours)).toBeInTheDocument();
    // The other 6 days are inactive → a ✕ each.
    expect(screen.getAllByText('✕')).toHaveLength(6);
  });

  it('renders a fully-off position with ✕ in every day cell', () => {
    render(
      <ProfileMatrix
        positions={[POSITION({ day_schedules: {} })]}
        profile={{ day_labels: {} }}
      />,
    );
    expect(screen.getAllByText('✕')).toHaveLength(7);
  });

  it('renders the event badge exactly like the cards (with count when set)', () => {
    render(
      <ProfileMatrix
        positions={[POSITION({ is_event: true, event_required_count: 4 })]}
        profile={{ day_labels: {} }}
      />,
    );
    expect(screen.getByText('📣 אירוע · 4')).toBeInTheDocument();
  });

  it('renders the event badge without a count when unlimited', () => {
    render(
      <ProfileMatrix positions={[POSITION({ is_event: true })]} profile={{ day_labels: {} }} />
    );
    expect(screen.getByText('📣 אירוע')).toBeInTheDocument();
  });

  it('renders a day-label chip when the profile has day_labels', () => {
    render(
      <ProfileMatrix
        positions={[POSITION()]}
        profile={{ day_labels: { 4: 'ט׳ באב' } }}
      />,
    );
    expect(screen.getByText('ט׳ באב')).toBeInTheDocument();
  });

  it('omits the day-label chip when no label is set for a day', () => {
    render(<ProfileMatrix positions={[POSITION()]} profile={{ day_labels: {} }} />);
    expect(screen.queryByText('ט׳ באב')).toBeNull();
  });

  it('keeps rows in the given (display) order', () => {
    render(
      <ProfileMatrix
        positions={[POSITION({ id: 'a', name: 'ראשון-בסדר' }), POSITION({ id: 'b', name: 'שני-בסדר' })]}
        profile={{ day_labels: {} }}
      />,
    );
    const names = screen
      .getAllByRole('row')
      .map((r) => r.querySelector('.profile-matrix-name-text')?.textContent)
      .filter(Boolean);
    expect(names).toEqual(['ראשון-בסדר', 'שני-בסדר']);
  });
});

// ── Step 04: cell toggle, dirty tracking, save/discard ──────────────────────
describe('ProfileMatrix editing (step 04)', () => {
  const A = messages.positions.active; // "פעיל"
  const OFF = messages.positions.matrixOff; // "לא פעיל"
  const hours = (s, e) => messages.positions.matrixHours(s, e);

  it('toggle off→on restores the cell\'s own snapshot hours (restore order a)', () => {
    render(
      <ProfileMatrix
        positions={[POSITION({ day_schedules: { 0: { start: '07:30', end: '15:00' } } })]}
        profile={{ day_labels: {} }}
        onSave={vi.fn()}
        onDirtyChange={vi.fn()}
      />,
    );
    // Sunday is active → toggle it off.
    fireEvent.click(screen.getByRole('button', { name: cellName('ארנונה', 0, true) }));
    expect(screen.getByRole('button', { name: cellName('ארנונה', 0, false) })).toBeInTheDocument();
    // Toggle back on → restores the snapshot's 07:30–15:00 for that cell.
    fireEvent.click(screen.getByRole('button', { name: cellName('ארנונה', 0, false) }));
    const restored = screen.getByRole('button', { name: cellName('ארנונה', 0, true) });
    expect(restored).toHaveTextContent(hours('07:30', '15:00'));
  });

  it('toggle on with no snapshot for that day copies the position\'s first active window (order b)', () => {
    // Sunday active 07:30–15:00; Tuesday has no snapshot hours.
    render(
      <ProfileMatrix
        positions={[POSITION({ day_schedules: { 0: { start: '07:30', end: '15:00' } } })]}
        profile={{ day_labels: {} }}
        onSave={vi.fn()}
        onDirtyChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: cellName('ארנונה', 2, false) }));
    // First active day in the snapshot is Sunday (07:30–15:00) → copied.
    expect(screen.getByRole('button', { name: cellName('ארנונה', 2, true) })).toHaveTextContent(
      hours('07:30', '15:00'),
    );
  });

  it('toggle on with no active day in the snapshot falls back to 07:00–15:00 (order c)', () => {
    render(
      <ProfileMatrix
        positions={[POSITION({ day_schedules: {} })]}
        profile={{ day_labels: {} }}
        onSave={vi.fn()}
        onDirtyChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: cellName('ארנונה', 0, false) }));
    expect(screen.getByRole('button', { name: cellName('ארנונה', 0, true) })).toHaveTextContent(
      hours('07:00', '15:00'),
    );
  });

  it('save sends ONLY changed positions, each with its full current day map [EDGE C1/D3]', async () => {
    const onSave = vi.fn().mockResolvedValue('ok');
    const posA = POSITION({ id: 'a', day_schedules: { 0: { start: '07:30', end: '15:00' } } });
    const posB = POSITION({ id: 'b', name: 'שער', day_schedules: { 1: { start: '08:00', end: '16:00' } } });
    render(<ProfileMatrix positions={[posA, posB]} profile={{ day_labels: {} }} onSave={onSave} onDirtyChange={vi.fn()} />);
    // Toggle only posA's Sunday off; posB untouched.
    fireEvent.click(screen.getByRole('button', { name: cellName('ארנונה', 0, true) }));
    fireEvent.click(screen.getByText(messages.positions.matrixSave(1)));

    expect(onSave).toHaveBeenCalledTimes(1);
    const [items] = onSave.mock.calls[0];
    expect(items).toHaveLength(1);
    expect(items[0].position_id).toBe('a');
    // posA's Sunday was removed → its current map is {} (all-days-off allowed).
    expect(items[0].day_schedules).toEqual({});
  });

  it('discards changes back to the snapshot and clears the dirty highlight', () => {
    const onDirtyChange = vi.fn();
    render(
      <ProfileMatrix
        positions={[POSITION()]}
        profile={{ day_labels: {} }}
        onSave={vi.fn()}
        onDirtyChange={onDirtyChange}
      />,
    );
    // Make Sunday dirty (off).
    fireEvent.click(screen.getByRole('button', { name: cellName('ארנונה', 0, true) }));
    expect(onDirtyChange).toHaveBeenLastCalledWith(1);
    const dirtyCell = screen.getByRole('button', { name: cellName('ארנונה', 0, false) });
    expect(dirtyCell.className).toContain('is-dirty');

    // Discard.
    fireEvent.click(screen.getByText(messages.positions.matrixDiscard));

    // Sunday is active again with its snapshot hours, no longer dirty, count back to 0.
    const restored = screen.getByRole('button', { name: cellName('ארנונה', 0, true) });
    expect(restored).toHaveTextContent(hours('07:30', '15:00'));
    expect(restored.className).not.toContain('is-dirty');
    expect(onDirtyChange).toHaveBeenLastCalledWith(0);
  });
});
