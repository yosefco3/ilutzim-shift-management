import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../src/api/attendanceApiClient', () => ({
  postAttendanceAdjustment: vi.fn(),
}));

import { postAttendanceAdjustment } from '../src/api/attendanceApiClient';
import AttendanceEditDialog from '../src/components/attendance/AttendanceEditDialog';

const day = (overrides = {}) => ({
  user_id: 'u1',
  user_name: 'יוסי כהן',
  date: '2026-07-05',
  planned: [],
  actual: [
    {
      shift_id: 's1',
      check_in_at: '2026-07-05T07:02:00',
      check_out_raw: '2026-07-05T15:01:00',
      check_out_rounded: '2026-07-05T15:15:00',
      status: 'complete',
      in_source: 'telegram',
      out_source: 'manual',
      out_of_radius: false,
      in_event_id: 'ev-in',
      out_event_id: 'ev-out',
    },
  ],
  segments: [],
  summary: { severity: 'ok', tag: 'תקין ✔', orphan_out_times: [] },
  ...overrides,
});

describe('AttendanceEditDialog', () => {
  const onSaved = vi.fn();
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    postAttendanceAdjustment.mockResolvedValue({
      adjustment: { id: 'a1' },
      day: day(),
    });
  });

  it('lists the punches with manual marker', () => {
    render(<AttendanceEditDialog day={day()} onSaved={onSaved} onClose={onClose} />);
    expect(screen.getByText('07:02')).toBeInTheDocument();
    expect(screen.getByText('15:01').parentElement.textContent).toContain('✎');
  });

  it('void requires a reason, then posts and hands back the fresh day', async () => {
    render(<AttendanceEditDialog day={day()} onSaved={onSaved} onClose={onClose} />);
    fireEvent.click(screen.getAllByRole('button', { name: 'בטל החתמה' })[0]);
    fireEvent.click(screen.getByRole('button', { name: 'אישור' }));
    expect(await screen.findByText('נדרשת סיבה לתיקון')).toBeInTheDocument();
    expect(postAttendanceAdjustment).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('סיבה'), { target: { value: 'בטעות' } });
    fireEvent.click(screen.getByRole('button', { name: 'אישור' }));
    await waitFor(() => expect(postAttendanceAdjustment).toHaveBeenCalledWith({
      action: 'void_punch',
      reason: 'בטעות',
      event_id: 'ev-in',
    }));
    expect(onSaved).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it('edit time posts the new timestamp on the same day', async () => {
    render(<AttendanceEditDialog day={day()} onSaved={onSaved} onClose={onClose} />);
    fireEvent.click(screen.getAllByRole('button', { name: 'תקן שעה' })[1]); // the out punch
    fireEvent.change(screen.getByLabelText('שעה'), { target: { value: '16:30' } });
    fireEvent.change(screen.getByLabelText('סיבה'), { target: { value: 'נשאר לתגבור' } });
    fireEvent.click(screen.getByRole('button', { name: 'אישור' }));
    await waitFor(() => expect(postAttendanceAdjustment).toHaveBeenCalledWith({
      action: 'edit_time',
      reason: 'נשאר לתגבור',
      event_id: 'ev-out',
      punched_at: '2026-07-05T16:30:00',
    }));
  });

  it('a no-show day offers absence approval', async () => {
    render(
      <AttendanceEditDialog
        day={day({ actual: [] })}
        onSaved={onSaved}
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'סמן היעדרות מאושרת' }));
    fireEvent.change(screen.getByLabelText('סיבה'), { target: { value: 'מחלה' } });
    fireEvent.click(screen.getByRole('button', { name: 'אישור' }));
    await waitFor(() => expect(postAttendanceAdjustment).toHaveBeenCalledWith({
      action: 'mark_absence',
      reason: 'מחלה',
      user_id: 'u1',
      work_date: '2026-07-05',
    }));
  });

  it('lists an orphan OUT (out-without-in) as an editable row, in time order', async () => {
    const d = day({
      summary: {
        severity: 'big', tag: 'יציאה בלי כניסה',
        orphan_out_times: ['18:48'],
        orphan_outs: [{ event_id: 'ev-orphan', punched_at: '2026-07-05T18:48:00', source: 'telegram' }],
      },
    });
    render(<AttendanceEditDialog day={d} onSaved={onSaved} onClose={onClose} />);
    // shown after the paired punches (sorted by time) and tagged as orphan
    expect(screen.getByText('18:48')).toBeInTheDocument();
    expect(screen.getByText('18:48').parentElement.textContent).toContain('(ללא כניסה)');

    // its void action targets the orphan's own event id
    fireEvent.click(screen.getAllByRole('button', { name: 'בטל החתמה' })[2]);
    fireEvent.change(screen.getByLabelText('סיבה'), { target: { value: 'החתמה כפולה' } });
    fireEvent.click(screen.getByRole('button', { name: 'אישור' }));
    await waitFor(() => expect(postAttendanceAdjustment).toHaveBeenCalledWith({
      action: 'void_punch',
      reason: 'החתמה כפולה',
      event_id: 'ev-orphan',
    }));
  });

  it('add punch posts direction and time', async () => {
    render(<AttendanceEditDialog day={day()} onSaved={onSaved} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: 'הוסף החתמה' }));
    fireEvent.change(screen.getByLabelText('כיוון'), { target: { value: 'out' } });
    fireEvent.change(screen.getByLabelText('שעה'), { target: { value: '19:00' } });
    fireEvent.change(screen.getByLabelText('סיבה'), { target: { value: 'תקלה' } });
    fireEvent.click(screen.getByRole('button', { name: 'אישור' }));
    await waitFor(() => expect(postAttendanceAdjustment).toHaveBeenCalledWith({
      action: 'add_punch',
      reason: 'תקלה',
      user_id: 'u1',
      direction: 'out',
      punched_at: '2026-07-05T19:00:00',
    }));
  });
});
