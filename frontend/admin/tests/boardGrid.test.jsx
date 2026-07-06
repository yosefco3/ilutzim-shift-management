import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import BoardGrid from '../src/components/board/BoardGrid';

function cellsAllActive(start, end) {
  return Array.from({ length: 7 }, (_, d) => ({
    day_index: d,
    active: true,
    window: { start, end },
    is_override: false,
  }));
}

// א'–ה' (0..4) active; Thursday (idx 4) ends early -> override; ו'–ש' blocked.
function cellsWeekdaysWithOverride() {
  return Array.from({ length: 7 }, (_, d) => {
    if (d > 4) return { day_index: d, active: false, window: null, is_override: false };
    if (d === 4) {
      return { day_index: d, active: true, window: { start: '07:00', end: '14:00' }, is_override: true };
    }
    return { day_index: d, active: true, window: { start: '07:00', end: '15:00' }, is_override: false };
  });
}

const BOARD = {
  days: Array.from({ length: 7 }, (_, i) => ({
    index: i,
    date: `2026-07-${String(5 + i).padStart(2, '0')}`,
  })),
  rows: [
    {
      position_id: 'm1',
      name: 'אחמ"ש בוקר',
      band: 'morning',
      canonical_window: { start: '07:00', end: '15:00' },
      required_attributes: ['armed'],
      active_day_count: 7,
      cells: cellsAllActive('07:00', '15:00'),
    },
    {
      position_id: 'm2',
      name: 'ארנונה',
      band: 'morning',
      canonical_window: { start: '07:00', end: '15:00' },
      required_attributes: [],
      active_day_count: 5,
      cells: cellsWeekdaysWithOverride(),
    },
    {
      position_id: 'e1',
      name: 'רכב סיור',
      band: 'evening',
      canonical_window: { start: '19:00', end: '07:00' },
      required_attributes: [],
      active_day_count: 7,
      cells: cellsAllActive('19:00', '07:00'),
    },
    {
      position_id: 'n1',
      name: 'חמ"ל לילה',
      band: 'night',
      canonical_window: { start: '23:00', end: '07:00' },
      required_attributes: [],
      active_day_count: 7,
      cells: cellsAllActive('23:00', '07:00'),
    },
  ],
};

const attrLabel = (key) => ({ armed: 'חמוש' }[key] || key);

