import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import LockBanner from '../src/components/guard/LockBanner';
import DayRow from '../src/components/guard/DayRow';

describe('LockBanner', () => {
  it('should render locked message', () => {
    render(<LockBanner status="locked" />);
    expect(screen.getByText(/נסגרה|נעול|לא נפתח/)).toBeInTheDocument();
  });

  it('should render closed (submissions currently closed) message', () => {
    render(<LockBanner status="closed" />);
    expect(screen.getByText(/סגורה כרגע/)).toBeInTheDocument();
  });

  it('should render no-week message when status is null', () => {
    render(<LockBanner status={null} />);
    expect(screen.getByText(/אין שבוע/)).toBeInTheDocument();
  });
});

describe('DayRow', () => {
  // New model: shifts is an object keyed by shift_type, each with active/hours.
  const makeShifts = (overrides = {}) => ({
    morning: { active: false, from_hour: '', to_hour: '' },
    afternoon: { active: false, from_hour: '', to_hour: '' },
    night: { active: false, from_hour: '', to_hour: '' },
    ...overrides,
  });

  const baseDay = {
    day_index: 0,
    blocked: false,
    shifts: makeShifts(),
  };

  const renderRow = (day, props = {}) =>
    render(
      <DayRow
        day={day}
        disabled={false}
        onToggleShift={vi.fn()}
        onSetShiftHours={vi.fn()}
        {...props}
      />,
    );

  it('should render day name', () => {
    renderRow(baseDay);
    expect(screen.getByText('יום ראשון')).toBeInTheDocument();
  });

  it('should show shift toggle buttons', () => {
    renderRow(baseDay);
    expect(screen.getByText('בוקר')).toBeInTheDocument();
    expect(screen.getByText('ערב')).toBeInTheDocument();
    expect(screen.getByText('לילה')).toBeInTheDocument();
  });

  it('should call onToggleShift with day index and shift type when clicked', () => {
    const onToggleShift = vi.fn();
    renderRow(baseDay, { onToggleShift });
    fireEvent.click(screen.getByText('בוקר'));
    expect(onToggleShift).toHaveBeenCalledWith(0, 'morning');
  });

  it('should show blocked badge and hide shifts when day is blocked', () => {
    renderRow({ ...baseDay, blocked: true });
    expect(screen.getByText('חסום')).toBeInTheDocument();
    expect(screen.queryByText('בוקר')).not.toBeInTheDocument();
  });

  it('should show hours inputs when a shift is active', () => {
    const day = {
      ...baseDay,
      shifts: makeShifts({
        morning: { active: true, from_hour: '07:00', to_hour: '16:00' },
      }),
    };
    renderRow(day);
    expect(screen.getByDisplayValue('07:00')).toBeInTheDocument();
    expect(screen.getByDisplayValue('16:00')).toBeInTheDocument();
  });

  it('should call onSetShiftHours when an hour input changes', () => {
    const onSetShiftHours = vi.fn();
    const day = {
      ...baseDay,
      shifts: makeShifts({
        morning: { active: true, from_hour: '07:00', to_hour: '16:00' },
      }),
    };
    renderRow(day, { onSetShiftHours });
    fireEvent.change(screen.getByDisplayValue('07:00'), {
      target: { value: '08:00' },
    });
    expect(onSetShiftHours).toHaveBeenCalledWith(0, 'morning', '08:00', '16:00');
  });

  it('should render hours as half-hour dropdowns (no free-text input)', () => {
    const day = {
      ...baseDay,
      shifts: makeShifts({
        morning: { active: true, from_hour: '07:00', to_hour: '16:30' },
      }),
    };
    const { container } = renderRow(day);
    const selects = container.querySelectorAll('select.hour-input');
    expect(selects).toHaveLength(2);
    // No free-text time inputs remain.
    expect(container.querySelector('input.hour-input')).toBeNull();
    // The start dropdown only offers half-hour slots from 07:00 onward — the
    // security day starts at 07:00, so 00:00–06:30 are not selectable.
    const fromOptions = [...selects[0].options].map((o) => o.value);
    expect(fromOptions).toContain('07:00');
    expect(fromOptions).toContain('23:30');
    expect(fromOptions).not.toContain('00:00');
    expect(fromOptions).not.toContain('06:30');
    expect(fromOptions).not.toContain('07:15');
  });

  it('should disable all buttons when disabled=true', () => {
    renderRow(baseDay, { disabled: true });
    const buttons = screen.getAllByRole('button');
    buttons.forEach((btn) => {
      expect(btn).toBeDisabled();
    });
  });
});