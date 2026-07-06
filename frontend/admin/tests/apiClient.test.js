import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as adminApi from '../src/api/adminApiClient';

describe('Admin API Client', () => {
  beforeEach(() => {
    localStorage.clear();
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('has all required API methods', () => {
    expect(typeof adminApi.adminLogin).toBe('function');
    expect(typeof adminApi.adminLogout).toBe('function');
    expect(typeof adminApi.fetchGuards).toBe('function');
    expect(typeof adminApi.createGuard).toBe('function');
    expect(typeof adminApi.updateGuard).toBe('function');
    expect(typeof adminApi.deleteGuard).toBe('function');
    expect(typeof adminApi.fetchWeeks).toBe('function');
    expect(typeof adminApi.createWeek).toBe('function');
    expect(typeof adminApi.fetchSubmissions).toBe('function');
    expect(typeof adminApi.fetchSettings).toBe('function');
    expect(typeof adminApi.updateSettings).toBe('function');
    expect(typeof adminApi.exportWeekExcel).toBe('function');
  });

  it('login sends POST with credentials and stores token', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ access_token: 'token123' }),
    });

    const result = await adminApi.adminLogin('admin', 'password');

    expect(global.fetch).toHaveBeenCalledOnce();
    const call = global.fetch.mock.calls[0];
    expect(call[1].method).toBe('POST');
    const body = JSON.parse(call[1].body);
    expect(body.username).toBe('admin');
    expect(body.password).toBe('password');
    expect(result.access_token).toBe('token123');
    expect(localStorage.getItem('admin_token')).toBe('token123');
  });

  it('sends auth header when token exists', async () => {
    localStorage.setItem('admin_token', 'my-token');
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ([]),
    });

    await adminApi.fetchGuards();

    const call = global.fetch.mock.calls[0];
    expect(call[1].headers.Authorization).toBe('Bearer my-token');
  });

  it('changeAdminPassword posts current + new password to the endpoint', async () => {
    localStorage.setItem('admin_token', 'my-token');
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ success: true }),
    });

    await adminApi.changeAdminPassword('oldpass1234', 'newpass5678');

    const call = global.fetch.mock.calls[0];
    expect(call[0]).toContain('/auth/admin/change-password');
    expect(call[1].method).toBe('POST');
    const body = JSON.parse(call[1].body);
    expect(body.current_password).toBe('oldpass1234');
    expect(body.new_password).toBe('newpass5678');
  });

  it('surfaces app-exception `error` field on failure', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      json: async () => ({ success: false, error: 'סיסמה נוכחית שגויה' }),
    });

    await expect(adminApi.changeAdminPassword('x', 'y')).rejects.toThrow('סיסמה נוכחית שגויה');
  });

  it('throws on failed request', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Server Error',
      json: async () => ({ detail: 'Server error' }),
    });

    await expect(adminApi.fetchGuards()).rejects.toThrow('Server error');
  });
});