describe('BoardGrid', () => {
  it('renders a band group header for each band present', () => {
    render(<BoardGrid board={BOARD} attrLabel={attrLabel} />);
    expect(screen.getByText(/משמרת בוקר/)).toBeInTheDocument();
    expect(screen.getByText(/משמרת ערב/)).toBeInTheDocument();
    expect(screen.getByText(/משמרת לילה/)).toBeInTheDocument();
  });

  it('resolves requirement-attribute labels in chips', () => {
    render(<BoardGrid board={BOARD} attrLabel={attrLabel} />);
    expect(screen.getByText('חמוש')).toBeInTheDocument();
  });

  it('shows a compact active-days tag for a non-daily position', () => {
    render(<BoardGrid board={BOARD} attrLabel={attrLabel} />);
    expect(screen.getByText('א–ה')).toBeInTheDocument();
  });

  it('marks inactive days as blocked and shows per-day override windows', () => {
    render(<BoardGrid board={BOARD} attrLabel={attrLabel} />);
    expect(screen.getAllByText('╳').length).toBeGreaterThan(0); // ו'–ש' on ארנונה
    expect(screen.getByText(/07:00–14:00/)).toBeInTheDocument(); // Thursday override
  });

  // ── Drag-to-reorder position rows (within a band) ────────────────────
  function posHead(name) {
    return screen.getByText(name).closest('th');
  }
  function makeDataTransfer() {
    return {
      data: {},
      effectAllowed: '',
      dropEffect: '',
      setData(type, val) { this.data[type] = val; },
      getData(type) { return this.data[type]; },
    };
  }

  it('makes position rows draggable only when onReorderPositions is supplied', () => {
    const { container, rerender } = render(<BoardGrid board={BOARD} attrLabel={attrLabel} />);
    expect(posHead('אחמ"ש בוקר').getAttribute('draggable')).toBeNull();
    // No drag grip in read-only mode.
    expect(container.querySelector('.board-pos-grip')).toBeNull();

    rerender(<BoardGrid board={BOARD} attrLabel={attrLabel} onReorderPositions={vi.fn()} />);
    expect(posHead('אחמ"ש בוקר').getAttribute('draggable')).toBe('true');
    // A grip appears on each position row to signal it's draggable.
    expect(container.querySelectorAll('.board-pos-grip').length).toBe(BOARD.rows.length);
  });

  it('reorders within the same band on drop', () => {
    const onReorderPositions = vi.fn();
    render(<BoardGrid board={BOARD} attrLabel={attrLabel} onReorderPositions={onReorderPositions} />);
    const dataTransfer = makeDataTransfer();
    // Drag ארנונה (m2) up onto אחמ"ש בוקר (m1) — both morning band.
    fireEvent.dragStart(posHead('ארנונה'), { dataTransfer });
    fireEvent.drop(posHead('אחמ"ש בוקר'), { dataTransfer });
    // m2 lands before m1; other bands untouched.
    expect(onReorderPositions).toHaveBeenCalledWith(['m2', 'm1', 'e1', 'n1']);
  });

  it('rejects a drop onto a row in a different band', () => {
    const onReorderPositions = vi.fn();
    render(<BoardGrid board={BOARD} attrLabel={attrLabel} onReorderPositions={onReorderPositions} />);
    const dataTransfer = makeDataTransfer();
    // Drag אחמ"ש בוקר (morning) onto רכב סיור (evening) — cross-band, blocked.
    fireEvent.dragStart(posHead('אחמ"ש בוקר'), { dataTransfer });
    fireEvent.drop(posHead('רכב סיור'), { dataTransfer });
    expect(onReorderPositions).not.toHaveBeenCalled();
  });

  // ── Edit-position shortcut ───────────────────────────────────────────
  it('shows an edit button per row only when onEditPosition is supplied', () => {
    const { container, rerender } = render(<BoardGrid board={BOARD} attrLabel={attrLabel} />);
    expect(container.querySelector('.board-pos-edit')).toBeNull();

    rerender(<BoardGrid board={BOARD} attrLabel={attrLabel} onEditPosition={vi.fn()} />);
    expect(container.querySelectorAll('.board-pos-edit').length).toBe(BOARD.rows.length);
  });

  it('calls onEditPosition (and not onReorderPositions) when the edit button is clicked', () => {
    const onEditPosition = vi.fn();
    const onReorderPositions = vi.fn();
    render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        onEditPosition={onEditPosition}
        onReorderPositions={onReorderPositions}
      />,
    );
    const editBtn = within(posHead('ארנונה')).getByLabelText('ערוך עמדה');
    fireEvent.click(editBtn);
    expect(onEditPosition).toHaveBeenCalledWith('m2');
    expect(onReorderPositions).not.toHaveBeenCalled();
  });

  it('shows a delete button per row only when onDeletePosition is supplied', () => {
    const { container, rerender } = render(<BoardGrid board={BOARD} attrLabel={attrLabel} />);
    expect(container.querySelector('.board-pos-delete')).toBeNull();

    rerender(<BoardGrid board={BOARD} attrLabel={attrLabel} onDeletePosition={vi.fn()} />);
    expect(container.querySelectorAll('.board-pos-delete').length).toBe(BOARD.rows.length);
  });

  it('calls onDeletePosition (and not onReorderPositions) when the delete button is clicked', () => {
    const onDeletePosition = vi.fn();
    const onReorderPositions = vi.fn();
    render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        onDeletePosition={onDeletePosition}
        onReorderPositions={onReorderPositions}
      />,
    );
    const deleteBtn = within(posHead('ארנונה')).getByLabelText('מחק עמדה');
    fireEvent.click(deleteBtn);
    expect(onDeletePosition).toHaveBeenCalledWith('m2');
    expect(onReorderPositions).not.toHaveBeenCalled();
  });

  it('stays read-only (no add buttons) when no assignment handlers are passed', () => {
    render(<BoardGrid board={BOARD} attrLabel={attrLabel} />);
    expect(screen.queryByLabelText('שבץ מאבטח')).toBeNull();
  });

  it('opens the candidate modal and assigns the picked guard', () => {
    const onAssign = vi.fn();
    // Available 07:00–15:00 on Sunday → shows up for אחמ"ש בוקר's Sunday cell.
    const pool = [{ id: 'u1', full_name: 'נתן כהן', roles: ['ARMED'], remaining_hours: 8, availability: { 0: [{ start: '07:00', end: '15:00' }] } }];
    render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={pool}
        assignmentsByCell={{}}
        onAssign={onAssign}
        onUnassign={vi.fn()}
      />,
    );
    fireEvent.click(screen.getAllByLabelText('שבץ מאבטח')[0]);
    const dialog = screen.getByRole('dialog', { name: 'מי זמין לחלון' });
    fireEvent.click(within(dialog).getByText('נתן כהן'));
    expect(onAssign).toHaveBeenCalledWith('m1', 0, 'u1');
  });

  it('hides a guard from the picker of another cell in the shift they already fill (075)', () => {
    // u1 is assigned to m1 (morning) on Sunday. Opening the picker for ארנונה (m2),
    // the same morning band+day, must NOT list u1 — even though they're available
    // for that window — because a guard is never placed twice in one shift.
    const pool = [
      { id: 'u1', full_name: 'נתן כהן', roles: ['ARMED'], remaining_hours: 8, availability: { 0: [{ start: '07:00', end: '15:00' }] } },
      { id: 'u2', full_name: 'מאי לוי', roles: [], remaining_hours: 8, availability: { 0: [{ start: '07:00', end: '15:00' }] } },
    ];
    const { container } = render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={pool}
        assignmentsByCell={{
          'm1:0': [{ id: 'a1', position_id: 'm1', day_index: 0, user_id: 'u1', user_full_name: 'נתן כהן' }],
        }}
        onAssign={vi.fn()}
        onUnassign={vi.fn()}
      />,
    );
    // Open ארנונה (m2) Sunday picker — first active cell in that row is Sunday.
    const m2Row = [...container.querySelectorAll('tr.board-row')].find(
      (tr) => tr.querySelector('.board-pos-name')?.textContent === 'ארנונה',
    );
    fireEvent.click(within(m2Row).getAllByLabelText('שבץ מאבטח')[0]);
    const dialog = screen.getByRole('dialog', { name: 'מי זמין לחלון' });
    expect(within(dialog).queryByText('נתן כהן')).toBeNull(); // already in this shift
    expect(within(dialog).getByText('מאי לוי')).toBeInTheDocument(); // free to place
  });

  it('still lists a guard in the picker of a different shift on the same day (075)', () => {
    // u1 fills m1 (morning) on Sunday but is also available in the evening — opening
    // the picker for רכב סיור (e1, evening band, same Sunday) must still list them.
    const pool = [
      { id: 'u1', full_name: 'נתן כהן', roles: ['ARMED'], remaining_hours: 8, availability: { 0: [{ start: '19:00', end: '07:00' }] } },
    ];
    const { container } = render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={pool}
        assignmentsByCell={{
          'm1:0': [{ id: 'a1', position_id: 'm1', day_index: 0, user_id: 'u1', user_full_name: 'נתן כהן' }],
        }}
        onAssign={vi.fn()}
        onUnassign={vi.fn()}
      />,
    );
    // רכב סיור (e1, evening) Sunday is a different shift → u1 stays listed.
    const e1Row = [...container.querySelectorAll('tr.board-row')].find(
      (tr) => tr.querySelector('.board-pos-name')?.textContent === 'רכב סיור',
    );
    fireEvent.click(within(e1Row).getAllByLabelText('שבץ מאבטח')[0]);
    const dialog = screen.getByRole('dialog', { name: 'מי זמין לחלון' });
    expect(within(dialog).getByText('נתן כהן')).toBeInTheDocument();
  });

  it('colours cells by the selected guard coverage and assigns on click', () => {
    const onAssign = vi.fn();
    // Guard available all day on Sunday (day 0); ארנונה Sun window 07:00–15:00.
    const selectedGuard = {
      id: 'u1',
      roles: ['ARMED'], // m1 (אחמ"ש בוקר) requires 'armed'
      availability: { 0: [{ start: '07:00', end: '15:00' }] },
    };
    const { container } = render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={[selectedGuard]}
        assignmentsByCell={{}}
        selectedGuard={selectedGuard}
        onAssign={onAssign}
        onUnassign={vi.fn()}
      />,
    );
    // First fully-covered Sunday cell (אחמ"ש בוקר, 07:00–15:00) → placeable.
    const fullCell = container.querySelector('.board-cell.cov-full.placeable');
    expect(fullCell).not.toBeNull();
    fireEvent.click(fullCell);
    expect(onAssign).toHaveBeenCalledWith('m1', 0, 'u1');
  });

  it('leaves cells uncoloured but still placeable when the guard lacks the required attribute', () => {
    // Available all day Sunday, but holds no roles → can't fill m1 (requires armed).
    const selectedGuard = {
      id: 'u1',
      roles: [],
      availability: { 0: [{ start: '07:00', end: '15:00' }] },
    };
    const onAssign = vi.fn();
    const { container } = render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={[selectedGuard]}
        assignmentsByCell={{}}
        selectedGuard={selectedGuard}
        onAssign={onAssign}
        onUnassign={vi.fn()}
      />,
    );
    // Find the m1 row (אחמ"ש בוקר, requires armed). The attribute gate suppresses the
    // coverage colour (no "good fit" wash), but the missing attribute is a soft
    // warning — the cell stays a clickable override (placeable-warn, not placeable).
    const m1Row = [...container.querySelectorAll('tr.board-row')].find((tr) =>
      tr.querySelector('.board-pos-name')?.textContent === 'אחמ"ש בוקר',
    );
    const m1Cells = m1Row.querySelectorAll('.board-cell.active');
    expect(m1Cells.length).toBeGreaterThan(0);
    m1Cells.forEach((c) => {
      expect(c.className).not.toMatch(/cov-(full|partial|none)/);
      expect(c.classList.contains('placeable')).toBe(false);
      expect(c.classList.contains('placeable-warn')).toBe(true);
    });
    // Placing anyway is allowed — it will raise a missing_attribute warning.
    fireEvent.click(m1Cells[0]);
    expect(onAssign).toHaveBeenCalledWith('m1', 0, 'u1');
  });

  it('suppresses the coverage colour across a shift once the guard is used in it (075)', () => {
    // u1 (armed, available all Sunday) is already assigned to m1 (morning) on Sun.
    const selectedGuard = {
      id: 'u1',
      roles: ['ARMED'],
      availability: { 0: [{ start: '07:00', end: '15:00' }] },
    };
    const onAssign = vi.fn();
    const { container } = render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={[selectedGuard]}
        assignmentsByCell={{
          'm1:0': [{ id: 'a1', position_id: 'm1', day_index: 0, user_id: 'u1', user_full_name: 'נתן' }],
        }}
        selectedGuard={selectedGuard}
        onAssign={onAssign}
        onUnassign={vi.fn()}
      />,
    );
    // ארנונה (m2) Sunday is the same morning band + day → colour gone, but the
    // cell stays clickable as a deliberate override (placeable-warn, not placeable).
    const m2Row = [...container.querySelectorAll('tr.board-row')].find(
      (tr) => tr.querySelector('.board-pos-name')?.textContent === 'ארנונה',
    );
    const m2Sun = m2Row.querySelectorAll('.board-cell.active')[0];
    expect(m2Sun.className).not.toMatch(/cov-(full|partial|none)/);
    expect(m2Sun.classList.contains('placeable')).toBe(false);
    expect(m2Sun.classList.contains('placeable-warn')).toBe(true);
    // Override still works: clicking assigns the guard again (warning, not a block).
    fireEvent.click(m2Sun);
    expect(onAssign).toHaveBeenCalledWith('m2', 0, 'u1');
  });

  it('keeps the colour in other shifts / other days when used in one shift (075)', () => {
    const selectedGuard = {
      id: 'u1',
      roles: ['ARMED'],
      availability: {
        0: [{ start: '07:00', end: '15:00' }], // Sunday morning
        1: [{ start: '07:00', end: '15:00' }], // Monday morning
      },
    };
    const { container } = render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={[selectedGuard]}
        assignmentsByCell={{
          'm1:0': [{ id: 'a1', position_id: 'm1', day_index: 0, user_id: 'u1', user_full_name: 'נתן' }],
        }}
        selectedGuard={selectedGuard}
        onAssign={vi.fn()}
        onUnassign={vi.fn()}
      />,
    );
    // ארנונה Monday (same morning band, different day) keeps its coverage colour.
    const m2Row = [...container.querySelectorAll('tr.board-row')].find(
      (tr) => tr.querySelector('.board-pos-name')?.textContent === 'ארנונה',
    );
    const m2Mon = m2Row.querySelectorAll('.board-cell.active')[1];
    expect(m2Mon.className).toMatch(/cov-full/);
  });

  it('marks a cell the selected guard cannot cover as cov-none but still placeable (override)', () => {
    // Available nowhere → on any position they meet the attributes for, coverage is
    // computed as 'none' (an attribute-free position always qualifies).
    const selectedGuard = { id: 'u1', availability: {} };
    const onAssign = vi.fn();
    const { container } = render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={[selectedGuard]}
        assignmentsByCell={{}}
        selectedGuard={selectedGuard}
        onAssign={onAssign}
        onUnassign={vi.fn()}
      />,
    );
    // Out of availability everywhere: cells wear cov-none (no blue "good fit" wash)
    // but stay a clickable override — placement is allowed and raises a soft warning.
    const noneCell = container.querySelector('.board-cell.cov-none');
    expect(noneCell).not.toBeNull();
    expect(noneCell.classList.contains('placeable')).toBe(false);
    expect(noneCell.classList.contains('placeable-warn')).toBe(true);
    expect(container.querySelector('.board-cell.placeable')).toBeNull();
    fireEvent.click(noneCell);
    expect(onAssign).toHaveBeenCalled();
  });

  it('renders a hard soft-warning badge on a flagged assigned cell', () => {
    const { container } = render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={[]}
        assignmentsByCell={{
          'm1:0': [
            { id: 'a1', position_id: 'm1', day_index: 0, user_id: 'u1', user_full_name: 'נתן כהן', user_roles: [] },
          ],
        }}
        onAssign={vi.fn()}
        onUnassign={vi.fn()}
        warnings={{
          byCell: {
            'm1:0': [
              { type: 'out_of_availability', guardId: 'u1', guardName: 'נתן כהן' },
              { type: 'missing_attribute', guardId: 'u1', guardName: 'נתן כהן', missing: ['armed'] },
            ],
          },
          byGuard: {},
        }}
      />,
    );
    expect(container.querySelector('.board-cell.has-warn-hard')).not.toBeNull();
    expect(screen.getByText(/משובץ מחוץ לזמינותו/)).toBeInTheDocument();
    // missing attribute resolves through attrLabel (armed → חמוש)
    expect(screen.getByText(/חסר מאפיין נדרש: חמוש/)).toBeInTheDocument();
  });

  it('renders an event (non-splitting) cell with N guards, no divider, no coverage colour', () => {
    const eventBoard = {
      days: BOARD.days,
      rows: [
        {
          position_id: 'ev1',
          name: 'רענון',
          band: 'morning',
          canonical_window: { start: '07:00', end: '15:00' },
          required_attributes: [],
          is_event: true,
          active_day_count: 7,
          cells: cellsAllActive('07:00', '15:00'),
        },
      ],
    };
    const { container } = render(
      <BoardGrid
        board={eventBoard}
        attrLabel={attrLabel}
        pool={[]}
        assignmentsByCell={{
          'ev1:0': [
            { id: 'a1', position_id: 'ev1', day_index: 0, user_id: 'u1', user_full_name: 'נתן' },
            { id: 'a2', position_id: 'ev1', day_index: 0, user_id: 'u2', user_full_name: 'מאי' },
            { id: 'a3', position_id: 'ev1', day_index: 0, user_id: 'u3', user_full_name: 'רון' },
          ],
        }}
        onAssign={vi.fn()}
        onUnassign={vi.fn()}
      />,
    );
    const sunday = container.querySelector('.board-cell-event');
    expect(sunday).toBeTruthy();
    // Three guards share the window — all names shown, no split divider.
    expect(within(sunday).getByText('נתן')).toBeInTheDocument();
    expect(within(sunday).getByText('מאי')).toBeInTheDocument();
    expect(within(sunday).getByText('רון')).toBeInTheDocument();
    expect(sunday.querySelector('.board-cell-split')).toBeNull();
    // No coverage colour is applied to an event cell.
    expect(sunday.className).not.toMatch(/cov-/);
  });

  it('surfaces a per-guard policy warning on each involved cell', () => {
    const { container } = render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={[]}
        assignmentsByCell={{
          'm1:0': [
            { id: 'a1', position_id: 'm1', day_index: 0, user_id: 'u1', user_full_name: 'נתן כהן', user_roles: ['armed'] },
          ],
        }}
        onAssign={vi.fn()}
        onUnassign={vi.fn()}
        warnings={{
          byCell: {},
          byGuard: {
            u1: [{ type: 'over_continuous_hours', guardId: 'u1', guardName: 'נתן כהן', hours: 15, cells: ['m1:0'] }],
          },
        }}
      />,
    );
    expect(container.querySelector('.board-cell.has-warn-hard')).not.toBeNull();
    expect(screen.getByText(/מעל 12ש׳ רצופות/)).toBeInTheDocument();
  });

  it('shows no warning badge for a clean assignment', () => {
    const { container } = render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={[]}
        assignmentsByCell={{
          'm1:0': [
            { id: 'a1', position_id: 'm1', day_index: 0, user_id: 'u1', user_full_name: 'נתן כהן', user_roles: ['armed'] },
          ],
        }}
        onAssign={vi.fn()}
        onUnassign={vi.fn()}
        warnings={{ byCell: {}, byGuard: {} }}
      />,
    );
    expect(container.querySelector('.board-warn')).toBeNull();
  });

  it('accepts a guard dropped on an empty cell (assign via drag-and-drop)', () => {
    const onAssign = vi.fn();
    const { container } = render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={[]}
        assignmentsByCell={{}}
        onAssign={onAssign}
        onUnassign={vi.fn()}
      />,
    );
    const cell = container.querySelector('.board-cell.active');
    fireEvent.dragOver(cell, { dataTransfer: {} });
    expect(cell.className).toMatch(/drag-over/);
    fireEvent.dragLeave(cell);
    expect(cell.className).not.toMatch(/drag-over/);
    fireEvent.drop(cell, { dataTransfer: { getData: () => 'u7' } });
    expect(onAssign).toHaveBeenCalledWith('m1', 0, 'u7');
  });

  it('does not accept a drop on a full (two-guard) cell', () => {
    const onAssign = vi.fn();
    const { container } = render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={[]}
        assignmentsByCell={{
          'm1:0': [
            { id: 'a1', position_id: 'm1', day_index: 0, user_id: 'u1', user_full_name: 'נתן', user_roles: [], segment_start: '07:00', segment_end: '11:00' },
            { id: 'a2', position_id: 'm1', day_index: 0, user_id: 'u2', user_full_name: 'מאי', user_roles: [], segment_start: '11:00', segment_end: '15:00' },
          ],
        }}
        onAssign={onAssign}
        onUnassign={vi.fn()}
      />,
    );
    const m1Row = [...container.querySelectorAll('tr.board-row')].find(
      (tr) => tr.querySelector('.board-pos-name')?.textContent === 'אחמ"ש בוקר',
    );
    const fullCell = m1Row.querySelectorAll('.board-cell.active')[0];
    fireEvent.drop(fullCell, { dataTransfer: { getData: () => 'u7' } });
    expect(onAssign).not.toHaveBeenCalled();
  });

  it('paints a fully-tiled split cell cov-full with עד/מ- labels', () => {
    const { container } = render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={[]}
        assignmentsByCell={{
          'm1:0': [
            { id: 'a1', position_id: 'm1', day_index: 0, user_id: 'u1', user_full_name: 'נתן', user_roles: [], segment_start: '07:00', segment_end: '11:00' },
            { id: 'a2', position_id: 'm1', day_index: 0, user_id: 'u2', user_full_name: 'מאי', user_roles: [], segment_start: '11:00', segment_end: '15:00' },
          ],
        }}
        onAssign={vi.fn()}
        onUnassign={vi.fn()}
      />,
    );
    expect(container.querySelector('.board-cell.cov-full')).not.toBeNull();
    expect(screen.getByText(/עד 11:00/)).toBeInTheDocument();
    expect(screen.getByText('מ-11:00')).toBeInTheDocument();
  });

  it('paints a single partial segment cov-partial and shows the remaining gap', () => {
    const { container } = render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={[]}
        assignmentsByCell={{
          'm1:0': [
            { id: 'a1', position_id: 'm1', day_index: 0, user_id: 'u1', user_full_name: 'נתן', user_roles: [], segment_start: '07:00', segment_end: '11:00' },
          ],
        }}
        onAssign={vi.fn()}
        onUnassign={vi.fn()}
      />,
    );
    expect(container.querySelector('.board-cell.cov-partial')).not.toBeNull();
    expect(screen.getByText(/נותר 11:00–15:00/)).toBeInTheDocument();
  });

  it('renders a draggable divider on a lone partial cell and commits a new segment', () => {
    const onPartialChange = vi.fn();
    const { container } = render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={[]}
        assignmentsByCell={{
          'm1:0': [
            { id: 'a1', position_id: 'm1', day_index: 0, user_id: 'u1', user_full_name: 'נתן', user_roles: [], segment_start: '07:00', segment_end: '11:00' },
          ],
        }}
        onAssign={vi.fn()}
        onUnassign={vi.fn()}
        onPartialChange={onPartialChange}
      />,
    );
    // The guard sits above an amber gap zone, split by a draggable handle.
    expect(container.querySelector('.board-cell-split-gap')).not.toBeNull();
    const handle = container.querySelector('.board-cell-split-handle');
    expect(handle).not.toBeNull();
    // Nudging the divider down by one 30-min step extends נתן 11:00 → 11:30; the
    // commit fires on key release (F-low: no PATCH storm while a key is held).
    fireEvent.keyDown(handle, { key: 'ArrowDown' });
    fireEvent.keyUp(handle, { key: 'ArrowDown' });
    expect(onPartialChange).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'a1' }),
      { start: '07:00', end: '11:30' },
    );
  });

  it('commits a whole-window segment when the divider is dragged to the cell edge', () => {
    const onPartialChange = vi.fn();
    const { container } = render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={[]}
        assignmentsByCell={{
          'm1:0': [
            { id: 'a1', position_id: 'm1', day_index: 0, user_id: 'u1', user_full_name: 'נתן', user_roles: [], segment_start: '07:00', segment_end: '11:00' },
          ],
        }}
        onAssign={vi.fn()}
        onUnassign={vi.fn()}
        onPartialChange={onPartialChange}
      />,
    );
    const split = container.querySelector('.board-cell-split');
    // jsdom has no layout — give the container a concrete box so moveTo() can map
    // clientY→offset (window 07:00–15:00 = 480 min, so 1px = 1min here).
    split.getBoundingClientRect = () => ({ top: 0, height: 480, left: 0, width: 10, right: 10, bottom: 480 });
    const handle = container.querySelector('.board-cell-split-handle');
    // Grab the end handle and drag it to the bottom edge (15:00). The guard then
    // fills the whole cell, which unmounts the handle mid-drag — the commit must
    // still fire from the container's pointerup (regression: extend-to-fill was
    // silently dropped when capture lived on the now-unmounted handle).
    fireEvent.pointerDown(handle, { pointerId: 1 });
    fireEvent.pointerMove(split, { pointerId: 1, clientY: 480 });
    fireEvent.pointerUp(split, { pointerId: 1, clientY: 480 });
    expect(onPartialChange).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'a1' }),
      { start: '07:00', end: '15:00' },
    );
  });

  it('renders the assigned guard chip and removes it on click', () => {
    const onUnassign = vi.fn();
    render(
      <BoardGrid
        board={BOARD}
        attrLabel={attrLabel}
        pool={[]}
        assignmentsByCell={{
          'm1:0': [
            {
              id: 'a1',
              position_id: 'm1',
              day_index: 0,
              user_id: 'u1',
              user_full_name: 'נתן כהן',
              user_roles: ['armed'],
            },
          ],
        }}
        onAssign={vi.fn()}
        onUnassign={onUnassign}
      />,
    );
    expect(screen.getByText('נתן כהן')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('הסר שיבוץ'));
    expect(onUnassign).toHaveBeenCalledWith('a1');
  });

  // A fixed-count event board with one event row (מועצה, 4 required).
  const EVENT_BOARD = {
    days: BOARD.days,
    rows: [
      {
        position_id: 'ev1',
        name: 'מועצה',
        band: 'morning',
        canonical_window: { start: '07:00', end: '15:00' },
        required_attributes: [],
        is_event: true,
        event_required_count: 4,
        active_day_count: 7,
        cells: cellsAllActive('07:00', '15:00'),
      },
    ],
  };

  it('renders a "חסר מאבטח" slot per missing participant on a fixed-count event', () => {
    const { container } = render(
      <BoardGrid
        board={EVENT_BOARD}
        attrLabel={attrLabel}
        assignmentsByCell={{
          'ev1:0': [
            { id: 'a1', position_id: 'ev1', day_index: 0, user_id: 'u1', user_full_name: 'אבי כהן' },
            { id: 'a2', position_id: 'ev1', day_index: 0, user_id: 'u2', user_full_name: 'דנה לוי' },
          ],
        }}
        onAssign={vi.fn()}
        onUnassign={vi.fn()}
      />,
    );
    // Sunday cell: 2 of 4 filled → 2 "חסר מאבטח" placeholders + understaffed class.
    const sundayCell = container.querySelector('.board-cell.board-cell-event');
    expect(sundayCell.classList.contains('board-cell-understaffed')).toBe(true);
    expect(within(sundayCell).getAllByText('חסר מאבטח')).toHaveLength(2);
  });

  it('shows no missing slots once a fixed-count event is fully staffed', () => {
    const { container } = render(
      <BoardGrid
        board={EVENT_BOARD}
        attrLabel={attrLabel}
        assignmentsByCell={{
          'ev1:0': [
            { id: 'a1', position_id: 'ev1', day_index: 0, user_id: 'u1', user_full_name: 'א' },
            { id: 'a2', position_id: 'ev1', day_index: 0, user_id: 'u2', user_full_name: 'ב' },
            { id: 'a3', position_id: 'ev1', day_index: 0, user_id: 'u3', user_full_name: 'ג' },
            { id: 'a4', position_id: 'ev1', day_index: 0, user_id: 'u4', user_full_name: 'ד' },
          ],
        }}
        onAssign={vi.fn()}
        onUnassign={vi.fn()}
      />,
    );
    const sundayCell = container.querySelector('.board-cell.board-cell-event');
    expect(sundayCell.classList.contains('board-cell-understaffed')).toBe(false);
    expect(within(sundayCell).queryByText('חסר מאבטח')).toBeNull();
  });
});
