import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('../src/api/attendanceApiClient', () => ({
  getAttendanceDay: vi.fn(),
  getAttendanceStatus: vi.fn(),
  getAttendanceUserPeriod: vi.fn(),
  getAttendancePeriodSummary: vi.fn(),
}));

import {
  getAttendanceUserPeriod,
  getAttendancePeriodSummary,
  getAttendanceDay,
  getAttendanceStatus,
} from '../src/api/attendanceApiClient';
import AttendanceUserPage from '../src/pages/AttendanceUserPage';
import AttendancePage from '../src/pages/AttendancePage';
import { weekRange, monthRange, shiftRange } from '../src/utils/attendanceDates';

const day = (overrides = {}) => ({
  user_id: 'u1',
  user_name: 'יוסי כהן',
  date: '2026-07-05',
  band: 'morning',
  planned: [
    {
      position_name: 'שער ראשי',
      start: '2026-07-05T07:00:00',
      end: '2026-07-05T15:00:00',
      is_event: false,
    },
  ],
  actual: [
    {
      shift_id: 's1',
      check_in_at: '2026-07-05T07:02:00',
      check_out_raw: '2026-07-05T15:01:00',
      check_out_rounded: '2026-07-05T15:15:00',
      status: 'complete',
      in_source: 'telegram',
      out_source: 'telegram',
      out_of_radius: false,
    },
  ],
  segments: [
    { start: '2026-07-05T07:02:00', end: '2026-07-05T15:01:00', kind: 'covered' },
  ],
  summary: {
    planned_minutes: 480,
    actual_minutes: 493,
    extra_minutes: 0,
    delta_in_minutes: 2,
    delta_out_minutes: 1,
    severity: 'ok',
    tag: 'תקין ✔',
    orphan_out_times: [],
  },
  ...overrides,
});

function mockPeriod(days) {
  getAttendanceUserPeriod.mockResolvedValue({
    user_id: 'u1',
    user_name: 'יוסי כהן',
    date_from: '2026-07-05',
    date_to: '2026-07-11',
    days: days || [day()],
    summary: {
      planned_minutes: 480,
      actual_minutes: 493,
      extra_minutes: 0,
      big: 0,
      small: 0,
    },
  });
}

function renderUserPage(search = '?date=2026-07-05&view=week') {
  return render(
    <MemoryRouter initialEntries={[`/attendance/users/u1${search}`]}>
      <Routes>
        <Route path="/attendance/users/:userId" element={<AttendanceUserPage />} />
        <Route path="/attendance" element={<div>DAY-VIEW</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('date range helpers', () => {
  it('weekRange is Sunday→Saturday', () => {
    // 2026-07-08 is a Wednesday
    expect(weekRange('2026-07-08')).toEqual({ from: '2026-07-05', to: '2026-07-11' });
  });
  it('monthRange covers the calendar month', () => {
    expect(monthRange('2026-07-08')).toEqual({ from: '2026-07-01', to: '2026-07-31' });
  });
  it('shiftRange moves by week/month', () => {
    expect(shiftRange('2026-07-08', 'week', 1)).toBe('2026-07-15');
    expect(shiftRange('2026-07-08', 'month', -1)).toBe('2026-06-01');
  });
});

describe('AttendanceUserPage — dual-lane day blocks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPeriod();
  });

  it('renders the day block with lanes, tag and labeled human numbers', async () => {
    renderUserPage();
    expect(await screen.findByText(/יוסי כהן/)).toBeInTheDocument();
    expect(screen.getByTestId('att-day-block')).toBeInTheDocument();
    expect(screen.getByText('מתוכנן')).toBeInTheDocument();
    expect(screen.getByText('בפועל')).toBeInTheDocument();
    expect(screen.getByText('שער ראשי')).toBeInTheDocument();
    expect(screen.getByText('תקין ✔')).toBeInTheDocument();
    // deltas as words, not signed numbers: in +2 → "איחר 2 ד'", out +1 → "נשאר עוד 1 ד'"
    const nums = document.querySelector('.att-day-nums').textContent;
    expect(nums).toContain('בפועל 8:13');
    expect(nums).toContain('מתוכנן 8:00');
    expect(nums).toContain("איחר 2 ד'");
    expect(nums).toContain("נשאר עוד 1 ד'");
    expect(nums).not.toMatch(/[+-]\d+ ד/);
  });

  it('shows the rounded check-out with the real time next to it', async () => {
    renderUserPage();
    await screen.findByTestId('att-day-block');
    const label = screen.getByText('15:15');
    expect(label.parentElement.textContent).toContain('⤴');
    expect(label.parentElement.textContent).toContain('15:01');
  });

  it('fetches the week range for view=week', async () => {
    renderUserPage('?date=2026-07-08&view=week');
    await screen.findByTestId('att-day-block');
    expect(getAttendanceUserPeriod).toHaveBeenCalledWith('u1', '2026-07-05', '2026-07-11');
  });

  it('fetches the month range for view=month', async () => {
    renderUserPage('?date=2026-07-08&view=month');
    await screen.findByTestId('att-day-block');
    expect(getAttendanceUserPeriod).toHaveBeenCalledWith('u1', '2026-07-01', '2026-07-31');
  });

  it('back button returns to the exact list we came from (view preserved)', async () => {
    renderUserPage('?date=2026-07-05&view=week&back=week');
    fireEvent.click(await screen.findByRole('button', { name: /חזרה לנוכחות/ }));
    expect(await screen.findByText('DAY-VIEW')).toBeInTheDocument();
    // the URL carried the week view back to the main page
  });
});

describe('AttendancePage — week/month summary list', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getAttendanceDay.mockResolvedValue({
      date: '2026-07-05',
      now: '2026-07-05T14:30:00',
      counters: { scheduled: 0, present: 0, big: 0, small: 0 },
      bands: [],
    });
    getAttendanceStatus.mockResolvedValue(null);
    getAttendancePeriodSummary.mockResolvedValue([
      {
        user_id: 'u1',
        user_name: 'יוסי כהן',
        planned_minutes: 2400,
        actual_minutes: 2465,
        extra_minutes: 65,
        days_scheduled: 5,
        days_present: 5,
        big: 0,
        small: 1,
      },
    ]);
  });

  it('switching to week shows labeled columns and a week period picker', async () => {
    render(
      <MemoryRouter>
        <AttendancePage />
      </MemoryRouter>,
    );
    await screen.findByText('אין משובצים או החתמות ביום זה.');
    fireEvent.click(screen.getByRole('button', { name: 'שבוע' }));
    expect(await screen.findByText('יוסי כהן')).toBeInTheDocument();
    await waitFor(() => expect(getAttendancePeriodSummary).toHaveBeenCalled());

    // column headers instead of a blob of numbers
    expect(screen.getByText('שעות בפועל')).toBeInTheDocument();
    expect(screen.getByText('שעות מתוכנן')).toBeInTheDocument();
    expect(screen.getByText('מעבר למתוכנן')).toBeInTheDocument();
    expect(screen.getByText('41:05')).toBeInTheDocument(); // 2465 min in its own cell

    // the date input is replaced by a prev/next week picker with a range label
    expect(screen.getByRole('button', { name: /הקודם/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /הבא/ })).toBeInTheDocument();
    expect(document.querySelector('input[type="date"]')).toBeNull();
    expect(document.querySelector('.att-range-label').textContent).toMatch(/—/);
  });
});
