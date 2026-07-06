import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../src/hooks/useWeeks', () => ({ useWeeks: vi.fn() }));
vi.mock('../src/api/builderApiClient', () => ({
  getActualBoard: vi.fn(),
  listAttributes: vi.fn(() => Promise.resolve([])),
  createActualAssignment: vi.fn(() => Promise.resolve({})),
  updateActualSegment: vi.fn(() => Promise.resolve({})),
  deleteActualAssignment: vi.fn(() => Promise.resolve()),
  createActualPosition: vi.fn(() => Promise.resolve({})),
  updateActualPosition: vi.fn(() => Promise.resolve({})),
  deleteActualPosition: vi.fn(() => Promise.resolve()),
  saveActualAsProfile: vi.fn(() => Promise.resolve({ id: 'pr-1', name: 'שגרה חדשה' })),
  createReinforcement: vi.fn(() => Promise.resolve({ id: 'card-1', user_id: 'ru-1', full_name: 'חיצוני מתגבר' })),
  deleteReinforcement: vi.fn(() => Promise.resolve()),
  exportReinforcementsReport: vi.fn(() => Promise.resolve(new Blob(['x']))),
  exportActualScheduleGrid: vi.fn(() => Promise.resolve(new Blob(['xlsx']))),
  exportActualSchedulePng: vi.fn(() => Promise.resolve(new Blob(['png']))),
}));
vi.mock('../src/api/adminApiClient', () => ({
  fetchGuards: vi.fn(() => Promise.resolve([])),
}));
const toast = { success: vi.fn(), error: vi.fn() };
vi.mock('../src/components/Toast', () => ({ useToast: () => toast }));

import { useWeeks } from '../src/hooks/useWeeks';
import {
  getActualBoard,
  createActualPosition,
  deleteActualPosition,
  saveActualAsProfile,
  createReinforcement,
  deleteReinforcement,
  exportActualScheduleGrid,
  exportActualSchedulePng,
} from '../src/api/builderApiClient';
import { fetchGuards } from '../src/api/adminApiClient';
import ActualBoardPage from '../src/pages/ActualBoardPage';
import messages from '../src/utils/messages';

const PAST_WEEK = { id: 'w-old', status: 'locked', start_date: '2020-01-05', end_date: '2020-01-11' };
const CURRENT_WEEK = { id: 'w-now', status: 'locked', start_date: '2020-02-02', end_date: '2020-02-08' };
const FUTURE_WEEK = { id: 'w-future', status: 'closed', start_date: '2099-01-03', end_date: '2099-01-09' };

const WINDOW = { start: '07:00', end: '15:00' };

function boardFixture(overrides = {}) {
  return {
    week: { id: 'w-now', start_date: '2020-02-02', end_date: '2020-02-08', status: 'locked' },
    actual_schedule_id: 'as-1',
    seeded_at: '2020-02-02T00:00:00',
    seed_source: 'rollover',
    days: Array.from({ length: 7 }, (_, i) => ({ index: i, date: `2020-02-0${2 + i}` })),
    rows: [
      {
        position_id: 'p1',
        name: 'שער ראשי',
        band: 'morning',
        canonical_window: WINDOW,
        required_attributes: [],
        is_event: false,
        event_required_count: null,
        active_day_count: 7,
        source_position_id: 'src-1',
        is_adhoc: false,
        cells: Array.from({ length: 7 }, (_, i) => ({
          day_index: i, active: true, window: WINDOW, is_override: false,
        })),
      },
    ],
    assignments: [
      {
        id: 'a1', actual_position_id: 'p1', day_index: 0, user_id: 'u1',
        user_full_name: 'נתן כהן', user_roles: [],
        segment_start: null, segment_end: null,
      },
    ],
    reinforcements: [],
    warnings: [],
    ...overrides,
  };
}

function mockWeeks(weeks = [PAST_WEEK, CURRENT_WEEK, FUTURE_WEEK]) {
  useWeeks.mockReturnValue({ weeks, loading: false });
}

function renderPage(url = '/actual') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <ActualBoardPage />
    </MemoryRouter>,
  );
}

