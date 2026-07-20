import { useEffect, useRef, useState } from 'react';
import messages from '../../utils/messages';

/**
 * EventCountPopover — quick editor for an event position's participant count
 * (event_required_count) straight from the matrix row header.
 *
 * Anchored inside the row-name <th> (which the matrix makes position:relative).
 * Owns a local draft of a single number field; an EMPTY field means "no fixed
 * count" (ללא הגבלה → null). Confirm hands the count (a positive integer or
 * null) up; the parent does the PATCH.
 *
 * Keyboard: Enter = confirm, Escape = cancel. Pointer: a mousedown anywhere
 * outside the popover cancels it. Clicks and keys are stopped at the root so
 * they never bubble to the row/cell handlers.
 *
 * Props:
 *   count      — current event_required_count (number | null) to prefill.
 *   onConfirm  — (count | null) => void.
 *   onCancel   — () => void.
 */
export default function EventCountPopover({ count, onConfirm, onCancel }) {
  const m = messages.positions;
  const c = messages.common;
  const [draft, setDraft] = useState(count != null ? String(count) : '');
  const rootRef = useRef(null);

  // Empty = unlimited (valid). A filled value must be an integer ≥ 1.
  const trimmed = draft.trim();
  const asNumber = Number(trimmed);
  const valid =
    trimmed === '' || (Number.isInteger(asNumber) && asNumber >= 1);

  useEffect(() => {
    const onPointerDown = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) onCancel();
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [onCancel]);

  const confirm = () => {
    if (!valid) return;
    onConfirm(trimmed === '' ? null : asNumber);
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
      className="cell-hours-popover event-count-popover"
      ref={rootRef}
      role="dialog"
      aria-label={m.matrixEventCountTitle}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
    >
      <label className="cell-hours-field">
        <span>{m.eventCountLabel}</span>
        <input
          type="number"
          min="1"
          step="1"
          autoFocus
          placeholder={m.eventCountUnlimited}
          aria-label={m.matrixEventCountTitle}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
        />
      </label>
      <p className="cell-hours-hint">{m.eventCountUnlimitedHint}</p>
      <div className="cell-hours-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={!valid}
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
