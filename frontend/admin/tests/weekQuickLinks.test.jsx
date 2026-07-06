import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../src/hooks/useWeeks', () => ({ useWeeks: vi.fn() }));
vi.mock('../src/hooks/useSettings', () => ({ useSettings: vi.fn() }));
vi.mock('../src/api/builderApiClient', () => ({
  listSavedSchedules: vi.fn(() => Promise.resolve([])),
  downloadSavedSchedule: vi.fn(() => Promise.resolve(new Blob(['x']))),
  saveSchedule: vi.fn(() => Promise.resolve({})),
  exportActualScheduleGrid: vi.fn(() => Promise.resolve(new Blob(['x']))),
}));
vi.mock('../src/api/adminApiClient', () => ({
  exportExcel: vi.fn(() => Promise.resolve(new Blob(['xlsx']))),
}));
const toast = { success: vi.fn(), error: vi.fn(), warning: vi.fn() };
vi.mock('../src/components/Toast', () => ({ useToast: () => toast }));

import { useWeeks } from '../src/hooks/useWeeks';
import { useSettings } from '../src/hooks/useSettings';
import { listSavedSchedules, downloadSavedSchedule, exportActualScheduleGrid } from '../src/api/builderApiClient';
import { exportExcel } from '../src/api/adminApiClient';
import WeeksPage from '../src/pages/WeeksPage';
import messages from '../src/utils/messages';

const L = messages.weeks.links;

// One week far in the past (already started) and one far in the future
// (upcoming → the "current"/publishable week). Dates are extreme on purpose so
// the started/upcoming split is stable no matter when the tests run.
const PAST_WEEK = { id: 'w-past', status: 'locked', start_date: '2020-01-05', end_date: '2020-01-11' };
const FUTURE_WEEK = { id: 'w-future', status: 'closed', start_date: '2099-01-03', end_date: '2099-01-09' };

const disabledSettings = [
  { key: 'auto_open_enabled', value: 'false' },
  { key: 'auto_lock_enabled', value: 'false' },
];

function mockWeeks(weeks) {
  useWeeks.mockReturnValue({
    weeks,
    loading: false,
    setStatus: vi.fn(),
    openForSubmission: vi.fn(),
    publish: vi.fn(),
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <WeeksPage />
    </MemoryRouter>,
  );
}

// The card that shows the given week's start date.
function cardOf(container, week) {
  const card = Array.from(container.querySelectorAll('.week-card'))
    .find((c) => c.textContent.includes(week.start_date));
  expect(card).toBeTruthy();
  return within(card);
}

describe('WeekQuickLinks (weeks page card footer)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSettings.mockReturnValue({ settings: disabledSettings, loading: false });
    listSavedSchedules.mockResolvedValue([]);
    global.URL.createObjectURL = vi.fn(() => 'blob:mock');
    global.URL.revokeObjectURL = vi.fn();
  });

  it('links every week to the EDITABLE submissions page with the week preselected', () => {
    mockWeeks([PAST_WEEK, FUTURE_WEEK]);
    const { container } = renderPage();
    expect(cardOf(container, PAST_WEEK).getByRole('link', { name: new RegExp(L.submissions) }))
      .toHaveAttribute('href', '/submissions?week=w-past');
    expect(cardOf(container, FUTURE_WEEK).getByRole('link', { name: new RegExp(L.submissions) }))
      .toHaveAttribute('href', '/submissions?week=w-future');
  });

  it('exports the week constraints directly from the card', async () => {
    mockWeeks([FUTURE_WEEK]);
    const { container } = renderPage();
    fireEvent.click(cardOf(container, FUTURE_WEEK).getByRole('button', { name: new RegExp(L.exportConstraints) }));
    await waitFor(() => expect(exportExcel).toHaveBeenCalledWith('w-future'));
  });

  it('surfaces an export failure as a toast', async () => {
    exportExcel.mockRejectedValueOnce(new Error('boom'));
    mockWeeks([FUTURE_WEEK]);
    const { container } = renderPage();
    fireEvent.click(cardOf(container, FUTURE_WEEK).getByRole('button', { name: new RegExp(L.exportConstraints) }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('boom'));
  });

  it('shows the attendance link only on weeks that already started', () => {
    mockWeeks([PAST_WEEK, FUTURE_WEEK]);
    const { container } = renderPage();
    expect(cardOf(container, PAST_WEEK).getByRole('link', { name: new RegExp(L.attendance) }))
      .toHaveAttribute('href', '/attendance?view=week&date=2020-01-05');
    expect(cardOf(container, FUTURE_WEEK).queryByRole('link', { name: new RegExp(L.attendance) }))
      .toBeNull();
  });

  it('shows the publish-preview link only on the current (publishable) week', () => {
    mockWeeks([PAST_WEEK, FUTURE_WEEK]);
    const { container } = renderPage();
    expect(cardOf(container, FUTURE_WEEK).getByRole('link', { name: new RegExp(L.publishPreview) }))
      .toHaveAttribute('href', '/publish-preview');
    expect(cardOf(container, PAST_WEEK).queryByRole('link', { name: new RegExp(L.publishPreview) }))
      .toBeNull();
  });

  it('a STARTED week downloads the ACTUAL schedule (what really happened)', async () => {
    mockWeeks([PAST_WEEK, FUTURE_WEEK]);
    const { container } = renderPage();
    const btn = cardOf(container, PAST_WEEK).getByRole('button', { name: new RegExp(L.downloadActualSchedule) });
    // A future week never offers the actual download — it hasn't happened yet.
    expect(cardOf(container, FUTURE_WEEK).queryByRole('button', { name: new RegExp(L.downloadActualSchedule) }))
      .toBeNull();
    fireEvent.click(btn);
    await waitFor(() => expect(exportActualScheduleGrid).toHaveBeenCalledWith('w-past'));
    expect(downloadSavedSchedule).not.toHaveBeenCalled();
  });

  it('a FUTURE week keeps the planned-snapshot download (when one exists)', async () => {
    listSavedSchedules.mockResolvedValue([{ week_id: 'w-future', profile_name: 'שגרה', saved_at: '2026-07-01T12:00:00' }]);
    mockWeeks([PAST_WEEK, FUTURE_WEEK]);
    const { container } = renderPage();
    const btn = await cardOf(container, FUTURE_WEEK).findByRole('button', { name: new RegExp(L.downloadSchedule) });
    fireEvent.click(btn);
    await waitFor(() => expect(downloadSavedSchedule).toHaveBeenCalledWith('w-future'));
    expect(exportActualScheduleGrid).not.toHaveBeenCalled();
  });
});
