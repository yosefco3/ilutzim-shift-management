import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { bulkUpdateDaySchedules } from '../src/api/builderApiClient';

// bulkUpdateDaySchedules ships with the step-03 client (the matrix's Save in
// step 04 will call it). Verify the URL shape + body here, against the shared
// `request` helper (which calls fetch) — mirrors apiClient.test.js.
describe('builderApiClient.bulkUpdateDaySchedules', () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('PUTs { items } to the profile day-schedules endpoint', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ items: [] }),
    });

    const items = [{ position_id: 'pos1', day_schedules: {} }];
    await bulkUpdateDaySchedules('p1', items);

    expect(global.fetch).toHaveBeenCalledOnce();
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toContain('/admin/builder/profiles/p1/positions/day-schedules');
    expect(opts.method).toBe('PUT');
    expect(JSON.parse(opts.body)).toEqual({ items });
  });
});
