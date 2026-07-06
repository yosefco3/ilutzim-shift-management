import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../src/api/attendanceApiClient', () => ({
  getAttendanceDay: vi.fn(),
  getAttendanceStatus: vi.fn(),
  getAttendanceUserPeriod: vi.fn(),
}));

const navigate = vi.fn();
vi.mock('react-router-dom', async (orig) => ({
  ...(await orig()),
  useNavigate: () => navigate,
}));

import { getAttendanceDay, getAttendanceStatus } from '../src/api/attendanceApiClient';
import AttendancePage from '../src/pages/AttendancePage';

const TODAY = new Date().toLocaleDateString('sv-SE');

const row = (overrides = {}) => ({
  user_id: 'u1',
  user_name: 'יוסי כהן',
  date: TODAY,
  band: 'morning',
  planned: [
    {
      position_name: 'שער ראשי',
      start: `${TODAY}T07:00:00`,
      end: `${TODAY}T15:00:00`,
      is_event: false,
    },
  ],
  actual: [],
  segments: [
    { start: `${TODAY}T07:02:00`, end: `${TODAY}T14:00:00`, kind: 'covered' },
  ],
  summary: {
    planned_minutes: 480,
    actual_minutes: 418,
    extra_minutes: 0,
    delta_in_minutes: 2,
    delta_out_minutes: null,
    severity: 'ok',
    tag: 'בעמדה ✔',
    orphan_out_times: [],
  },
  ...overrides,
});

function mockDay({ bands, counters } = {}) {
  getAttendanceDay.mockResolvedValue({
    date: TODAY,
    now: `${TODAY}T14:30:00`,
    counters: counters || { scheduled: 2, present: 1, big: 1, small: 0 },
    bands: bands || [
      { band: 'morning', rows: [row()] },
      {
        band: 'night',
        rows: [
          row({
            user_id: 'u2',
            user_name: 'אבי מזרחי',
            band: 'night',
            segments: [
              { start: `${TODAY}T23:00:00`, end: `${TODAY}T23:59:00`, kind: 'no_show' },
            ],
            summary: { ...row().summary, severity: 'big', tag: 'לא הגיע' },
          }),
        ],
      },
    ],
  });
  getAttendanceStatus.mockResolvedValue({
    enabled: true,
    events_today: 5,
    last_event_at: `${TODAY}T13:03:00`,
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AttendancePage />
    </MemoryRouter>,
  );
}

describe('AttendancePage — compact all-employees day view', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDay();
  });

  it('renders band groups with employee rows and tags', async () => {
    renderPage();
    expect(await screen.findByText('יוסי כהן')).toBeInTheDocument();
    expect(screen.getByText(/בוקר/)).toBeInTheDocument();
    expect(screen.getByText(/לילה/)).toBeInTheDocument();
    expect(screen.getByText('אבי מזרחי')).toBeInTheDocument();
    expect(screen.getByText('לא הגיע')).toBeInTheDocument();
  });

  it('shows counters and the source status widget', async () => {
    renderPage();
    await screen.findByText('יוסי כהן');
    expect(screen.getByText('משובצים:').parentElement.textContent).toContain('2');
    expect(screen.getByText(/החתמות היום/).parentElement.textContent).toContain('5');
  });

  it('draws the red now-line for today', async () => {
    renderPage();
    await screen.findByText('יוסי כהן');
    expect(screen.getAllByTestId('att-nowline').length).toBeGreaterThan(0);
  });

  it('view switches render with day active', async () => {
    renderPage();
    await screen.findByText('יוסי כהן');
    expect(screen.getByRole('button', { name: 'יום' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'שבוע' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'חודש' })).toBeEnabled();
  });

  it('clicking a row navigates to the employee page with a back target', async () => {
    renderPage();
    fireEvent.click(await screen.findByText('יוסי כהן'));
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith(
        `/attendance/users/u1?date=${TODAY}&back=day`,
      ),
    );
  });

  it('empty day shows the empty state', async () => {
    getAttendanceDay.mockResolvedValue({
      date: TODAY,
      now: `${TODAY}T14:30:00`,
      counters: { scheduled: 0, present: 0, big: 0, small: 0 },
      bands: [],
    });
    renderPage();
    expect(
      await screen.findByText('אין משובצים או החתמות ביום זה.'),
    ).toBeInTheDocument();
  });
});
