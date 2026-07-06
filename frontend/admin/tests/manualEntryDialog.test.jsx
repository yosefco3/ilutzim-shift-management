import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../src/api/attendanceApiClient', () => ({
  postAttendanceManualEntry: vi.fn(),
}));
vi.mock('../src/hooks/useGuards', () => ({ useGuards: vi.fn() }));

import { postAttendanceManualEntry } from '../src/api/attendanceApiClient';
import { useGuards } from '../src/hooks/useGuards';
import ManualEntryDialog from '../src/components/attendance/ManualEntryDialog';

const GUARDS = [
  { id: 'g-tg', first_name: 'עם', last_name: 'טלגרם', telegram_id: '111', is_active: true },
  { id: 'g-no', first_name: 'בלי', last_name: 'טלגרם', telegram_id: null, is_active: true },
  { id: 'g-off', first_name: 'לא', last_name: 'פעיל', telegram_id: null, is_active: false },
];

describe('ManualEntryDialog', () => {
  const onSaved = vi.fn();
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    useGuards.mockReturnValue({ guards: GUARDS, loading: false });
    postAttendanceManualEntry.mockResolvedValue({});
  });

  it('sorts guards without telegram first (tagged 📵) and hides inactive', () => {
    render(
      <ManualEntryDialog date="2026-07-05" onSaved={onSaved} onClose={onClose} />,
    );
    const options = screen.getAllByRole('option').map((o) => o.textContent);
    expect(options[1]).toContain('📵');
    expect(options[1]).toContain('בלי טלגרם');
    expect(options[2]).toContain('עם טלגרם');
    expect(options.join()).not.toContain('לא פעיל');
  });

  it('selecting a no-telegram guard auto-fills the default reason', () => {
    render(
      <ManualEntryDialog date="2026-07-05" onSaved={onSaved} onClose={onClose} />,
    );
    fireEvent.change(screen.getByLabelText('עובד'), { target: { value: 'g-no' } });
    expect(screen.getByLabelText('סיבה')).toHaveValue('עובד ללא טלגרם');
  });

  it('"לפי הסידור" prefills the planned window', () => {
    render(
      <ManualEntryDialog
        date="2026-07-05"
        plannedByUser={{
          'g-no': [
            { start: '2026-07-05T07:00:00', end: '2026-07-05T15:00:00' },
          ],
        }}
        onSaved={onSaved}
        onClose={onClose}
      />,
    );
    fireEvent.change(screen.getByLabelText('עובד'), { target: { value: 'g-no' } });
    fireEvent.click(screen.getByRole('button', { name: '⚡ לפי הסידור' }));
    expect(screen.getByLabelText('שעת כניסה')).toHaveValue('07:00');
    expect(screen.getByLabelText('שעת יציאה')).toHaveValue('15:00');
  });

  it('submits the full entry and refreshes', async () => {
    render(
      <ManualEntryDialog
        date="2026-07-05"
        plannedByUser={{
          'g-no': [
            { start: '2026-07-05T07:00:00', end: '2026-07-05T15:00:00' },
          ],
        }}
        onSaved={onSaved}
        onClose={onClose}
      />,
    );
    fireEvent.change(screen.getByLabelText('עובד'), { target: { value: 'g-no' } });
    fireEvent.click(screen.getByRole('button', { name: '⚡ לפי הסידור' }));
    fireEvent.click(screen.getByRole('button', { name: 'אישור' }));

    await waitFor(() => expect(postAttendanceManualEntry).toHaveBeenCalledWith({
      user_id: 'g-no',
      date: '2026-07-05',
      check_in: '07:00',
      check_out: '15:00',
      reason: 'עובד ללא טלגרם',
    }));
    expect(onSaved).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it('blocks submit without a guard or check-in', async () => {
    render(
      <ManualEntryDialog date="2026-07-05" onSaved={onSaved} onClose={onClose} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'אישור' }));
    expect(await screen.findByText('יש לבחור עובד')).toBeInTheDocument();
    expect(postAttendanceManualEntry).not.toHaveBeenCalled();
  });
});
