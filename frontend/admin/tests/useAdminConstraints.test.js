import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useAdminConstraints } from '../src/hooks/useAdminConstraints';

vi.mock('../src/api/adminApiClient', () => ({
  fetchGuard: vi.fn(),
  fetchWeeks: vi.fn(),
  fetchGuardSubmission: vi.fn(),
  createGuardSubmission: vi.fn(),
}));

vi.mock('../src/api/guardApiClient.js', () => ({
  get: vi.fn(),
}));

import {
  fetchGuard,
  fetchWeeks,
  fetchGuardSubmission,
  createGuardSubmission,
} from '../src/api/adminApiClient';
import { get as guardGet } from '../src/api/guardApiClient.js';

describe('useAdminConstraints', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    fetchGuard.mockResolvedValue({ id: 'g1', first_name: 'דנה', last_name: 'כהן' });
    fetchWeeks.mockResolvedValue([
      { id: 'w1', status: 'open', week_label: 'שבוע 1', start_date: '2025-06-01' },
      { id: 'w2', status: 'closed', week_label: 'שבוע 2', start_date: '2025-06-08' },
    ]);
    fetchGuardSubmission.mockResolvedValue(null);
    guardGet.mockResolvedValue({ data: null, error: 'x' });
    createGuardSubmission.mockResolvedValue({ id: 's1' });
  });

  it('loads guard + weeks and defaults to the open week with 7 day rows', async () => {
    const { result } = renderHook(() => useAdminConstraints('g1'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.guard.first_name).toBe('דנה');
    expect(result.current.weeks).toHaveLength(2);
    expect(result.current.selectedWeekId).toBe('w1'); // the open week

    await waitFor(() => expect(result.current.days).toHaveLength(7));
  });

  it('pre-fills an existing submission (incl. Telegram) for the selected week', async () => {
    fetchGuardSubmission.mockResolvedValue({
      week_id: 'w1',
      general_notes: 'הערה',
      days: [
        {
          date: '2025-06-01', // day_index 0
          shift_windows: [
            { shift_type: 'morning', start_time: '07:00:00', end_time: '15:00:00' },
          ],
        },
      ],
    });

    const { result } = renderHook(() => useAdminConstraints('g1'));
    await waitFor(() => expect(result.current.days).toHaveLength(7));

    // Fetched for the selected guard + week
    expect(fetchGuardSubmission).toHaveBeenCalledWith('g1', 'w1');

    const day0 = result.current.days.find((d) => d.day_index === 0);
    expect(day0.shifts.morning.active).toBe(true);
    expect(day0.shifts.morning.from_hour).toBe('07:00');
    expect(result.current.notes).toBe('הערה');
  });

  it('can edit a closed/locked week (editing allowed pre-publish)', async () => {
    // Select the closed/locked-style week — editing must still work.
    const { result } = renderHook(() => useAdminConstraints('g1'));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.setSelectedWeekId('w2'));
    await waitFor(() => expect(result.current.selectedWeekId).toBe('w2'));
    await waitFor(() => expect(result.current.days).toHaveLength(7));

    act(() => result.current.toggleShift(0, 'morning'));
    await act(async () => {
      await result.current.submit();
    });

    expect(createGuardSubmission).toHaveBeenCalledTimes(1);
    expect(createGuardSubmission.mock.calls[0][0].week_id).toBe('w2');
    expect(result.current.saved).toBe(true);
  });

  it('blocks editing a locked (final) week: isPublished + submit is a no-op', async () => {
    fetchWeeks.mockResolvedValue([
      { id: 'wp', status: 'locked', week_label: 'שבוע נעול', start_date: '2025-06-01' },
    ]);

    const { result } = renderHook(() => useAdminConstraints('g1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await waitFor(() => expect(result.current.selectedWeekId).toBe('wp'));

    expect(result.current.isPublished).toBe(true);

    let returned;
    await act(async () => {
      returned = await result.current.submit();
    });

    expect(returned).toBe(false);
    expect(createGuardSubmission).not.toHaveBeenCalled();
  });

  it('defaults to the editable (closed) week, never a locked week', async () => {
    // Regression: with no OPEN week, the default used to land on whatever week
    // came first in the unordered list — often the LOCKED current week, which
    // is read-only. It must prefer the editable CLOSED week instead. Order the
    // list locked-first to prove the fix does not rely on list position.
    fetchWeeks.mockResolvedValue([
      { id: 'wlock', status: 'locked', week_label: 'שבוע נעול', start_date: '2025-06-15' },
      { id: 'wclosed', status: 'closed', week_label: 'שבוע סגור', start_date: '2025-06-22' },
    ]);

    const { result } = renderHook(() => useAdminConstraints('g1'));
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.selectedWeekId).toBe('wclosed');
    expect(result.current.isPublished).toBe(false);
  });

  it('builds the payload with user_id + week_id and only active shifts', async () => {
    const { result } = renderHook(() => useAdminConstraints('g1'));
    await waitFor(() => expect(result.current.days).toHaveLength(7));

    act(() => result.current.toggleShift(2, 'night'));
    await act(async () => {
      await result.current.submit();
    });

    expect(createGuardSubmission).toHaveBeenCalledTimes(1);
    const payload = createGuardSubmission.mock.calls[0][0];
    expect(payload.user_id).toBe('g1');
    expect(payload.week_id).toBe('w1');

    const day2 = payload.days.find((d) => d.day_index === 2);
    expect(day2.shifts).toHaveLength(1);
    expect(day2.shifts[0].shift_type).toBe('night');

    // Untouched days carry no active shifts
    const day0 = payload.days.find((d) => d.day_index === 0);
    expect(day0.shifts).toHaveLength(0);

    expect(result.current.saved).toBe(true);
  });
});