describe('ActualBoardPage (read-only skeleton)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getActualBoard.mockResolvedValue(boardFixture());
  });

  it('defaults to the most recent STARTED week (future weeks excluded)', async () => {
    mockWeeks();
    renderPage();
    await waitFor(() => expect(getActualBoard).toHaveBeenCalledWith('w-now'));
    const picker = screen.getByLabelText(messages.actualBoard.weekPicker);
    expect(picker.value).toBe('w-now');
    // The future week is not offered at all.
    expect(
      Array.from(picker.options).map((o) => o.value),
    ).toEqual(['w-now', 'w-old']);
  });

  it('honours ?week= and lets the admin switch weeks', async () => {
    mockWeeks();
    renderPage('/actual?week=w-old');
    await waitFor(() => expect(getActualBoard).toHaveBeenCalledWith('w-old'));

    fireEvent.change(screen.getByLabelText(messages.actualBoard.weekPicker), {
      target: { value: 'w-now' },
    });
    await waitFor(() => expect(getActualBoard).toHaveBeenCalledWith('w-now'));
  });

  it('renders the grid with positions and assigned guards', async () => {
    mockWeeks();
    renderPage();
    expect(await screen.findByText('שער ראשי')).toBeInTheDocument();
    expect(screen.getByText(/נתן כהן/)).toBeInTheDocument();
    expect(screen.getByText(messages.actualBoard.badge)).toBeInTheDocument();
  });

  it('surfaces soft warnings as a count banner', async () => {
    mockWeeks();
    getActualBoard.mockResolvedValue(boardFixture({
      warnings: [
        { type: 'overstaffed_cell', day_index: 0, position_id: 'p1', position_name: 'שער ראשי', count: 3 },
        { type: 'already_in_shift', day_index: 1, user_id: 'u1', user_name: 'נתן כהן', position_names: ['א', 'ב'] },
      ],
    }));
    renderPage();
    expect(await screen.findByText(/2 אזהרות רכות/)).toBeInTheDocument();
  });

  it('shows a friendly empty state when no week has started yet', async () => {
    mockWeeks([FUTURE_WEEK]);
    renderPage();
    expect(
      await screen.findByText(messages.actualBoard.noStartedWeeks),
    ).toBeInTheDocument();
    expect(getActualBoard).not.toHaveBeenCalled();
  });
});

