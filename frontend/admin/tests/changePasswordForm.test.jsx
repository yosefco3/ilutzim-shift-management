import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../src/api/adminApiClient', () => ({
  changeAdminPassword: vi.fn(),
}));

const toast = { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() };
vi.mock('../src/components/Toast', () => ({
  useToast: () => toast,
}));

import { changeAdminPassword } from '../src/api/adminApiClient';
import ChangePasswordForm from '../src/components/ChangePasswordForm';

function fill(current, next, confirm) {
  fireEvent.change(screen.getByLabelText('סיסמה נוכחית'), { target: { value: current } });
  fireEvent.change(screen.getByLabelText('סיסמה חדשה'), { target: { value: next } });
  fireEvent.change(screen.getByLabelText('אימות סיסמה חדשה'), { target: { value: confirm } });
}

function submit() {
  fireEvent.click(screen.getByRole('button', { name: 'החלף סיסמה' }));
}

describe('ChangePasswordForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    changeAdminPassword.mockResolvedValue({ success: true });
  });

  it('renders the three password fields', () => {
    render(<ChangePasswordForm />);
    expect(screen.getByLabelText('סיסמה נוכחית')).toBeInTheDocument();
    expect(screen.getByLabelText('סיסמה חדשה')).toBeInTheDocument();
    expect(screen.getByLabelText('אימות סיסמה חדשה')).toBeInTheDocument();
  });

  it('blocks submit when new and confirm do not match', async () => {
    render(<ChangePasswordForm />);
    fill('oldpass1234', 'newpass5678', 'different999');
    submit();
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(changeAdminPassword).not.toHaveBeenCalled();
  });

  it('blocks submit when new password is too weak', async () => {
    render(<ChangePasswordForm />);
    fill('oldpass1234', 'short', 'short');
    submit();
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(changeAdminPassword).not.toHaveBeenCalled();
  });

  it('calls API with the right args and shows success toast', async () => {
    render(<ChangePasswordForm />);
    fill('oldpass1234', 'newpass5678', 'newpass5678');
    submit();
    await waitFor(() =>
      expect(changeAdminPassword).toHaveBeenCalledWith('oldpass1234', 'newpass5678'),
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it('surfaces the backend error message on failure', async () => {
    changeAdminPassword.mockRejectedValueOnce(new Error('סיסמה נוכחית שגויה'));
    render(<ChangePasswordForm />);
    fill('wrongpass99', 'newpass5678', 'newpass5678');
    submit();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('סיסמה נוכחית שגויה'));
  });
});
