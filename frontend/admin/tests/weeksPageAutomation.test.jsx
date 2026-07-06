import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// WeeksPage now renders react-router <Link>s (quick-links row) → needs a router.
const render = (ui) => rtlRender(<MemoryRouter>{ui}</MemoryRouter>);

vi.mock('../src/hooks/useWeeks', () => ({ useWeeks: vi.fn() }));
vi.mock('../src/hooks/useSettings', () => ({ useSettings: vi.fn() }));
vi.mock('../src/api/builderApiClient', () => ({
  listSavedSchedules: vi.fn(() => Promise.resolve([])),
  downloadSavedSchedule: vi.fn(() => Promise.resolve(new Blob(['x']))),
  saveSchedule: vi.fn(() => Promise.resolve({})),
}));
const toast = { success: vi.fn(), error: vi.fn() };
vi.mock('../src/components/Toast', () => ({ useToast: () => toast }));

import { useWeeks } from '../src/hooks/useWeeks';
import { useSettings } from '../src/hooks/useSettings';
import { listSavedSchedules, downloadSavedSchedule, saveSchedule } from '../src/api/builderApiClient';
import WeeksPage from '../src/pages/WeeksPage';

function mockWeeks() {
  useWeeks.mockReturnValue({
    weeks: [{ id: 'w1', status: 'closed', start_date: '2026-06-21', end_date: '2026-06-27' }],
    loading: false,
    setStatus: vi.fn(),
    openForSubmission: vi.fn(),
    publish: vi.fn(),
  });
}

function mockSettings(list) {
  useSettings.mockReturnValue({ settings: list, loading: false });
}

const enabledSettings = [
  { key: 'auto_open_enabled', value: 'true' },
  { key: 'auto_open_weekday', value: 'sunday' },
  { key: 'auto_open_time', value: '07:00' },
  { key: 'auto_lock_enabled', value: 'true' },
  { key: 'auto_lock_weekday', value: 'wednesday' },
  { key: 'auto_lock_time', value: '12:00' },
];

const disabledSettings = [
  { key: 'auto_open_enabled', value: 'false' },
  { key: 'auto_lock_enabled', value: 'false' },
];

describe('WeeksPage automation banner', () => {
  beforeEach(() => {
    useWeeks.mockReset();
    useSettings.mockReset();
    mockWeeks();
  });

  it('shows a summary banner when automation is on', () => {
    mockSettings(enabledSettings);
    render(<WeeksPage />);
    const banner = screen.getByText(/🤖/);
    expect(banner).toBeInTheDocument();
    expect(banner.textContent).toContain('ראשון 07:00');
    expect(banner.textContent).toContain('רביעי 12:00');
    expect(banner.textContent).toContain('ידני'); // publish is always manual
  });

  it('shows no banner when both switches are off', () => {
    mockSettings(disabledSettings);
    render(<WeeksPage />);
    expect(screen.queryByText(/🤖/)).not.toBeInTheDocument();
  });

  it('waits for settings before rendering (no flicker)', () => {
    useSettings.mockReturnValue({ settings: [], loading: true });
    render(<WeeksPage />);
    // Spinner shown, week cards not yet rendered.
    expect(screen.queryByText(/📅/)).not.toBeInTheDocument();
  });

  // Snapshot-download behaviour applies to FUTURE weeks only — a started week
  // offers the ACTUAL schedule instead (covered in weekQuickLinks.test.jsx).
  function mockFutureWeek() {
    useWeeks.mockReturnValue({
      weeks: [{ id: 'w1', status: 'closed', start_date: '2099-01-03', end_date: '2099-01-09' }],
      loading: false,
      setStatus: vi.fn(),
      openForSubmission: vi.fn(),
      publish: vi.fn(),
    });
  }

  it('shows a download button only on weeks that have a saved schedule', async () => {
    mockFutureWeek();
    mockSettings(disabledSettings);
    // jsdom lacks URL.createObjectURL / revokeObjectURL (used by the download).
    global.URL.createObjectURL = vi.fn(() => 'blob:mock');
    global.URL.revokeObjectURL = vi.fn();
    listSavedSchedules.mockResolvedValueOnce([{ week_id: 'w1', profile_name: 'שגרה', saved_at: '2026-07-01T12:00:00' }]);
    render(<WeeksPage />);
    const btn = await screen.findByText(/הורדת סידור/);
    fireEvent.click(btn);
    await waitFor(() => expect(downloadSavedSchedule).toHaveBeenCalledWith('w1'));
  });

  it('shows no download button when the week has no saved schedule', async () => {
    mockFutureWeek();
    mockSettings(disabledSettings);
    listSavedSchedules.mockResolvedValueOnce([]);
    render(<WeeksPage />);
    await screen.findByText(/📅/);
    expect(screen.queryByText(/הורדת סידור/)).not.toBeInTheDocument();
  });

  it('publishing a closed week also snapshots its schedule', async () => {
    const publishFn = vi.fn().mockResolvedValue({});
    useWeeks.mockReturnValue({
      weeks: [{ id: 'w1', status: 'closed', start_date: '2026-06-21', end_date: '2026-06-27' }],
      loading: false,
      setStatus: vi.fn(),
      openForSubmission: vi.fn(),
      publish: publishFn,
    });
    mockSettings(disabledSettings);
    saveSchedule.mockResolvedValueOnce({});
    render(<WeeksPage />);

    // Open the confirm dialog from the (now visible) publish button, then confirm.
    fireEvent.click(screen.getByRole('button', { name: /📢/ }));
    fireEvent.click(screen.getByText('כן, פרסם'));

    await waitFor(() => expect(publishFn).toHaveBeenCalledWith('w1'));
    await waitFor(() => expect(saveSchedule).toHaveBeenCalledWith('w1'));
    // The download button appears immediately for the freshly-saved week.
    await waitFor(() => expect(screen.getByText(/הורדת סידור/)).toBeInTheDocument());
  });
});