describe('ActualBoardPage — editing UX', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getActualBoard.mockResolvedValue(boardFixture());
    fetchGuards.mockResolvedValue([
      { id: 'u2', first_name: 'דנה', last_name: 'לוי', roles: [], is_active: true },
      { id: 'u3', first_name: 'רן', last_name: 'אחמש', roles: ['AHMASH'], is_active: true },
      { id: 'u4', first_name: 'כבוי', last_name: 'לא-פעיל', roles: [], is_active: false },
    ]);
  });

  it('renders the simple pool: active guards only, AHMASH first, no hour meta', async () => {
    mockWeeks();
    renderPage();
    await screen.findByText('שער ראשי');
    const pool = screen.getByLabelText(messages.board.pool.title);
    const names = Array.from(pool.querySelectorAll('.guard-card-name')).map((n) => n.textContent);
    expect(names).toEqual(['רן אחמש', 'דנה לוי']); // AHMASH first, inactive dropped
    expect(pool.querySelector('.guard-card-meter')).toBeNull(); // simple mode
  });

  it('adds an ad-hoc position through the SHARED position form', async () => {
    mockWeeks();
    renderPage();
    await screen.findByText('שער ראשי');

    fireEvent.click(screen.getByRole('button', { name: new RegExp(messages.actualBoard.addPosition) }));
    // The very same editor form the profile's positions page uses.
    const dialog = screen.getByText(messages.positions.addTitle).closest('.modal-content');
    fireEvent.change(dialog.querySelector('#pos-name'), {
      target: { value: 'אבטחת אירוע' },
    });
    // Enable day א (index 0) via the shared form's day toggle.
    fireEvent.click(dialog.querySelectorAll('.day-toggle input')[0]);
    fireEvent.click(screen.getByRole('button', { name: messages.common.save }));

    await waitFor(() => expect(createActualPosition).toHaveBeenCalledWith('w-now', {
      name: 'אבטחת אירוע',
      day_schedules: { 0: { start: '07:00', end: '15:00' } },
      required_attributes: [],
      is_event: false,
      event_required_count: null,
    }));
  });

  it('deletes a position after confirmation', async () => {
    mockWeeks();
    renderPage();
    await screen.findByText('שער ראשי');

    fireEvent.click(screen.getByLabelText(messages.board.deletePosition));
    expect(screen.getByText(messages.actualBoard.deletePositionTitle)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: messages.common.delete }));

    await waitFor(() => expect(deleteActualPosition).toHaveBeenCalledWith('p1'));
  });

  it('saves the board as a new profile', async () => {
    mockWeeks();
    renderPage();
    await screen.findByText('שער ראשי');

    fireEvent.click(screen.getByRole('button', { name: new RegExp(messages.actualBoard.saveAsProfile) }));
    const dialog = screen.getByText(messages.actualBoard.saveAsProfileTitle).closest('.modal-content');
    fireEvent.change(dialog.querySelector('input[type="text"]'), {
      target: { value: 'שגרה חדשה' },
    });
    fireEvent.click(screen.getByRole('button', { name: messages.common.save }));

    await waitFor(() => expect(saveActualAsProfile).toHaveBeenCalledWith('w-now', 'שגרה חדשה'));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it('reinforcements from the board join the pool with the מתגבר chip', async () => {
    mockWeeks();
    getActualBoard.mockResolvedValue(boardFixture({
      reinforcements: [
        { id: 'card-1', user_id: 'ru-1', full_name: 'חיצוני מתגבר', phone_number: null, note: 'מחברה ב' },
      ],
    }));
    renderPage();
    await screen.findByText('שער ראשי');
    const pool = screen.getByLabelText(messages.board.pool.title);
    const names = Array.from(pool.querySelectorAll('.guard-card-name')).map((n) => n.textContent);
    expect(names).toContain('חיצוני מתגבר');
    // The synthetic chip renders through ROLE_LABELS.
    expect(pool.textContent).toContain('מתגבר');
  });

  it('adds a reinforcement through the dialog', async () => {
    mockWeeks();
    renderPage();
    await screen.findByText('שער ראשי');

    fireEvent.click(screen.getByRole('button', { name: /🧩/ }));
    const dialog = screen.getByText(messages.actualBoard.reinforcements.dialogTitle).closest('.modal-content');
    fireEvent.change(dialog.querySelectorAll('input[type="text"], input[type="tel"]')[0], { target: { value: 'חיצוני' } });
    fireEvent.change(dialog.querySelectorAll('input[type="text"], input[type="tel"]')[1], { target: { value: 'מתגבר' } });
    fireEvent.change(dialog.querySelector('input[type="tel"]'), { target: { value: '0501234567' } });
    // Supervisor is the 4th field (first/last/phone/supervisor/note).
    fireEvent.change(dialog.querySelectorAll('.reinforcement-form input')[3], { target: { value: 'מפקח כהן' } });
    fireEvent.click(screen.getByRole('button', { name: new RegExp(messages.actualBoard.reinforcements.add) }));

    await waitFor(() => expect(createReinforcement).toHaveBeenCalledWith('w-now', {
      first_name: 'חיצוני',
      last_name: 'מתגבר',
      phone_number: '0501234567',
      note: null,
      supervisor_name: 'מפקח כהן',
    }));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it('exports the actual board as Excel and PNG from the toolbar', async () => {
    global.URL.createObjectURL = vi.fn(() => 'blob:mock');
    global.URL.revokeObjectURL = vi.fn();
    mockWeeks();
    renderPage();
    await screen.findByText('שער ראשי');

    fireEvent.click(screen.getByRole('button', { name: new RegExp(messages.actualBoard.exportExcel) }));
    await waitFor(() => expect(exportActualScheduleGrid).toHaveBeenCalledWith('w-now'));

    fireEvent.click(screen.getByRole('button', { name: new RegExp(messages.actualBoard.exportPng) }));
    await waitFor(() => expect(exportActualSchedulePng).toHaveBeenCalledWith('w-now'));
  });

  it('links to the reinforcements-report page (own route, not the dialog)', async () => {
    mockWeeks();
    renderPage();
    await screen.findByText('שער ראשי');
    expect(
      screen.getByRole('link', { name: new RegExp(messages.actualBoard.reinforcements.reportTitle) }),
    ).toHaveAttribute('href', '/actual/report');
  });

  it('removes a reinforcement after confirmation', async () => {
    mockWeeks();
    getActualBoard.mockResolvedValue(boardFixture({
      reinforcements: [
        { id: 'card-1', user_id: 'ru-1', full_name: 'חיצוני מתגבר', phone_number: null, note: null },
      ],
    }));
    renderPage();
    await screen.findByText('שער ראשי');

    fireEvent.click(screen.getByRole('button', { name: /🧩/ }));
    const dialog = screen.getByText(messages.actualBoard.reinforcements.dialogTitle).closest('.modal-content');
    // The card row's delete opens a confirm; confirm it.
    fireEvent.click(dialog.querySelector('.reinforcement-row button'));
    fireEvent.click(screen.getByText(messages.actualBoard.reinforcements.confirmDeleteTitle).closest('.modal-content').querySelector('.modal-actions .btn-primary, .modal-actions button'));

    await waitFor(() => expect(deleteReinforcement).toHaveBeenCalledWith('card-1'));
  });

  it('marks ad-hoc rows with the "נוספה" tag', async () => {
    mockWeeks();
    getActualBoard.mockResolvedValue(boardFixture({
      rows: [
        {
          ...boardFixture().rows[0],
          position_id: 'p2',
          name: 'אירוע פתע',
          source_position_id: null,
          is_adhoc: true,
        },
      ],
      assignments: [],
    }));
    renderPage();
    expect(await screen.findByText(messages.board.adhocTag)).toBeInTheDocument();
  });
});
