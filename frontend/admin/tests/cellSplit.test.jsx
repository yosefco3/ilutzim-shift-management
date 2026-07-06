import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import CellSplit from '../src/components/board/CellSplit';
import messages from '../src/utils/messages';

const m = messages.board;
const WIN = { start: '06:00', end: '16:00' }; // 10h, straddles the 07:00 anchor

function pair(splitEnd = '11:00') {
  return [
    { id: 'a1', user_id: 'u1', user_full_name: 'נתן', segment_start: '06:00', segment_end: splitEnd },
    { id: 'b1', user_id: 'u2', user_full_name: 'מאי', segment_start: splitEnd, segment_end: '16:00' },
  ];
}

describe('CellSplit (draggable divider)', () => {
  it('renders both guards with עד / מ- handoff labels', () => {
    const { getByText } = render(
      <CellSplit cellWindow={WIN} assignments={pair('11:00')} onCommit={vi.fn()} onUnassign={vi.fn()} m={m} />,
    );
    expect(getByText('נתן')).toBeInTheDocument();
    expect(getByText(/עד 11:00/)).toBeInTheDocument();
    expect(getByText('מ-11:00')).toBeInTheDocument();
  });

  it('commits a 30-min-rounded handoff inside the window on drag release', () => {
    const onCommit = vi.fn();
    const { container } = render(
      <CellSplit cellWindow={WIN} assignments={pair('11:00')} onCommit={onCommit} onUnassign={vi.fn()} m={m} />,
    );
    const split = container.querySelector('.board-cell-split');
    const handle = container.querySelector('.board-cell-split-handle');
    split.getBoundingClientRect = () => ({ top: 0, height: 100, left: 0, right: 50, bottom: 100, width: 50 });

    fireEvent.pointerDown(handle, { pointerId: 1 });
    fireEvent.pointerMove(handle, { clientY: 50 }); // 50% of 10h = 5h after 06:00 → 11:00
    fireEvent.pointerUp(handle, { pointerId: 1 });

    expect(onCommit).toHaveBeenCalled();
    const committed = onCommit.mock.calls.at(-1)[0];
    expect(committed).toBe('11:00');
    // Always a 30-min multiple, strictly inside the window.
    expect(toMinutes(committed) % 30).toBe(0);
  });

  it('moves the handoff by 30 minutes and commits once on key release (F-low)', () => {
    const onCommit = vi.fn();
    const { container } = render(
      <CellSplit cellWindow={WIN} assignments={pair('11:00')} onCommit={onCommit} onUnassign={vi.fn()} m={m} />,
    );
    const handle = container.querySelector('.board-cell-split-handle');
    // Hold: two ArrowDowns move the local handoff 11:00 → 11:30 → 12:00 with NO
    // network commit; the single keyup commits the final value exactly once.
    fireEvent.keyDown(handle, { key: 'ArrowDown' });
    fireEvent.keyDown(handle, { key: 'ArrowDown' });
    expect(onCommit).not.toHaveBeenCalled();
    fireEvent.keyUp(handle, { key: 'ArrowDown' });
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenLastCalledWith('12:00');
  });

  it('reverts without committing on pointercancel (F-low)', () => {
    const onCommit = vi.fn();
    const { container } = render(
      <CellSplit cellWindow={WIN} assignments={pair('11:00')} onCommit={onCommit} onUnassign={vi.fn()} m={m} />,
    );
    const split = container.querySelector('.board-cell-split');
    const handle = container.querySelector('.board-cell-split-handle');
    split.getBoundingClientRect = () => ({ top: 0, height: 100, left: 0, right: 50, bottom: 100, width: 50 });
    fireEvent.pointerDown(handle, { pointerId: 1 });
    fireEvent.pointerMove(handle, { clientY: 80 }); // drag toward the bottom
    fireEvent.pointerCancel(handle, { pointerId: 1 });
    expect(onCommit).not.toHaveBeenCalled(); // cancelled drag never commits
  });

  it('clamps the divider strictly inside the window', () => {
    const onCommit = vi.fn();
    const { container } = render(
      <CellSplit cellWindow={WIN} assignments={pair('11:00')} onCommit={onCommit} onUnassign={vi.fn()} m={m} />,
    );
    const split = container.querySelector('.board-cell-split');
    const handle = container.querySelector('.board-cell-split-handle');
    split.getBoundingClientRect = () => ({ top: 0, height: 100, left: 0, right: 50, bottom: 100, width: 50 });
    fireEvent.pointerDown(handle, { pointerId: 1 });
    fireEvent.pointerMove(handle, { clientY: 999 }); // way past the bottom
    fireEvent.pointerUp(handle, { pointerId: 1 });
    expect(onCommit).toHaveBeenLastCalledWith('15:30'); // end (16:00) − 30 min
  });

  it('removes a guard via its × button', () => {
    const onUnassign = vi.fn();
    const { getAllByLabelText } = render(
      <CellSplit cellWindow={WIN} assignments={pair('11:00')} onCommit={vi.fn()} onUnassign={onUnassign} m={m} />,
    );
    fireEvent.click(getAllByLabelText('הסר שיבוץ')[0]);
    expect(onUnassign).toHaveBeenCalledWith('a1');
  });
});

function toMinutes(hhmm) {
  const [h, mm] = hhmm.split(':').map(Number);
  return h * 60 + mm;
}
