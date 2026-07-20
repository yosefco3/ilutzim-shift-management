import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import ProfileMatrix from '../src/components/positions/ProfileMatrix';
import messages from '../src/utils/messages';

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
