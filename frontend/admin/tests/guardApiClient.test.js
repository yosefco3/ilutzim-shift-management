import { describe, it, expect, vi, beforeEach } from 'vitest';
import { get, post } from '../src/api/guardApiClient';

// Mock fetch
global.fetch = vi.fn();

beforeEach(() => {
  vi.resetAllMocks();
});

describe('guardApiClient', () => {
  const initData = 'test-init-data';

  describe('get', () => {
    it('should send GET with X-Telegram-Init-Data header', async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ week_id: '123' }),
      });

      const { data, error } = await get('/submissions/current-week', initData);

      expect(error).toBeNull();
      expect(data).toEqual({ week_id: '123' });
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/submissions/current-week'),
        expect.objectContaining({
          headers: expect.objectContaining({
            'X-Telegram-Init-Data': initData,
          }),
        }),
      );
    });

    it('should return error on 401', async () => {
      fetch.mockResolvedValueOnce({ ok: false, status: 401 });
      const { error } = await get('/test', initData);
      expect(error).toContain('אימות');
    });

    it('should return error on network failure', async () => {
      fetch.mockRejectedValueOnce(new Error('Network error'));
      const { error } = await get('/test', initData);
      expect(error).toContain('תקשורת');
    });
  });

  describe('post', () => {
    it('should send POST with body and initData', async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => ({ success: true }),
      });

      const { data, error } = await post('/submissions/submit', { week_id: '123' }, initData);

      expect(error).toBeNull();
      expect(data).toEqual({ success: true });
    });

    it('should return error on 403 (locked)', async () => {
      fetch.mockResolvedValueOnce({ ok: false, status: 403 });
      const { error } = await post('/test', {}, initData);
      expect(error).toContain('נעול');
    });

    it('surfaces the backend detail message on rejection', async () => {
      fetch.mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: async () => ({ detail: 'ניתן להגיש רק לשבוע הפתוח הנוכחי.' }),
      });
      const { error } = await post('/submissions', {}, initData);
      expect(error).toBe('ניתן להגיש רק לשבוע הפתוח הנוכחי.');
    });

    it('keeps the friendly auth hint on 401 even if a detail is present', async () => {
      fetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Invalid Telegram auth' }),
      });
      const { error } = await post('/submissions', {}, initData);
      expect(error).toContain('אימות');
    });
  });

  describe('get current week', () => {
    it('should call GET /submissions/current-week', async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ id: 'abc', status: 'open' }),
      });

      const { data } = await get('/submissions/current-week', initData);
      expect(data.id).toBe('abc');
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/submissions/current-week'),
        expect.any(Object),
      );
    });
  });
});