import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../src/api/builderApiClient', () => ({
  listProfiles: vi.fn(),
  listAttributes: vi.fn(),
  getNextWeekBoard: vi.fn(),
  setWeekProfile: vi.fn(),
  getPool: vi.fn(),
  getAssignments: vi.fn(),
  createAssignment: vi.fn(),
  updateAssignmentSegment: vi.fn(),
  deleteAssignment: vi.fn(),
  deletePosition: vi.fn(),
  saveSchedule: vi.fn(),
}));
const toast = { success: vi.fn(), error: vi.fn() };
vi.mock('../src/components/Toast', () => ({ useToast: () => toast }));

import {
  listProfiles,
  listAttributes,
  getNextWeekBoard,
  setWeekProfile,
  getPool,
  getAssignments,
  createAssignment,
  updateAssignmentSegment,
  deleteAssignment,
  deletePosition,
  saveSchedule,
} from '../src/api/builderApiClient';
import BoardPage from '../src/pages/builder/BoardPage';

const POOL = [
  {
    id: 'u1',
    full_name: 'נתן כהן',
    roles: ['ARMED'],
    remaining_hours: 12,
    notes: null,
    availability: { 0: [{ start: '07:00', end: '15:00' }] },
  },
  {
    id: 'u2',
    full_name: 'רון לוי',
    roles: [],
    remaining_hours: 8,
    notes: null,
    availability: {},
  },
];

const PROFILES = [
  { id: 'p1', name: 'שגרה', is_default: true },
  { id: 'p2', name: 'חג', is_default: false },
];

function makeBoard(overrides = {}) {
  return {
    week: { id: 'w1', start_date: '2026-07-05', end_date: '2026-07-11', status: 'OPEN' },
    profile: { id: 'p1', name: 'שגרה', is_default: true },
    is_default_fallback: true,
    days: Array.from({ length: 7 }, (_, i) => ({
      index: i,
      date: `2026-07-${String(5 + i).padStart(2, '0')}`,
    })),
    rows: [
      {
        position_id: 'pos1',
        name: 'ארנונה',
        band: 'morning',
        canonical_window: { start: '07:00', end: '15:00' },
        required_attributes: ['armed'],
        active_day_count: 5,
        cells: Array.from({ length: 7 }, (_, d) => ({
          day_index: d,
          active: d < 5,
          window: d < 5 ? { start: '07:00', end: '15:00' } : null,
          is_override: false,
        })),
      },
    ],
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <BoardPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listProfiles.mockResolvedValue(PROFILES);
  listAttributes.mockResolvedValue([{ id: 'a1', key: 'armed', label: 'חמוש' }]);
  getNextWeekBoard.mockResolvedValue(makeBoard());
  setWeekProfile.mockResolvedValue({});
  getPool.mockResolvedValue(POOL);
  getAssignments.mockResolvedValue([]);
  createAssignment.mockResolvedValue({});
  updateAssignmentSegment.mockResolvedValue({});
  deleteAssignment.mockResolvedValue();
  deletePosition.mockResolvedValue();
  saveSchedule.mockResolvedValue({ week_id: 'w1', profile_name: 'שגרה', saved_at: '2026-07-01T12:00:00' });
});

