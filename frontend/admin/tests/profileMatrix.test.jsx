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

// ── Step 05: per-cell hours popover ───────────────────────────────────────
describe('ProfileMatrix hours popover (step 05)', () => {
  const m = messages.positions;
  const common = messages.common;

  it('confirm updates the cell hours, marks the row dirty, and flows into the save payload', async () => {
    const onSave = vi.fn().mockResolvedValue('ok');
    render(
      <ProfileMatrix
        positions={[POSITION()]}
        profile={{ day_labels: {} }}
        onSave={onSave}
        onDirtyChange={vi.fn()}
      />,
    );
    // Sunday is active 07:30–15:00. Open the popover via the pencil.
    fireEvent.click(screen.getByRole('button', { name: m.matrixEditHours }));
    fireEvent.change(screen.getByLabelText(m.end), { target: { value: '17:45' } });
    fireEvent.click(screen.getByText(common.confirm));

    // Cell now shows the trimmed end, row is dirty → save shows count 1.
    expect(screen.getByText(m.matrixHours('07:30', '17:45'))).toBeInTheDocument();
    fireEvent.click(screen.getByText(m.matrixSave(1)));

    expect(onSave).toHaveBeenCalledTimes(1);
    const [items] = onSave.mock.calls[0];
    expect(items[0].position_id).toBe('pos1');
    expect(items[0].day_schedules[0]).toEqual({ start: '07:30', end: '17:45' });
  });

  it('Escape cancels without changing the cell or marking it dirty', () => {
    const onDirtyChange = vi.fn();
    render(
      <ProfileMatrix
        positions={[POSITION()]}
        profile={{ day_labels: {} }}
        onSave={vi.fn()}
        onDirtyChange={onDirtyChange}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: m.matrixEditHours }));
    fireEvent.change(screen.getByLabelText(m.end), { target: { value: '17:45' } });
    fireEvent.keyDown(screen.getByLabelText(m.end), { key: 'Escape' });

    // Popover closed, cell unchanged, still not dirty.
    expect(screen.queryByLabelText(m.end)).toBeNull();
    expect(screen.getByText(m.matrixHours('07:30', '15:00'))).toBeInTheDocument();
    expect(onDirtyChange).toHaveBeenLastCalledWith(0);
  });

  it('click-outside cancels without changing the cell', () => {
    render(
      <ProfileMatrix
        positions={[POSITION()]}
        profile={{ day_labels: {} }}
        onSave={vi.fn()}
        onDirtyChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: m.matrixEditHours }));
    fireEvent.change(screen.getByLabelText(m.end), { target: { value: '17:45' } });
    // A mousedown anywhere outside the popover root cancels it.
    fireEvent.mouseDown(document.body);

    expect(screen.queryByLabelText(m.end)).toBeNull();
    expect(screen.getByText(m.matrixHours('07:30', '15:00'))).toBeInTheDocument();
  });

  it('accepts an overnight window (end <= start) and shows the חוצה חצות hint [EDGE D2]', () => {
    render(
      <ProfileMatrix
        positions={[POSITION()]}
        profile={{ day_labels: {} }}
        onSave={vi.fn()}
        onDirtyChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: m.matrixEditHours }));
    fireEvent.change(screen.getByLabelText(m.start), { target: { value: '23:00' } });
    fireEvent.change(screen.getByLabelText(m.end), { target: { value: '07:00' } });

    // Hint visible and confirm NOT blocked (overnight is a valid window).
    expect(screen.getByText(m.matrixOvernightHint)).toBeInTheDocument();
    expect(screen.getByText(common.confirm)).not.toBeDisabled();

    fireEvent.click(screen.getByText(common.confirm));
    expect(screen.getByText(m.matrixHours('23:00', '07:00'))).toBeInTheDocument();
  });

  it('blocks confirm while a field is empty [EDGE D1]', () => {
    render(
      <ProfileMatrix
        positions={[POSITION()]}
        profile={{ day_labels: {} }}
        onSave={vi.fn()}
        onDirtyChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: m.matrixEditHours }));
    fireEvent.change(screen.getByLabelText(m.end), { target: { value: '' } });

    // Confirm disabled, cell still shows the original hours.
    expect(screen.getByText(common.confirm)).toBeDisabled();
    expect(screen.getByText(m.matrixHours('07:30', '15:00'))).toBeInTheDocument();
  });

  it('single click on the cell body still toggles (popover opens only via the pencil)', () => {
    render(
      <ProfileMatrix
        positions={[POSITION()]}
        profile={{ day_labels: {} }}
        onSave={vi.fn()}
        onDirtyChange={vi.fn()}
      />,
    );
    // Single click the active Sunday cell body → it toggles off; no popover.
    fireEvent.click(screen.getByRole('button', { name: cellName('ארנונה', 0, true) }));
    expect(screen.getByRole('button', { name: cellName('ארנונה', 0, false) })).toBeInTheDocument();
    expect(screen.queryByLabelText(m.end)).toBeNull();
  });

  it('double-clicking an OFF cell opens nothing — and does not park a popover for a later toggle', () => {
    render(
      <ProfileMatrix
        positions={[POSITION()]}
        profile={{ day_labels: {} }}
        onSave={vi.fn()}
        onDirtyChange={vi.fn()}
      />,
    );
    // Monday starts OFF. A real double-click = click(detail 1) + click(detail 2)
    // + dblclick; the two clicks toggle on→off, the dblclick must revert and
    // NOT open (the cell is off) nor remember an openCell for later.
    let cell = screen.getByRole('button', { name: cellName('ארנונה', 1, false) });
    fireEvent.click(cell, { detail: 1 });
    cell = screen.getByRole('button', { name: cellName('ארנונה', 1, true) });
    fireEvent.click(cell, { detail: 2 });
    cell = screen.getByRole('button', { name: cellName('ארנונה', 1, false) });
    fireEvent.dblClick(cell);
    expect(screen.getByRole('button', { name: cellName('ארנונה', 1, false) })).toBeInTheDocument();
    expect(screen.queryByLabelText(m.end)).toBeNull();
    // Toggling the cell on afterwards must not surprise-open the popover.
    fireEvent.click(screen.getByRole('button', { name: cellName('ארנונה', 1, false) }), { detail: 1 });
    expect(screen.getByRole('button', { name: cellName('ארנונה', 1, true) })).toBeInTheDocument();
    expect(screen.queryByLabelText(m.end)).toBeNull();
  });
});

