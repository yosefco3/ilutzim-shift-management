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
const toast = { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() };
vi.mock('../src/components/Toast', () => ({ useToast: () => toast }));

import { useWeeks } from '../src/hooks/useWeeks';
import { useSettings } from '../src/hooks/useSettings';
import WeeksPage from '../src/pages/WeeksPage';

// A single CLOSED week in the past → currentWeek falls back to it (isCurrent),
// so the publish (📢) button is shown.
function mockWeeks(overrides = {}) {
  const base = {
    weeks: [{ id: 'w1', status: 'closed', start_date: '2026-06-21', end_date: '2026-06-27' }],
    loading: false,
    setStatus: vi.fn(),
    openForSubmission: vi.fn(),
    publish: vi.fn(() => Promise.resolve({ sent: 3, failed: 0, total: 3, republished: false })),
    ...overrides,
  };
  useWeeks.mockReturnValue(base);
  return base;
}

const disabledSettings = [
  { key: 'auto_open_enabled', value: 'false' },
  { key: 'auto_lock_enabled', value: 'false' },
];

async function clickPublish() {
  fireEvent.click(screen.getByText(/📢/));
  fireEvent.click(await screen.findByText('כן, פרסם'));
}

describe('WeeksPage publish robustness (F-1, F-2)', () => {
  beforeEach(() => {
    useWeeks.mockReset();
    useSettings.mockReset();
    useSettings.mockReturnValue({ settings: disabledSettings, loading: false });
    Object.values(toast).forEach((fn) => fn.mockReset());
  });

  it('shows a success toast when every guard is reached', async () => {
    mockWeeks();
    render(<WeeksPage />);
    await clickPublish();
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(toast.warning).not.toHaveBeenCalled();
  });

  it('shows a warning toast (not success) when some deliveries failed', async () => {
    mockWeeks({
      publish: vi.fn(() => Promise.resolve({ sent: 1, failed: 2, total: 3, republished: false })),
    });
    render(<WeeksPage />);
    await clickPublish();
    await waitFor(() => expect(toast.warning).toHaveBeenCalled());
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('shows an error toast when publish rejects (not swallowed)', async () => {
    mockWeeks({ publish: vi.fn(() => Promise.reject(new Error('boom'))) });
    render(<WeeksPage />);
    await clickPublish();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('boom'));
  });

  it('guards against a double publish while one is in flight (F-1)', async () => {
    let resolvePublish;
    const publish = vi.fn(() => new Promise((res) => { resolvePublish = res; }));
    mockWeeks({ publish });
    render(<WeeksPage />);

    await clickPublish();                      // first publish → in flight
    expect(publish).toHaveBeenCalledTimes(1);
    // The publish button is now disabled during the in-flight window.
    expect(screen.getByText(/📢/).closest('button')).toBeDisabled();

    resolvePublish({ sent: 3, failed: 0, total: 3, republished: false });
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(publish).toHaveBeenCalledTimes(1);
  });

  it('surfaces a lock failure as an error toast (F-2)', async () => {
    mockWeeks({
      weeks: [{ id: 'w1', status: 'open', start_date: '2026-06-21', end_date: '2026-06-27' }],
      setStatus: vi.fn(() => Promise.reject(new Error('lock failed'))),
    });
    render(<WeeksPage />);
    fireEvent.click(screen.getByText(/סגור להגשה/));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('lock failed'));
  });
});
