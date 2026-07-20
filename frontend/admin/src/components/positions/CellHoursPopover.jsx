import { useEffect, useRef, useState } from 'react';
import messages from '../../utils/messages';

/**
 * CellHoursPopover — the per-cell start/end editor (step 05).
 *
 * Anchored inside the active cell's <td> (which the matrix makes
 * position:relative). Owns a local draft of the two <input type="time"> fields,
 * so the parent's WORKING state is touched only on confirm — same dirty/save
 * pipeline as a toggle (highlighted → "שמירה (N)" → bulk save, NO server call
 * from here).
 *
 * Keyboard: Enter = confirm, Escape = cancel. Pointer: a mousedown anywhere
 * outside the popover cancels it. Both fields are required (HH:MM, enforced
 * natively by type="time") [EDGE D1]. An overnight window (end <= start) is
 * VALID [EDGE D2] and shows a small "חוצה חצות" hint so the admin knows it's
 * intentional; it never blocks confirm.
 *
 * Clicks and keys are stopped at the root so they never bubble up to the cell's
 * toggle handler.
 *
 * Props:
 *   start, end — prefill values from the working cell's window.
 *   onConfirm  — ({ start, end }) => void.
 *   onCancel   — () => void.
 */
export default function CellHoursPopover({ start, end, onConfirm, onCancel }) {
  const m = messages.positions;
  const c = messages.common;
  const [draftStart, setDraftStart] = useState(start);
  const [draftEnd, setDraftEnd] = useState(end);
  const rootRef = useRef(null);

  const bothFilled = !!draftStart && !!draftEnd;
  const overnight = bothFilled && draftEnd <= draftStart;

  // Click-outside = cancel. Bound to mousedown so it fires before the click that
  // (e.g.) toggles another cell.
  useEffect(() => {
    const onPointerDown = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) onCancel();
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [onCancel]);

  const confirm = () => {
    if (!bothFilled) return; // [EDGE D1] both fields required
    onConfirm({ start: draftStart, end: draftEnd });
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      confirm();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onCancel();
    }
  };

  return (
    <div
      className="cell-hours-popover"
      ref={rootRef}
      role="dialog"
      aria-label={m.matrixHoursTitle}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
    >
      <label className="cell-hours-field">
        <span>{m.start}</span>
        <input
          type="time"
          aria-label={m.start}
          value={draftStart}
          onChange={(e) => setDraftStart(e.target.value)}
          onKeyDown={onKeyDown}
        />
      </label>
      <label className="cell-hours-field">
        <span>{m.end}</span>
        <input
          type="time"
          aria-label={m.end}
          value={draftEnd}
          onChange={(e) => setDraftEnd(e.target.value)}
          onKeyDown={onKeyDown}
        />
      </label>
      {overnight && <p className="cell-hours-hint">{m.matrixOvernightHint}</p>}
      <div className="cell-hours-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={!bothFilled}
          onClick={confirm}
        >
          {c.confirm}
        </button>
        <button type="button" className="btn btn-secondary" onClick={onCancel}>
          {c.cancel}
        </button>
      </div>
    </div>
  );
}
