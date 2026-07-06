import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import CellPicker from '../src/components/board/CellPicker';

const ROW = {
  position_id: 'pos1',
  name: 'סייר 1',
  required_attributes: ['patrol_vehicle'],
};
const CELL = { day_index: 0, active: true, window: { start: '07:00', end: '15:00' } };

const POOL = [
  // Full coverage, has the required attribute.
  { id: 'u1', full_name: 'בובי ביטון', roles: ['PATROL_VEHICLE'], remaining_hours: 9, availability: { 0: [{ start: '07:00', end: '19:00' }] } },
  // Available but missing the required attribute.
  { id: 'u2', full_name: 'משה שמעון', roles: ['AHMASH'], remaining_hours: 12, availability: { 0: [{ start: '07:00', end: '15:00' }] } },
  // Not available at this window.
  { id: 'u3', full_name: 'רון לוי', roles: ['PATROL_VEHICLE'], remaining_hours: 4, availability: { 0: [{ start: '19:00', end: '23:00' }] } },
];

const attrLabel = (k) => ({ patrol_vehicle: 'רכב סיור' }[k] || k);

function renderPicker(onPick = vi.fn(), onClose = vi.fn()) {
  render(
    <CellPicker
      row={ROW}
      cell={CELL}
      pool={POOL}
      assignedIds={new Set()}
      attrLabel={attrLabel}
      onPick={onPick}
      onClose={onClose}
    />,
  );
}

describe('CellPicker', () => {
  it('shows the window header and coverage labels', () => {
    renderPicker();
    expect(screen.getByText('מי זמין לחלון')).toBeInTheDocument();
    expect(screen.getByText('סייר 1 · ראשון')).toBeInTheDocument();
    expect(screen.getByText('07:00–15:00')).toBeInTheDocument();
    expect(screen.getAllByText('מכסה את כל הנותר').length).toBeGreaterThan(0);
  });

  it('flags a missing required attribute in Hebrew', () => {
    renderPicker();
    expect(screen.getByText(/חסר רכב סיור/)).toBeInTheDocument();
  });

  it('lists guards who are out of availability, flagged and still pickable', () => {
    const onPick = vi.fn();
    renderPicker(onPick);
    // רון לוי is only available 19:00–23:00 (out of this 07:00–15:00 window) — still
    // shown, tagged "מחוץ לזמינות", and pickable as a deliberate override.
    expect(screen.getByText('רון לוי')).toBeInTheDocument();
    expect(screen.getByText('מחוץ לזמינות')).toBeInTheDocument();
    expect(screen.getByText('בובי ביטון')).toBeInTheDocument();
    expect(screen.getByText('משה שמעון')).toBeInTheDocument();
    fireEvent.click(screen.getByText('רון לוי'));
    expect(onPick).toHaveBeenCalledWith('u3');
  });

  it('shows an empty message only when no unassigned guard remains', () => {
    render(
      <CellPicker
        row={ROW}
        cell={CELL}
        pool={[POOL[2]]}
        assignedIds={new Set(['u3'])} // the only guard is already in this shift
        attrLabel={attrLabel}
        onPick={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText('אין מאבטח זמין לחלון זה')).toBeInTheDocument();
  });

  it('calls onPick with the chosen guard id', () => {
    const onPick = vi.fn();
    renderPicker(onPick);
    fireEvent.click(screen.getByText('בובי ביטון'));
    expect(onPick).toHaveBeenCalledWith('u1');
  });

  it('closes on overlay click', () => {
    const onClose = vi.fn();
    renderPicker(vi.fn(), onClose);
    fireEvent.click(screen.getByText('מי זמין לחלון').closest('.cell-picker-overlay'));
    expect(onClose).toHaveBeenCalled();
  });
});
