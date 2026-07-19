/**
 * Multi-admin step 06 — AdminsSection: role-gated visibility, create flow,
 * and no deactivate action on super-admin rows.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const toast = { success: vi.fn(), error: vi.fn() };
vi.mock('../src/components/Toast', () => ({ useToast: () => toast }));

vi.mock('../src/api/adminApiClient', () => ({
  getAdminRole: vi.fn(),
  listAdmins: vi.fn(),
  createAdmin: vi.fn(),
  setAdminActive: vi.fn(),
  resetAdminPassword: vi.fn(),
}));

import {
  getAdminRole,
  listAdmins,
  createAdmin,
  setAdminActive,
} from '../src/api/adminApiClient';
import AdminsSection from '../src/components/AdminsSection';

const BOSS = {
  id: 1,
  email: 'boss@a.com',
  full_name: 'יוסף',
  role: 'super_admin',
  is_active: true,
};
const SECOND = {
  id: 2,
  email: 'second@a.com',
  full_name: 'דוד',
  role: 'admin',
  is_active: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  listAdmins.mockResolvedValue({ admins: [BOSS, SECOND], count: 2 });
});

describe('AdminsSection', () => {
  it('renders the admins table with role and status', async () => {
    render(<AdminsSection />);
    await waitFor(() => expect(screen.getByText('boss@a.com')).toBeInTheDocument());
    expect(screen.getByText('דוד')).toBeInTheDocument();
    expect(screen.getByText('סופר-אדמין')).toBeInTheDocument();
  });

  it('super-admin row has no deactivate/reset actions; admin row does', async () => {
    render(<AdminsSection />);
    await waitFor(() => expect(screen.getByText('boss@a.com')).toBeInTheDocument());

    // Exactly one deactivate and one reset button — for the regular admin only.
    expect(screen.getAllByRole('button', { name: 'השבתה' })).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: 'איפוס סיסמה' })).toHaveLength(1);
  });

  it('create flow calls createAdmin and refreshes the list', async () => {
    createAdmin.mockResolvedValue({ id: 3 });
    render(<AdminsSection />);
    await waitFor(() => expect(listAdmins).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole('button', { name: 'הוספת אדמין' }));
    fireEvent.change(screen.getByLabelText('שם מלא'), { target: { value: 'שלישי' } });
    fireEvent.change(screen.getByLabelText('כתובת מייל'), {
      target: { value: 'third@a.com' },
    });
    fireEvent.change(screen.getByLabelText('סיסמה ראשונית'), {
      target: { value: 'abcd123456' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'צור אדמין' }));

    await waitFor(() =>
      expect(createAdmin).toHaveBeenCalledWith({
        email: 'third@a.com',
        fullName: 'שלישי',
        password: 'abcd123456',
      }),
    );
    await waitFor(() => expect(listAdmins).toHaveBeenCalledTimes(2));
    expect(toast.success).toHaveBeenCalled();
  });

  it('weak initial password is blocked client-side', async () => {
    render(<AdminsSection />);
    await waitFor(() => expect(listAdmins).toHaveBeenCalled());

    fireEvent.click(screen.getByRole('button', { name: 'הוספת אדמין' }));
    fireEvent.change(screen.getByLabelText('שם מלא'), { target: { value: 'x' } });
    fireEvent.change(screen.getByLabelText('כתובת מייל'), {
      target: { value: 'x@a.com' },
    });
    fireEvent.change(screen.getByLabelText('סיסמה ראשונית'), {
      target: { value: 'short' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'צור אדמין' }));

    expect(createAdmin).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalled();
  });

  it('deactivate asks for confirmation then calls setAdminActive', async () => {
    setAdminActive.mockResolvedValue({ ...SECOND, is_active: false });
    render(<AdminsSection />);
    await waitFor(() => expect(screen.getByText('second@a.com')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'השבתה' }));
    expect(setAdminActive).not.toHaveBeenCalled(); // waits for confirm

    // The dialog's confirm button carries the same label.
    const buttons = screen.getAllByRole('button', { name: 'השבתה' });
    fireEvent.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(setAdminActive).toHaveBeenCalledWith(2, false));
  });
});

describe('SettingsPage gating', () => {
  it('shows the section only for super_admin', async () => {
    vi.doMock('../src/hooks/useSettings', () => ({
      useSettings: () => ({
        settings: [],
        draft: {},
        dirty: false,
        saving: false,
        error: null,
        setValue: vi.fn(),
        handleSave: vi.fn(),
      }),
    }));
    const { default: SettingsPage } = await import('../src/pages/SettingsPage');

    getAdminRole.mockReturnValue('admin');
    const { unmount } = render(<SettingsPage />);
    expect(screen.queryByText('ניהול אדמינים')).not.toBeInTheDocument();
    unmount();

    getAdminRole.mockReturnValue('super_admin');
    render(<SettingsPage />);
    await waitFor(() =>
      expect(screen.getByText('ניהול אדמינים')).toBeInTheDocument(),
    );
  });
});
