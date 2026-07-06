import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useSubmission } from '../src/hooks/useSubmission';

// Mock guardApiClient
vi.mock('../src/api/guardApiClient', () => ({
  get: vi.fn(),
  post: vi.fn(),
}));

import { get, post } from '../src/api/guardApiClient';

describe('useSubmission', () => {
  const initData = 'test-init-data';

  beforeEach(() => {
    vi.resetAllMocks();
    // Reset window.location.href
    delete window.location;
    window.location = { href: '' };
  });

  it('should start in loading state', () => {
    get.mockResolvedValue({ data: null, error: 'no week' });

    const { result } = renderHook(() => useSubmission(initData));
    expect(result.current.loading).toBe(true);
  });

  it('should load week data and set canSubmit=true for open week', async () => {
    get.mockImplementation((path) => {
      if (path.includes('current-week')) {
        return Promise.resolve({
          data: {
            id: 'w1',
            status: 'open',
            week_label: 'שבוע 1',
            days: [{ day_index: 0, blocked: false }],
          },
          error: null,
        });
      }
      if (path.includes('my')) {
        return Promise.resolve({ data: null, error: null });
      }
      return Promise.resolve({ data: null, error: null });
    });

    const { result } = renderHook(() => useSubmission(initData));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.canSubmit).toBe(true);
    expect(result.current.weekStatus).toBe('open');
    expect(result.current.days).toHaveLength(1);
  });

  it('should set canSubmit=false for locked week', async () => {
    get.mockResolvedValue({
      data: { id: 'w1', status: 'locked', days: [] },
      error: null,
    });

    const { result } = renderHook(() => useSubmission(initData));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.canSubmit).toBe(false);
    expect(result.current.isLocked).toBe(true);
  });

  it('should toggle shift on a day', async () => {
    get.mockResolvedValue({
      data: { id: 'w1', status: 'open', days: [{ day_index: 0, blocked: false }] },
      error: null,
    });

    const { result } = renderHook(() => useSubmission(initData));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    act(() => {
      result.current.toggleShift(0, 'morning');
    });

    expect(result.current.days[0].shifts.morning.active).toBe(true);
  });

  it('returns ok:true only when the backend echoes a persisted submission (id)', async () => {
    get.mockResolvedValue({
      data: { id: 'w1', status: 'open', days: [{ day_index: 0, blocked: false }] },
      error: null,
    });
    post.mockResolvedValue({ data: { id: 'sub1', submitted_at: 'now' }, error: null });

    const { result } = renderHook(() => useSubmission(initData));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    let res;
    await act(async () => {
      res = await result.current.submit();
    });

    expect(res).toEqual({ ok: true, error: null });
    expect(post).toHaveBeenCalledWith(
      expect.stringContaining('submissions'),
      expect.objectContaining({ week_id: 'w1' }),
      initData,
    );
  });

  it('does NOT treat a 2xx without a submission body as success', async () => {
    get.mockResolvedValue({
      data: { id: 'w1', status: 'open', days: [{ day_index: 0, blocked: false }] },
      error: null,
    });
    // 2xx but no persisted submission echoed back → must not be a "success".
    post.mockResolvedValue({ data: { success: true }, error: null });

    const { result } = renderHook(() => useSubmission(initData));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    let res;
    await act(async () => {
      res = await result.current.submit();
    });

    expect(res.ok).toBe(false);
    expect(result.current.error).toBeTruthy();
  });

  it('should prefill an existing submission (date→day_index, shift_windows→shifts)', async () => {
    get.mockImplementation((path) => {
      if (path.includes('current-week')) {
        return Promise.resolve({
          data: {
            id: 'w1',
            status: 'open',
            start_date: '2026-06-14',
            days: [
              { day_index: 0, blocked: false },
              { day_index: 1, blocked: false },
            ],
          },
          error: null,
        });
      }
      if (path.includes('my')) {
        return Promise.resolve({
          data: {
            general_notes: 'לא זמין בערב',
            days: [
              {
                date: '2026-06-15', // day_index 1
                is_available: true,
                shift_windows: [
                  {
                    shift_type: 'morning',
                    start_time: '06:00:00',
                    end_time: '14:00:00',
                  },
                ],
              },
            ],
          },
          error: null,
        });
      }
      return Promise.resolve({ data: null, error: null });
    });

    const { result } = renderHook(() => useSubmission(initData));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Day 1 has the submitted morning shift, with hours trimmed to HH:MM
    const day1 = result.current.days[1];
    expect(day1.shifts.morning.active).toBe(true);
    expect(day1.shifts.morning.from_hour).toBe('06:00');
    expect(day1.shifts.morning.to_hour).toBe('14:00');
    // Day 0 was not submitted → stays inactive
    expect(result.current.days[0].shifts.morning.active).toBe(false);
    // Notes are prefilled from general_notes
    expect(result.current.notes).toBe('לא זמין בערב');
  });

  it('should handle submit error', async () => {
    get.mockResolvedValue({
      data: { id: 'w1', status: 'open', days: [] },
      error: null,
    });
    post.mockResolvedValue({ data: null, error: 'שגיאה' });

    const { result } = renderHook(() => useSubmission(initData));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    await act(async () => {
      await result.current.submit();
    });

    expect(result.current.error).toBe('שגיאה');
  });
});