import { useRef, useState, useEffect } from 'react';
import { toMin, toHHMM } from '../../utils/intervals';

// Handoff steps match the security-day grid (30-minute snaps).
const STEP = 30;

function winLenOf(w) {
  return ((toMin(w.end) - toMin(w.start) + 1440) % 1440) || 1440;
}
function offsetOf(w, hhmm) {
  return (toMin(hhmm) - toMin(w.start) + 1440) % 1440;
}
function timeAtOffset(w, offset) {
  return toHHMM((toMin(w.start) + offset) % 1440);
}

// A partially-covered cell: one guard covering the slice they're available for,
// with the uncovered remainder shown as amber gap zone(s). A draggable handle sits
// on each guard/gap boundary — dragging it extends or shrinks the guard's segment
// (past their availability, if the admin chooses). Mirrors CellSplit's divider.
// Reaching the window edge on both sides clears the segment (whole-window cover),
// which the parent detects and persists as segment → null.
export default function CellPartial({ cellWindow, assignment, onCommit, onUnassign, m }) {
  const winLen = winLenOf(cellWindow);
  const ref = useRef(null);
  const dragging = useRef(null); // 'start' | 'end' | null

  const rawStart = assignment.segment_start ? offsetOf(cellWindow, assignment.segment_start) : 0;
  const rawEndOff = assignment.segment_end ? offsetOf(cellWindow, assignment.segment_end) : winLen;
  const rawEnd = rawEndOff === 0 ? winLen : rawEndOff;

  const [live, setLive] = useState({ start: rawStart, end: rawEnd });
  // Mirror of live that is always current within the same tick (pointerup / keyup
  // read it to commit the final value), plus the last server-acked value that
  // pointercancel reverts to, and a dirty flag for keyboard commit-on-keyup.
  const liveRef = useRef({ start: rawStart, end: rawEnd });
  const committedRef = useRef({ start: rawStart, end: rawEnd });
  const keyDirty = useRef(false);
  const setLiveBoth = (next) => { liveRef.current = next; setLive(next); };

  // Re-sync when the server values change after a reload.
  useEffect(() => {
    const v = { start: rawStart, end: rawEnd };
    setLive(v);
    liveRef.current = v;
    committedRef.current = v;
  }, [rawStart, rawEnd]);

  const snap = (off) => Math.round(off / STEP) * STEP;

  const commit = (next) => {
    onCommit({
      start: timeAtOffset(cellWindow, next.start),
      end: timeAtOffset(cellWindow, next.end % 1440 === 0 ? winLen : next.end),
    });
  };

  const moveTo = (clientY) => {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect || !rect.height || !dragging.current) return;
    const frac = Math.max(0, Math.min(1, (clientY - rect.top) / rect.height));
    const off = frac * winLen;
    const prev = liveRef.current;
    const next =
      dragging.current === 'start'
        ? { ...prev, start: Math.max(0, Math.min(prev.end - STEP, snap(off))) }
        : { ...prev, end: Math.max(prev.start + STEP, Math.min(winLen, snap(off))) };
    setLiveBoth(next);
  };

  // Capture the pointer on the container (always mounted), not the handle. When a
  // drag reaches the window edge the guard fills the cell and the handle unmounts;
  // if capture lived on the handle, pointerup would never fire and the new segment
  // would silently never commit (regression: extend-to-fill wasn't saved).
  const onPointerDown = (edge) => (e) => {
    dragging.current = edge;
    ref.current?.setPointerCapture?.(e.pointerId);
    e.stopPropagation();
    e.preventDefault();
  };
  const onPointerMove = (e) => {
    if (dragging.current) moveTo(e.clientY);
  };
  const onPointerUp = (e) => {
    if (!dragging.current) return;
    dragging.current = null;
    ref.current?.releasePointerCapture?.(e.pointerId);
    committedRef.current = liveRef.current;
    commit(liveRef.current);
  };
  // Browser/OS cancelled the drag — reset without committing, snap back to the
  // last saved segment (F-low).
  const onPointerCancel = (e) => {
    if (!dragging.current) return;
    dragging.current = null;
    ref.current?.releasePointerCapture?.(e.pointerId);
    setLiveBoth(committedRef.current);
  };

  // Arrow keys update the local segment only; the commit fires once on keyup, so
  // holding a key doesn't unleash a storm of PATCHes (F-low).
  const onKeyDown = (edge) => (e) => {
    let delta = 0;
    if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') delta = -STEP;
    else if (e.key === 'ArrowDown' || e.key === 'ArrowRight') delta = STEP;
    else return;
    e.preventDefault();
    const prev = liveRef.current;
    const next =
      edge === 'start'
        ? { ...prev, start: Math.max(0, Math.min(prev.end - STEP, snap(prev.start + delta))) }
        : { ...prev, end: Math.max(prev.start + STEP, Math.min(winLen, snap(prev.end + delta))) };
    keyDirty.current = true;
    setLiveBoth(next);
  };
  const onKeyUp = () => {
    if (!keyDirty.current) return;
    keyDirty.current = false;
    committedRef.current = liveRef.current;
    commit(liveRef.current);
  };

  const topPct = (live.start / winLen) * 100;
  const guardPct = ((live.end - live.start) / winLen) * 100;
  const botPct = ((winLen - live.end) / winLen) * 100;
  const startTime = timeAtOffset(cellWindow, live.start);
  const endTime = timeAtOffset(cellWindow, live.end % 1440 === 0 ? winLen : live.end);

  const handle = (edge, valueText) => (
    <div
      className="board-cell-split-handle"
      role="separator"
      aria-orientation="horizontal"
      aria-valuetext={valueText}
      tabIndex={0}
      title={valueText}
      onPointerDown={onPointerDown(edge)}
      onKeyDown={onKeyDown(edge)}
      onKeyUp={onKeyUp}
      onClick={(e) => e.stopPropagation()}
    />
  );

  const gapZone = (from, to, basis) => (
    <div
      className="board-cell-split-zone board-cell-split-gap"
      style={{ flexBasis: `${basis}%` }}
    >
      <span className="board-cell-gap">{m.cell.remaining} {from}–{to}</span>
    </div>
  );

  return (
    <div
      className="board-cell-split"
      ref={ref}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
    >
      {live.start > 0 && (
        <>
          {gapZone(cellWindow.start, startTime, topPct)}
          {handle('start', startTime)}
        </>
      )}

      <div className="board-cell-split-zone" style={{ flexBasis: `${guardPct}%` }}>
        <span className="board-cell-guard-name">{assignment.user_full_name}</span>
        <span className="board-cell-guard-seg">{startTime}–{endTime}</span>
        <button
          type="button"
          className="board-cell-guard-x"
          aria-label={m.cell.remove}
          onClick={(e) => {
            e.stopPropagation();
            onUnassign(assignment.id);
          }}
        >
          ×
        </button>
      </div>

      {live.end < winLen && (
        <>
          {handle('end', endTime)}
          {gapZone(endTime, cellWindow.end, botPct)}
        </>
      )}
    </div>
  );
}
