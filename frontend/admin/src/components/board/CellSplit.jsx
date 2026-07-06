import { useRef, useState, useEffect } from 'react';
import { toMin, toHHMM } from '../../utils/intervals';

// The handoff point is locked to 30-minute steps (matches the security-day grid).
const STEP = 30;

// Window length in minutes (a 0-length result means the whole 24h day).
function winLenOf(w) {
  return ((toMin(w.end) - toMin(w.start) + 1440) % 1440) || 1440;
}
// Minutes from the window start for a 'HH:MM' time.
function offsetOf(w, hhmm) {
  return (toMin(hhmm) - toMin(w.start) + 1440) % 1440;
}
// The 'HH:MM' time at a given offset from the window start.
function timeAtOffset(w, offset) {
  return toHHMM((toMin(w.start) + offset) % 1440);
}

// A split cell: two guards tiling one window in time. Guard A (top) covers from
// the window start to the handoff; guard B (bottom) from the handoff to the end.
// The admin drags the divider (or uses ↑/↓) to move the handoff; it snaps to 30
// minutes, stays strictly inside the window, and commits on release.
export default function CellSplit({ cellWindow, assignments, onCommit, onUnassign, m }) {
  const [a, b] = assignments;
  const winLen = winLenOf(cellWindow);
  const ref = useRef(null);
  const dragging = useRef(false);

  const clampOffset = (off) => {
    const snapped = Math.round(off / STEP) * STEP;
    return Math.max(STEP, Math.min(winLen - STEP, snapped));
  };

  const initialSplit =
    a.segment_end || timeAtOffset(cellWindow, clampOffset(winLen / 2));
  const [liveSplit, setLiveSplit] = useState(initialSplit);
  // Mirror of liveSplit that is always current within the same tick — pointerup /
  // keyup read it to commit the final value without a stale-closure race.
  const liveRef = useRef(initialSplit);
  const setLive = (t) => { liveRef.current = t; setLiveSplit(t); };
  // Last value the server acknowledged — pointercancel reverts to it (no commit).
  const committedRef = useRef(initialSplit);
  // Pending keyboard commit (arrow held down) → commit once on keyup.
  const keyDirty = useRef(false);

  // Re-sync if the server values change after a reload.
  useEffect(() => {
    if (a.segment_end) {
      setLiveSplit(a.segment_end);
      liveRef.current = a.segment_end;
      committedRef.current = a.segment_end;
    }
  }, [a.segment_end]);

  const splitOff = clampOffset(offsetOf(cellWindow, liveSplit));
  const splitTime = timeAtOffset(cellWindow, splitOff);
  const topPct = (splitOff / winLen) * 100;

  const commitLive = () =>
    onCommit(timeAtOffset(cellWindow, clampOffset(offsetOf(cellWindow, liveRef.current))));

  const moveTo = (clientY) => {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect || !rect.height) return;
    const frac = Math.max(0, Math.min(1, (clientY - rect.top) / rect.height));
    setLive(timeAtOffset(cellWindow, clampOffset(frac * winLen)));
  };

  const onPointerDown = (e) => {
    dragging.current = true;
    e.target.setPointerCapture?.(e.pointerId);
    e.preventDefault();
  };
  const onPointerMove = (e) => {
    if (dragging.current) moveTo(e.clientY);
  };
  const onPointerUp = (e) => {
    if (!dragging.current) return;
    dragging.current = false;
    e.target.releasePointerCapture?.(e.pointerId);
    committedRef.current = liveRef.current;
    commitLive();
  };
  // Browser/OS cancelled the drag (gesture, focus loss) — reset without committing
  // and snap back to the last saved value (F-low).
  const onPointerCancel = (e) => {
    if (!dragging.current) return;
    dragging.current = false;
    e.target.releasePointerCapture?.(e.pointerId);
    setLive(committedRef.current);
  };

  // Arrow keys update the local split only; the network commit fires once on
  // keyup, so holding a key doesn't unleash a storm of PATCHes (F-low).
  const onKeyDown = (e) => {
    let delta = 0;
    if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') delta = -STEP;
    else if (e.key === 'ArrowDown' || e.key === 'ArrowRight') delta = STEP;
    else return;
    e.preventDefault();
    keyDirty.current = true;
    setLive(timeAtOffset(cellWindow, clampOffset(offsetOf(cellWindow, liveRef.current) + delta)));
  };
  const onKeyUp = () => {
    if (!keyDirty.current) return;
    keyDirty.current = false;
    committedRef.current = liveRef.current;
    commitLive();
  };

  const zone = (guard, label, basis) => (
    <div className="board-cell-split-zone" style={{ flexBasis: `${basis}%` }}>
      <span className="board-cell-guard-name">{guard.user_full_name}</span>
      <span className="board-cell-guard-seg">{label}</span>
      <button
        type="button"
        className="board-cell-guard-x"
        aria-label={m.cell.remove}
        onClick={(e) => {
          e.stopPropagation();
          onUnassign(guard.id);
        }}
      >
        ×
      </button>
    </div>
  );

  return (
    <div className="board-cell-split" ref={ref}>
      {zone(a, `${m.cell.until} ${splitTime}`, topPct)}
      <div
        className="board-cell-split-handle"
        role="separator"
        aria-orientation="horizontal"
        aria-valuetext={splitTime}
        tabIndex={0}
        title={splitTime}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerCancel}
        onKeyDown={onKeyDown}
        onKeyUp={onKeyUp}
        onClick={(e) => e.stopPropagation()}
      />
      {zone(b, `${m.cell.from}${splitTime}`, 100 - topPct)}
    </div>
  );
}