// ── Step 06: multi-select + column operations ──────────────────────────────
describe('ProfileMatrix multi-select + column ops (step 06)', () => {
  const m = messages.positions;
  const common = messages.common;
  const hours = (s, e) => messages.positions.matrixHours(s, e);
  // Accessible name of a day-header chevron: "<יום> · תפריט יום".
  const chevName = (dayIdx) => `${DAY_NAMES[dayIdx]} · ${m.matrixDayMenu}`;

  // 3 positions, all active on Sunday — a clean single-column drag target.
  const THREE_ON_SUNDAY = [
    POSITION({ id: 'a', name: 'א', day_schedules: { 0: { start: '07:00', end: '15:00' } } }),
    POSITION({ id: 'b', name: 'ב', day_schedules: { 0: { start: '07:00', end: '15:00' } } }),
    POSITION({ id: 'c', name: 'ג', day_schedules: { 0: { start: '07:00', end: '15:00' } } }),
  ];

  it('drag-selects a 3-cell column; the cells stay active (drag does not toggle)', () => {
    render(
      <ProfileMatrix
        positions={THREE_ON_SUNDAY}
        profile={{ day_labels: {} }}
        onSave={vi.fn()}
        onDirtyChange={vi.fn()}
      />,
    );
    const a = screen.getByRole('button', { name: cellName('א', 0, true) });
    const b = screen.getByRole('button', { name: cellName('ב', 0, true) });
    const c = screen.getByRole('button', { name: cellName('ג', 0, true) });
    fireEvent.pointerDown(a, { pointerType: 'mouse', button: 0 });
    fireEvent.pointerEnter(b, { pointerType: 'mouse' });
    fireEvent.pointerEnter(c, { pointerType: 'mouse' });
    fireEvent.pointerUp(c, { pointerType: 'mouse', button: 0 });

    // 3 cells carry the selection outline; the action bar shows the count.
    expect(document.querySelectorAll('.profile-matrix-cell.is-selected')).toHaveLength(3);
    expect(screen.getByText(m.matrixSelCount(3))).toBeInTheDocument();
    // CRITICAL: the drag did NOT toggle — the cells are still active (not dirty).
    expect(screen.getByRole('button', { name: cellName('א', 0, true) })).toBeInTheDocument();
    expect(screen.getByText(m.matrixSave(0))).toBeInTheDocument();
  });

  it('"כבה" on the selection turns all 3 cells off and marks their rows dirty', () => {
    render(
      <ProfileMatrix
        positions={THREE_ON_SUNDAY}
        profile={{ day_labels: {} }}
        onSave={vi.fn()}
        onDirtyChange={vi.fn()}
      />,
    );
    const a = screen.getByRole('button', { name: cellName('א', 0, true) });
    const b = screen.getByRole('button', { name: cellName('ב', 0, true) });
    const c = screen.getByRole('button', { name: cellName('ג', 0, true) });
    fireEvent.pointerDown(a, { pointerType: 'mouse', button: 0 });
    fireEvent.pointerEnter(b, { pointerType: 'mouse' });
    fireEvent.pointerEnter(c, { pointerType: 'mouse' });
    fireEvent.pointerUp(c, { pointerType: 'mouse', button: 0 });

    fireEvent.click(screen.getByRole('button', { name: m.matrixSelOff }));

    // All three Sunday cells are now off (✕) and their rows dirty → שמירה (3).
    expect(screen.getByRole('button', { name: cellName('א', 0, false) })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: cellName('ב', 0, false) })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: cellName('ג', 0, false) })).toBeInTheDocument();
    expect(screen.getByText(m.matrixSave(3))).toBeInTheDocument();
  });

  it('ctrl/cmd+click builds a multi-cell selection one cell at a time', () => {
    render(
      <ProfileMatrix
        positions={THREE_ON_SUNDAY}
        profile={{ day_labels: {} }}
        onSave={vi.fn()}
        onDirtyChange={vi.fn()}
      />,
    );
    // No selection yet → no action bar.
    expect(screen.queryByRole('toolbar', { name: m.matrixSelBar })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: cellName('א', 0, true) }), { ctrlKey: true });
    // 1 cell → still below the ≥2 bar threshold.
    expect(screen.queryByRole('toolbar', { name: m.matrixSelBar })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: cellName('ג', 0, true) }), { ctrlKey: true });
    // 2 cells → bar appears, and neither cell was toggled (both still active).
    expect(screen.getByRole('toolbar', { name: m.matrixSelBar })).toBeInTheDocument();
    expect(screen.getByText(m.matrixSelCount(2))).toBeInTheDocument();
    expect(screen.getByRole('button', { name: cellName('א', 0, true) })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: cellName('ג', 0, true) })).toBeInTheDocument();
  });

  it('"קבע שעות…" on a mixed selection changes only the active cells', () => {
    // pos0 Sunday active; pos1 Sunday off. Select both Sundays via ctrl+click.
    const positions = [
      POSITION({ id: 'a', name: 'א', day_schedules: { 0: { start: '07:00', end: '15:00' } } }),
      POSITION({ id: 'b', name: 'ב', day_schedules: {} }),
    ];
    render(
      <ProfileMatrix positions={positions} profile={{ day_labels: {} }} onSave={vi.fn()} onDirtyChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole('button', { name: cellName('א', 0, true) }), { ctrlKey: true });
    fireEvent.click(screen.getByRole('button', { name: cellName('ב', 0, false) }), { ctrlKey: true });

    // Open the bulk-hours popover, set 08:00–16:00, confirm.
    fireEvent.click(screen.getByRole('button', { name: m.matrixSelHours }));
    fireEvent.change(screen.getByLabelText(m.start), { target: { value: '08:00' } });
    fireEvent.change(screen.getByLabelText(m.end), { target: { value: '16:00' } });
    fireEvent.click(screen.getByText(common.confirm));

    // Active cell got the new window; the off cell stayed off (✕).
    expect(screen.getByRole('button', { name: cellName('א', 0, true) })).toHaveTextContent(
      hours('08:00', '16:00'),
    );
    expect(screen.getByRole('button', { name: cellName('ב', 0, false) })).toBeInTheDocument();
  });

  it('column "כבה את כל היום" then "הדלק את כל היום" (restores snapshot hours)', () => {
    const positions = [
      POSITION({ id: 'a', name: 'א', day_schedules: { 4: { start: '07:00', end: '15:00' } } }),
      POSITION({ id: 'b', name: 'ב', day_schedules: { 4: { start: '08:00', end: '16:00' } } }),
    ];
    render(
      <ProfileMatrix positions={positions} profile={{ day_labels: {} }} onSave={vi.fn()} onDirtyChange={vi.fn()} />,
    );
    // Open Thursday's header menu → כבה את כל היום.
    fireEvent.click(screen.getByRole('button', { name: chevName(4) }));
    fireEvent.click(screen.getByText(m.matrixDayOff));
    expect(screen.getByRole('button', { name: cellName('א', 4, false) })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: cellName('ב', 4, false) })).toBeInTheDocument();

    // Reopen → הדלק את כל היום restores each cell's snapshot hours.
    fireEvent.click(screen.getByRole('button', { name: chevName(4) }));
    fireEvent.click(screen.getByText(m.matrixDayOn));
    expect(screen.getByRole('button', { name: cellName('א', 4, true) })).toHaveTextContent(
      hours('07:00', '15:00'),
    );
    expect(screen.getByRole('button', { name: cellName('ב', 4, true) })).toHaveTextContent(
      hours('08:00', '16:00'),
    );
  });

  it('column "קבע שעות לכל היום…" changes all active cells in the column', () => {
    const positions = [
      POSITION({ id: 'a', name: 'א', day_schedules: { 4: { start: '07:00', end: '15:00' } } }),
      POSITION({ id: 'b', name: 'ב', day_schedules: {} }), // Thursday off
    ];
    render(
      <ProfileMatrix positions={positions} profile={{ day_labels: {} }} onSave={vi.fn()} onDirtyChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole('button', { name: chevName(4) }));
    fireEvent.click(screen.getByText(m.matrixDayHours));
    fireEvent.change(screen.getByLabelText(m.start), { target: { value: '06:00' } });
    fireEvent.change(screen.getByLabelText(m.end), { target: { value: '18:00' } });
    fireEvent.click(screen.getByText(common.confirm));

    expect(screen.getByRole('button', { name: cellName('א', 4, true) })).toHaveTextContent(
      hours('06:00', '18:00'),
    );
    // The off cell in the column stays off.
    expect(screen.getByRole('button', { name: cellName('ב', 4, false) })).toBeInTheDocument();
  });

  it('a plain click (no drag) still toggles a single cell and clears the selection', () => {
    render(
      <ProfileMatrix
        positions={THREE_ON_SUNDAY}
        profile={{ day_labels: {} }}
        onSave={vi.fn()}
        onDirtyChange={vi.fn()}
      />,
    );
    // Build a 2-cell selection via ctrl+click, then a plain click elsewhere.
    fireEvent.click(screen.getByRole('button', { name: cellName('א', 0, true) }), { ctrlKey: true });
    fireEvent.click(screen.getByRole('button', { name: cellName('ג', 0, true) }), { ctrlKey: true });
    expect(screen.getByText(m.matrixSelCount(2))).toBeInTheDocument();

    // Plain click on pos1 Sunday → toggles it off and clears the selection.
    fireEvent.click(screen.getByRole('button', { name: cellName('ב', 0, true) }));
    expect(screen.getByRole('button', { name: cellName('ב', 0, false) })).toBeInTheDocument();
    expect(screen.queryByRole('toolbar', { name: m.matrixSelBar })).toBeNull();
  });

  it('the day-header menu closes on click-outside (another header opens one at a time)', () => {
    render(
      <ProfileMatrix
        positions={THREE_ON_SUNDAY}
        profile={{ day_labels: {} }}
        onSave={vi.fn()}
        onDirtyChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: chevName(0) }));
    expect(screen.getByText(m.matrixDayOff)).toBeInTheDocument();
    // Opening Tuesday's menu closes Sunday's (one menu at a time).
    fireEvent.click(screen.getByRole('button', { name: chevName(2) }));
    expect(screen.queryByText(m.matrixDayOff)).toBeInTheDocument(); // still one menu
    // A mousedown outside the menu closes it.
    fireEvent.mouseDown(document.body);
    expect(screen.queryByText(m.matrixDayOff)).toBeNull();
  });
});

