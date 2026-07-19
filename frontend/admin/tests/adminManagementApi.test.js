/**
 * Multi-admin step 05 — role storage on login/logout and the admin-management
 * API client functions (URL/method/body shape).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  adminLogin,
  adminLogout,
  getAdminRole,
  listAdmins,
  createAdmin,
  setAdminActive,
  resetAdminPassword,
} from '../src/api/adminApiClient';

global.fetch = vi.fn();

function mockJson(data, status = 200) {
  fetch.mockResolvedValueOnce({
    ok: status < 400,
    status,
    json: async () => data,
  });
}

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
});

describe('role storage', () => {
  it('login stores token and role', async () => {
    mockJson({ access_token: 'tok', role: 'super_admin', admin_id: 1 });
    await adminLogin('boss@a.com', 'strongpass1');

    expect(localStorage.getItem('admin_token')).toBe('tok');
    expect(getAdminRole()).toBe('super_admin');
  });

  it('logout clears token and role', async () => {
    mockJson({ access_token: 'tok', role: 'admin', admin_id: 2 });
    await adminLogin('second@a.com', 'strongpass1');

    adminLogout();
    expect(localStorage.getItem('admin_token')).toBeNull();
    expect(getAdminRole()).toBeNull();
  });

  it('401 auto-logout clears the role too', async () => {
    localStorage.setItem('admin_token', 'tok');
    localStorage.setItem('admin_role', 'admin');
    // jsdom: window.location.href assignment is tolerated in vitest jsdom env
    fetch.mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) });

    await expect(listAdmins()).rejects.toThrow();
    expect(getAdminRole()).toBeNull();
  });
});

describe('admin management functions', () => {
  beforeEach(() => {
    localStorage.setItem('admin_token', 'tok');
  });

  it('listAdmins GETs /auth/admin/admins', async () => {
    mockJson({ admins: [], count: 0 });
    await listAdmins();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/auth/admin/admins'),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer tok' }),
      }),
    );
  });

  it('createAdmin POSTs snake_case body', async () => {
    mockJson({ id: 3 }, 201);
    await createAdmin({ email: 'x@a.com', fullName: 'דוד', password: 'abcd123456' });
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toContain('/auth/admin/admins');
    expect(opts.method).toBe('POST');
    expect(JSON.parse(opts.body)).toEqual({
      email: 'x@a.com',
      full_name: 'דוד',
      password: 'abcd123456',
    });
  });

  it('setAdminActive PATCHes the active flag', async () => {
    mockJson({ id: 3, is_active: false });
    await setAdminActive(3, false);
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toContain('/auth/admin/admins/3/active');
    expect(opts.method).toBe('PATCH');
    expect(JSON.parse(opts.body)).toEqual({ active: false });
  });

  it('resetAdminPassword POSTs new_password', async () => {
    mockJson({ success: true });
    await resetAdminPassword(3, 'newpass1234');
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toContain('/auth/admin/admins/3/reset-password');
    expect(opts.method).toBe('POST');
    expect(JSON.parse(opts.body)).toEqual({ new_password: 'newpass1234' });
  });
});
