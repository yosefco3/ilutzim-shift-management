import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../src/hooks/useSettings', () => ({
  useSettings: vi.fn(),
}));

import { useSettings } from '../src/hooks/useSettings';
import SettingsPage from '../src/pages/SettingsPage';
import { ToastProvider } from '../src/components/Toast';

// SettingsPage embeds ChangePasswordForm, which uses the toast context.
function render(ui, opts) {
  return rtlRender(<ToastProvider>{ui}</ToastProvider>, opts);
}

function mockHook(overrides = {}) {
  useSettings.mockReturnValue({
    settings: [{ key: 'min_nights', value: '2', description: null }],
    draft: { min_nights: '2' },
    loading: false,
    saving: false,
    error: null,
    dirty: false,
    setValue: vi.fn(),
    save: vi.fn().mockResolvedValue(true),
    ...overrides,
  });
}

describe('SettingsPage', () => {
  beforeEach(() => {
    useSettings.mockReset();
    mockHook();
  });

  it('renders Hebrew labels, not raw keys', () => {
    render(<SettingsPage />);
    expect(screen.getByText('מינימום לילות')).toBeInTheDocument();
    expect(screen.queryByText('min_nights')).not.toBeInTheDocument();
  });

  it('renders the quiz-window field as a number input in the procedures group', () => {
    mockHook({
      settings: [{ key: 'procedure_quiz_window_days', value: '0', description: null }],
      draft: { procedure_quiz_window_days: '0' },
    });
    render(<SettingsPage />);
    const label = screen.getByText('חלון זמינות המבחן (ימים, 0 = ללא הגבלה)');
    expect(label).toBeInTheDocument();
    expect(screen.queryByText('procedure_quiz_window_days')).not.toBeInTheDocument();
  });

  it('does not render any telegram bot token field', () => {
    render(<SettingsPage />);
    expect(screen.queryByText('בוט טלגרם')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'החל טוקן' })).not.toBeInTheDocument();
  });

  it('save button is disabled until dirty', () => {
    render(<SettingsPage />);
    expect(screen.getByRole('button', { name: 'שמור' })).toBeDisabled();
  });

  it('clicking save calls the hook save()', async () => {
    const save = vi.fn().mockResolvedValue(true);
    mockHook({ dirty: true, save });
    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'שמור' }));
    await waitFor(() => expect(save).toHaveBeenCalled());
  });

  // The auto-open/lock window guard: lock must fire strictly after open when
  // both are enabled, otherwise save() is never reached.
  const autoDraft = (overrides) => ({
    auto_open_enabled: 'true',
    auto_open_weekday: 'thursday',
    auto_open_time: '19:00',
    auto_lock_enabled: 'true',
    auto_lock_weekday: 'thursday',
    auto_lock_time: '20:00',
    ...overrides,
  });

  it('blocks save when auto-lock is before auto-open', async () => {
    const save = vi.fn().mockResolvedValue(true);
    mockHook({ dirty: true, save, draft: autoDraft({ auto_lock_time: '18:00' }) });
    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'שמור' }));
    expect(await screen.findByText('הנעילה האוטומטית חייבת להיות אחרי הפתיחה האוטומטית'))
      .toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();
  });

  it('allows save when auto-lock is after auto-open', async () => {
    const save = vi.fn().mockResolvedValue(true);
    mockHook({ dirty: true, save, draft: autoDraft() });
    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'שמור' }));
    await waitFor(() => expect(save).toHaveBeenCalled());
  });

  it('skips the window guard when auto-lock is disabled', async () => {
    const save = vi.fn().mockResolvedValue(true);
    mockHook({
      dirty: true,
      save,
      draft: autoDraft({ auto_lock_enabled: 'false', auto_lock_time: '18:00' }),
    });
    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'שמור' }));
    await waitFor(() => expect(save).toHaveBeenCalled());
  });

  // Stage 3 — the attendance settings section (VITE_ATTENDANCE_ENABLED is
  // unset under vitest, which counts as enabled — same as the builder flag).
  it('renders the attendance section with Hebrew labels, not raw keys', () => {
    mockHook({
      settings: [
        { key: 'attendance_grace_minutes', value: '15', description: null },
        { key: 'attendance_admin_alerts_enabled', value: 'false', description: null },
        { key: 'company_name', value: 'ספרא', description: null },
      ],
      draft: {
        attendance_grace_minutes: '15',
        attendance_admin_alerts_enabled: 'false',
        company_name: 'ספרא',
      },
    });
    render(<SettingsPage />);

    expect(screen.getByText('נוכחות')).toBeInTheDocument();
    expect(screen.getByText('גרייס לאיחור (דקות)')).toBeInTheDocument();
    expect(screen.getByText('התראת טלגרם על אי-הגעה')).toBeInTheDocument();
    expect(screen.getByText('שם החברה (בדוחות השכר)')).toBeInTheDocument();
    expect(screen.queryByText('attendance_grace_minutes')).not.toBeInTheDocument();
    expect(screen.queryByText('company_name')).not.toBeInTheDocument();
  });

  it('pool_show_unsubmitted renders as a switch in the scheduling-rules group and toggles', () => {
    const setValue = vi.fn();
    mockHook({
      settings: [
        { key: 'min_nights', value: '2', description: null },
        { key: 'pool_show_unsubmitted', value: 'true', description: null },
      ],
      draft: { min_nights: '2', pool_show_unsubmitted: 'true' },
      setValue,
    });
    render(<SettingsPage />);

    expect(screen.getByText('כללי שיבוץ')).toBeInTheDocument();
    expect(screen.getByText('הצגת מאבטחים שלא הגישו אילוצים בלוח הסידור')).toBeInTheDocument();
    expect(screen.queryByText('pool_show_unsubmitted')).not.toBeInTheDocument();

    const toggle = screen.getByRole('switch');
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(toggle);
    expect(setValue).toHaveBeenCalledWith('pool_show_unsubmitted', 'false');
  });

  it('attendance alert toggle renders as a switch', () => {
    mockHook({
      settings: [
        { key: 'attendance_admin_alerts_enabled', value: 'false', description: null },
      ],
      draft: { attendance_admin_alerts_enabled: 'false' },
    });
    render(<SettingsPage />);
    expect(screen.getByRole('switch')).toBeInTheDocument();
  });

  it('renders the procedures section with Hebrew labels, not raw keys', () => {
    mockHook({
      settings: [
        { key: 'procedure_pass_threshold', value: '80', description: null },
        { key: 'procedure_quiz_size', value: '7', description: null },
        { key: 'procedure_bank_size', value: '20', description: null },
      ],
      draft: {
        procedure_pass_threshold: '80',
        procedure_quiz_size: '7',
        procedure_bank_size: '20',
      },
    });
    render(<SettingsPage />);

    expect(screen.getByText('נהלים (סד"פ)')).toBeInTheDocument();
    expect(screen.getByText('אחוז עובר במבחן נהלים')).toBeInTheDocument();
    expect(screen.getByText('מספר שאלות במבחן נהלים')).toBeInTheDocument();
    expect(screen.getByText('גודל בנק השאלות להפקה')).toBeInTheDocument();
    expect(screen.queryByText('procedure_bank_size')).not.toBeInTheDocument();
    expect(screen.queryByText('procedure_pass_threshold')).not.toBeInTheDocument();
  });
});