// ── Step 07: header day-label editing ──────────────────────────────────────
describe('ProfileMatrix day-label editing (step 07)', () => {
  const m = messages.positions;
  // Accessible name of a day's label chip / "+ תווית" affordance / input:
  // "<יום> · <…>" (mirrors the chevron's naming).
  const chipName = (dayIdx) => `${DAY_NAMES[dayIdx]} · ${m.matrixEditDayLabel}`;
  const addName = (dayIdx) => `${DAY_NAMES[dayIdx]} · ${m.matrixAddDayLabel}`;

  it('clicking the label chip opens an inline input seeded with the label (max 50)', () => {
    render(
      <ProfileMatrix
        positions={[POSITION()]}
        profile={{ day_labels: { 4: 'ט׳ באב' } }}
        onSaveDayLabel={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: chipName(4) }));
    const input = screen.getByRole('textbox');
    expect(input).toHaveValue('ט׳ באב');
    expect(input.maxLength).toBe(50);
  });

  it('shows a "+ תווית" affordance that opens an empty input when no label is set', () => {
    render(
      <ProfileMatrix positions={[POSITION()]} profile={{ day_labels: {} }} onSaveDayLabel={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole('button', { name: addName(0) }));
    expect(screen.getByRole('textbox')).toHaveValue('');
  });

  it('Enter confirms and hands the day + value up via onSaveDayLabel exactly once', () => {
    const onSaveDayLabel = vi.fn().mockResolvedValue('ok');
    render(
      <ProfileMatrix positions={[POSITION()]} profile={{ day_labels: {} }} onSaveDayLabel={onSaveDayLabel} />,
    );
    fireEvent.click(screen.getByRole('button', { name: addName(2) }));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'מנחה' } });
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });

    // Exactly once — the input's unmount-blur must not double-commit.
    expect(onSaveDayLabel).toHaveBeenCalledTimes(1);
    expect(onSaveDayLabel).toHaveBeenCalledWith(2, 'מנחה');
  });

  it('clearing an existing label and pressing Enter requests removal (empty value)', () => {
    const onSaveDayLabel = vi.fn().mockResolvedValue('ok');
    render(
      <ProfileMatrix
        positions={[POSITION()]}
        profile={{ day_labels: { 4: 'ישן' } }}
        onSaveDayLabel={onSaveDayLabel}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: chipName(4) }));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '' } });
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });

    expect(onSaveDayLabel).toHaveBeenCalledWith(4, '');
  });

  it('Escape cancels without calling onSaveDayLabel and leaves the label intact', () => {
    const onSaveDayLabel = vi.fn();
    render(
      <ProfileMatrix
        positions={[POSITION()]}
        profile={{ day_labels: { 4: 'ט׳ באב' } }}
        onSaveDayLabel={onSaveDayLabel}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: chipName(4) }));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'אחר' } });
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Escape' });

    expect(onSaveDayLabel).not.toHaveBeenCalled();
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.getByText('ט׳ באב')).toBeInTheDocument();
  });

  it('does not PATCH when the value is unchanged (open + blur with the same text)', () => {
    const onSaveDayLabel = vi.fn();
    render(
      <ProfileMatrix
        positions={[POSITION()]}
        profile={{ day_labels: { 4: 'ט׳ באב' } }}
        onSaveDayLabel={onSaveDayLabel}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: chipName(4) }));
    // Blur without changing the seeded value → no PATCH.
    fireEvent.blur(screen.getByRole('textbox'));
    expect(onSaveDayLabel).not.toHaveBeenCalled();
  });
});
