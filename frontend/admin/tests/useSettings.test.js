import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

vi.mock('../src/api/adminApiClient', () => ({
  fetchSettings: vi.fn(),
  updateSettings: vi.fn(),
}));

import { fetchSettings, updateSettings } from '../src/api/adminApiClient';
import { useSettings } from '../src/hooks/useSettings';

const LIST = [
  { key: 'min_nights', value: '2', description: null },
  { key: 'shift_default_morning', value: '07:00-16:30', description: null },
];

describe('useSettings', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    fetchSettings.mockResolvedValue(LIST);
    updateSettings.mockImplementation(async (map) =>
      LIST.map((s) => (map[s.key] != null ? { ...s, value: map[s.key] } : s)),
    );
  });

  it('loads the settings list and seeds the draft', async () => {
    const { result } = renderHook(() => useSettings());
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.settings).toHaveLength(2);
    expect(result.current.draft.min_nights).toBe('2');
    expect(result.current.dirty).toBe(false);
  });

  it('setValue updates the draft and flags dirty', async () => {
    const { result } = renderHook(() => useSettings());
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.setValue('min_nights', '5'));

    expect(result.current.draft.min_nights).toBe('5');
    expect(result.current.dirty).toBe(true);
  });

  it('save sends only the changed keys and clears dirty', async () => {
    const { result } = renderHook(() => useSettings());
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.setValue('min_nights', '5'));
    await act(async () => { await result.current.save(); });

    expect(updateSettings).toHaveBeenCalledWith({ min_nights: '5' });
    expect(result.current.draft.min_nights).toBe('5');
    expect(result.current.dirty).toBe(false);
  });

  it('surfaces an error when the fetch fails', async () => {
    fetchSettings.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useSettings());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('boom');
  });
});