describe('BoardPage', () => {
  it('loads the next week and renders the positions × days grid', async () => {
    renderPage();
    expect(await screen.findByText('ארנונה')).toBeInTheDocument();
    expect(getNextWeekBoard).toHaveBeenCalled();
    // the next week is shown as a fixed label, not a picker
    expect(screen.getByText('📅 2026-07-05 — 2026-07-11')).toBeInTheDocument();
    expect(screen.getByText('ראשון')).toBeInTheDocument();
    expect(screen.getByText('שבת')).toBeInTheDocument();
    expect(screen.getByText('07:00–15:00')).toBeInTheDocument();
  });

  it('deletes a position only after confirming the warning', async () => {
    renderPage();
    await screen.findByText('ארנונה');

    // Trash icon opens the confirm; nothing is deleted yet.
    fireEvent.click(screen.getByLabelText('מחק עמדה'));
    expect(deletePosition).not.toHaveBeenCalled();
    expect(screen.getByText('מחיקת עמדה')).toBeInTheDocument();

    // Confirming (the danger button inside the modal) deletes and reloads.
    getNextWeekBoard.mockClear();
    const modal = document.querySelector('.modal-content');
    fireEvent.click(within(modal).getByRole('button', { name: 'מחק עמדה' }));
    await waitFor(() => expect(deletePosition).toHaveBeenCalledWith('pos1'));
    await waitFor(() => expect(getNextWeekBoard).toHaveBeenCalled());
    expect(toast.success).toHaveBeenCalledWith('העמדה נמחקה');
  });

  it('does not delete the position when the warning is cancelled', async () => {
    renderPage();
    await screen.findByText('ארנונה');
    fireEvent.click(screen.getByLabelText('מחק עמדה'));
    fireEvent.click(screen.getByRole('button', { name: 'ביטול' }));
    expect(deletePosition).not.toHaveBeenCalled();
    expect(screen.queryByText('מחיקת עמדה')).toBeNull();
  });

  it('shows the default-fallback note when the week is unassigned', async () => {
    renderPage();
    expect(await screen.findByText('משויך אוטומטית לברירת-המחדל')).toBeInTheDocument();
  });

  it('auto-saves the schedule snapshot after an edit (no manual button)', async () => {
    renderPage();
    await screen.findByText('ארנונה');
    // The manual "save schedule" button is gone — saving is automatic now.
    expect(screen.queryByText('💾 שמור סידור')).toBeNull();
    // A real edit (here a profile change) triggers a debounced background
    // snapshot save; success is silent, only failures would toast.
    const profileSelect = screen.getByDisplayValue('שגרה');
    fireEvent.change(profileSelect, { target: { value: 'p2' } });
    await waitFor(() => expect(saveSchedule).toHaveBeenCalledWith('w1'), { timeout: 2500 });
  });

  it('assigns a profile to the next week when the selector changes', async () => {
    renderPage();
    await screen.findByText('ארנונה');
    const profileSelect = screen.getByDisplayValue('שגרה');
    fireEvent.change(profileSelect, { target: { value: 'p2' } });
    await waitFor(() => expect(setWeekProfile).toHaveBeenCalledWith('w1', 'p2'));
  });

  it('dragging the divider in a split cell PATCHes both segments with complementary edges', async () => {
    getAssignments.mockResolvedValue([
      { id: 'a1', position_id: 'pos1', day_index: 0, user_id: 'u1', user_full_name: 'נתן', user_roles: ['armed'], segment_start: '07:00', segment_end: '11:00' },
      { id: 'a2', position_id: 'pos1', day_index: 0, user_id: 'u2', user_full_name: 'רון', user_roles: [], segment_start: '11:00', segment_end: '15:00' },
    ]);
    const { container } = renderPage();
    await screen.findByText('ארנונה');
    const handle = await waitFor(() => {
      const h = container.querySelector('.board-cell-split-handle');
      if (!h) throw new Error('no split handle yet');
      return h;
    });
    fireEvent.keyDown(handle, { key: 'ArrowDown' }); // 11:00 → 11:30 (local)
    fireEvent.keyUp(handle, { key: 'ArrowDown' });   // commit on release (F-low)
    await waitFor(() => {
      expect(updateAssignmentSegment).toHaveBeenCalledWith('a1', { segment_start: '07:00', segment_end: '11:30' });
      expect(updateAssignmentSegment).toHaveBeenCalledWith('a2', { segment_start: '11:30', segment_end: '15:00' });
    });
  });

  it('clears the pool selection on Escape (board stops being coloured)', async () => {
    const { container } = renderPage();
    await screen.findByText('ארנונה');
    fireEvent.click(screen.getByText('נתן כהן'));
    await waitFor(() =>
      expect(container.querySelector('.board-cell.cov-full.placeable')).not.toBeNull(),
    );
    fireEvent.keyDown(document.body, { key: 'Escape' });
    await waitFor(() => expect(container.querySelector('.board-cell.placeable')).toBeNull());
  });

  it('hides a guard from the pool and restores them', async () => {
    renderPage();
    await screen.findByText('נתן כהן');
    fireEvent.click(screen.getAllByLabelText('הסתר מהמאגר')[0]);
    await waitFor(() => expect(screen.getByText(/הוסתרו/)).toBeInTheDocument());
    fireEvent.click(screen.getByTitle('החזר למאגר'));
    await waitFor(() => expect(screen.queryByText(/הוסתרו/)).toBeNull());
  });

  it('renders a guiding empty state when the next week does not exist', async () => {
    // The backend surfaces the real reason; the empty state echoes it verbatim.
    getNextWeekBoard.mockRejectedValue(
      new Error('השבוע הבא טרם נוצר — צור אותו במסך השבועות'),
    );
    renderPage();
    expect(
      await screen.findByText('השבוע הבא טרם נוצר — צור אותו במסך השבועות'),
    ).toBeInTheDocument();
  });

  it('shows the real failure reason in the empty state (not the generic week message)', async () => {
    // Regression: a non-week failure (e.g. no profile configured) must not be
    // masked by the hardcoded "next week not created" guidance.
    getNextWeekBoard.mockRejectedValue(new Error('פרופיל לא נמצא'));
    renderPage();
    expect(await screen.findByText('פרופיל לא נמצא')).toBeInTheDocument();
    expect(
      screen.queryByText('השבוע הבא טרם נוצר — צור אותו במסך השבועות'),
    ).toBeNull();
  });

  it('loads the pool + assignments for the resolved week', async () => {
    renderPage();
    await screen.findByText('ארנונה');
    await waitFor(() => expect(getPool).toHaveBeenCalledWith('w1'));
    expect(getAssignments).toHaveBeenCalledWith('w1');
  });

  it('opens the candidate modal and assigns the picked guard (no guard selected)', async () => {
    renderPage();
    await screen.findByText('ארנונה');
    // Open the first active cell's picker modal, then pick a candidate.
    const addButtons = screen.getAllByLabelText('שבץ מאבטח');
    fireEvent.click(addButtons[0]);
    const dialog = screen.getByRole('dialog', { name: 'מי זמין לחלון' });
    fireEvent.click(within(dialog).getByText('נתן כהן'));
    await waitFor(() =>
      expect(createAssignment).toHaveBeenCalledWith('w1', {
        position_id: 'pos1',
        day_index: 0,
        user_id: 'u1',
      }),
    );
  });

  it('selecting a guard from the pool colours and assigns on cell click', async () => {
    const { container } = renderPage();
    await screen.findByText('ארנונה');
    // Select נתן from the pool panel.
    fireEvent.click(screen.getByText('נתן כהן'));
    // Sunday cell (07:00–15:00) is fully covered → placeable; click assigns.
    const cell = await waitFor(() => {
      const c = container.querySelector('.board-cell.cov-full.placeable');
      if (!c) throw new Error('no placeable cell yet');
      return c;
    });
    fireEvent.click(cell);
    await waitFor(() =>
      expect(createAssignment).toHaveBeenCalledWith('w1', {
        position_id: 'pos1',
        day_index: 0,
        user_id: 'u1',
      }),
    );
  });

  it('assigns to an event (non-splitting) cell with no segment, ignoring availability', async () => {
    // An event board; רון has NO Sunday availability yet can still be placed —
    // events ignore availability and never carry a time segment.
    getNextWeekBoard.mockResolvedValue(
      makeBoard({
        rows: [
          {
            position_id: 'ev1',
            name: 'רענון',
            band: 'morning',
            canonical_window: { start: '07:00', end: '15:00' },
            required_attributes: [],
            is_event: true,
            active_day_count: 5,
            cells: Array.from({ length: 7 }, (_, d) => ({
              day_index: d,
              active: d < 5,
              window: d < 5 ? { start: '07:00', end: '15:00' } : null,
              is_override: false,
            })),
          },
        ],
      }),
    );
    const { container } = renderPage();
    await screen.findByText('רענון');
    fireEvent.click(screen.getByText('רון לוי')); // available nowhere
    const cell = await waitFor(() => {
      const c = container.querySelector('.board-cell-event.placeable');
      if (!c) throw new Error('no placeable event cell yet');
      return c;
    });
    // Event cells carry no coverage colour.
    expect(cell.className).not.toMatch(/cov-/);
    fireEvent.click(cell);
    await waitFor(() =>
      expect(createAssignment).toHaveBeenCalledWith('w1', {
        position_id: 'ev1',
        day_index: 0,
        user_id: 'u2',
      }),
    );
  });

  it('clips a partially-available guard to their available hours on assign', async () => {
    // שוהם is available only 09:00–15:00 of the 07:00–15:00 Sunday window.
    getPool.mockResolvedValue([
      {
        id: 'u3',
        full_name: 'שוהם',
        roles: ['ARMED'],
        remaining_hours: 20,
        notes: null,
        availability: { 0: [{ start: '09:00', end: '15:00' }] },
      },
    ]);
    const { container } = renderPage();
    await screen.findByText('ארנונה');
    fireEvent.click(screen.getByText('שוהם'));
    // Sunday cell is only partly covered → a placeable *partial* cell.
    const cell = await waitFor(() => {
      const c = container.querySelector('.board-cell.cov-partial.placeable');
      if (!c) throw new Error('no placeable partial cell yet');
      return c;
    });
    fireEvent.click(cell);
    // Assigned with the clipped segment — not the whole window.
    await waitFor(() =>
      expect(createAssignment).toHaveBeenCalledWith('w1', {
        position_id: 'pos1',
        day_index: 0,
        user_id: 'u3',
        segment_start: '09:00',
        segment_end: '15:00',
      }),
    );
  });

  it('renders an existing assignment and removes it on click', async () => {
    getAssignments.mockResolvedValue([
      {
        id: 'a1',
        position_id: 'pos1',
        day_index: 0,
        user_id: 'u1',
        user_full_name: 'נתן כהן',
        user_roles: ['armed'],
        segment_start: null,
        segment_end: null,
      },
    ]);
    renderPage();
    // Name shows in the cell chip (and the pool card) — just wait for render.
    await waitFor(() => expect(screen.getAllByText('נתן כהן').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByLabelText('הסר שיבוץ'));
    await waitFor(() => expect(deleteAssignment).toHaveBeenCalledWith('a1'));
  });

  it('shows the colour legend and does not warn on empty cells', async () => {
    const { container } = renderPage();
    await screen.findByText('ארנונה');
    const banner = container.querySelector('.board-summary');
    expect(banner).not.toBeNull();
    // Empty active cells are surfaced by the "ריק" coverage stat, not as a soft warning.
    const emptyChip = [...banner.querySelectorAll('.board-summary-chip')].find((c) =>
      c.textContent.includes('עמדה ריקה'),
    );
    expect(emptyChip).toBeFalsy();
    expect(container.querySelector('.board-legend')).not.toBeNull();
  });

  it('counts a missing-attribute warning for an under-qualified assignment', async () => {
    // u2 has no roles but pos1 requires "armed", and u2 is unavailable that day.
    getAssignments.mockResolvedValue([
      {
        id: 'a2',
        position_id: 'pos1',
        day_index: 0,
        user_id: 'u2',
        user_full_name: 'רון לוי',
        user_roles: [],
        segment_start: null,
        segment_end: null,
      },
    ]);
    const { container } = renderPage();
    await screen.findByText('ארנונה');
    const banner = container.querySelector('.board-summary');
    expect(banner.textContent).toMatch(/חוסר מאפיין/);
    expect(banner.textContent).toMatch(/מחוץ לזמינות/);
  });

  it('resyncs with the server even when an assign call fails (F-4)', async () => {
    createAssignment.mockRejectedValueOnce(new Error('nope'));
    const { container } = renderPage();
    await screen.findByText('ארנונה');
    fireEvent.click(screen.getByText('נתן כהן'));
    const cell = await waitFor(() => {
      const c = container.querySelector('.board-cell.cov-full.placeable');
      if (!c) throw new Error('no placeable cell yet');
      return c;
    });
    const before = getAssignments.mock.calls.length;
    fireEvent.click(cell);
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    // reloadAssignments ran in the finally despite the failed create.
    await waitFor(() =>
      expect(getAssignments.mock.calls.length).toBeGreaterThan(before),
    );
  });

  it('flushes a pending snapshot save on unmount (F-3)', async () => {
    const { container, unmount } = renderPage();
    await screen.findByText('ארנונה');
    fireEvent.click(screen.getByText('נתן כהן'));
    const cell = await waitFor(() => {
      const c = container.querySelector('.board-cell.cov-full.placeable');
      if (!c) throw new Error('no placeable cell yet');
      return c;
    });
    fireEvent.click(cell);
    // The edit scheduled a debounced (1.5s) snapshot save; toast.success marks it
    // done. Unmount BEFORE the timer fires — the pending save must still flush.
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    saveSchedule.mockClear();
    unmount();
    expect(saveSchedule).toHaveBeenCalledWith('w1');
  });

  it('toggles focus mode on/off (button, then Esc), flagging <body> and .board-page', async () => {
    const { container, unmount } = renderPage();
    await screen.findByText('ארנונה');

    // Off by default.
    expect(document.body.classList.contains('board-focus')).toBe(false);
    expect(container.querySelector('.board-page').classList.contains('is-focus')).toBe(false);

    // The controls button turns it on: both flags set, an exit button appears.
    fireEvent.click(screen.getByRole('button', { name: '⛶ מסך מלא' }));
    expect(document.body.classList.contains('board-focus')).toBe(true);
    expect(container.querySelector('.board-page').classList.contains('is-focus')).toBe(true);
    const exit = screen.getByRole('button', { name: '⛶ יציאה ממסך מלא' });

    // Clicking exit turns it off again.
    fireEvent.click(exit);
    expect(document.body.classList.contains('board-focus')).toBe(false);

    // Re-enter, then Esc exits (and doesn't leave <body> flagged).
    fireEvent.click(screen.getByRole('button', { name: '⛶ מסך מלא' }));
    expect(document.body.classList.contains('board-focus')).toBe(true);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(document.body.classList.contains('board-focus')).toBe(false);

    // Leaving the page never leaves the app chrome hidden.
    fireEvent.click(screen.getByRole('button', { name: '⛶ מסך מלא' }));
    unmount();
    expect(document.body.classList.contains('board-focus')).toBe(false);
  });
});
