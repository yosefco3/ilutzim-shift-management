import { useEffect } from 'react';
import { coverage } from '../../utils/intervals';
import messages, { ROLE_LABELS } from '../../utils/messages';

const DAY_NAMES = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת'];
const roleLabel = (key) => ROLE_LABELS[key] || key;

// Rank candidates: full coverage first, then partial, then unavailable; within a
// tier the most-free (remaining hours) first.
const COV_RANK = { full: 0, partial: 1, none: 2 };

function buildCandidates(row, cell, pool, assignedIds) {
  const required = row.required_attributes || [];
  return pool
    .filter((g) => !assignedIds.has(g.id))
    .map((g) => {
      const dayWindows = (g.availability || {})[String(cell.day_index)] || [];
      const cov = cell.window
        ? coverage(cell.window.start, cell.window.end, dayWindows)
        : { state: 'none', gaps: [] };
      // Position required attributes (lowercase keys) vs guard roles (UPPER enum).
      const held = new Set((g.roles || []).map((r) => r.toLowerCase()));
      const missing = required.filter((k) => !held.has(k.toLowerCase()));
      return { guard: g, cov, missing, remaining: g.remaining_hours ?? 0 };
    })
    // Everyone unassigned is listed — being out of availability is a soft warning,
    // not a block, so an unavailable guard can still be picked deliberately. They
    // sort last (COV_RANK: none = 2) and carry a "מחוץ לזמינות" label.
    .sort(
      (a, b) =>
        COV_RANK[a.cov.state] - COV_RANK[b.cov.state] || b.remaining - a.remaining,
    );
}

// Modal candidate picker for a cell (styled after the mockup's "מי זמין לחלון").
// Lists guards sorted by how well they cover the cell window, flags missing
// required attributes (soft — still assignable), and shows remaining hours.
export default function CellPicker({
  row,
  cell,
  pool,
  assignedIds,
  onPick,
  onClose,
  attrLabel = (k) => k,
  handoffGaps = [],
}) {
  const m = messages.board.cell;
  // The cell already holds one guard → we're completing the coverage with a second.
  const completing = handoffGaps.length > 0;

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const candidates = buildCandidates(row, cell, pool, assignedIds);
  const windowLabel = cell.window ? `${cell.window.start}–${cell.window.end}` : '';

  const covLabel = (state) =>
    state === 'full' ? m.coversAll : state === 'partial' ? m.coversPartial : m.notCovering;
  const covColor = (state) =>
    state === 'full'
      ? 'var(--on-success)'
      : state === 'partial'
        ? 'var(--on-warning)'
        : 'var(--danger)';

  return (
    <div className="cell-picker-overlay" onClick={onClose} role="presentation">
      <div
        className="cell-picker"
        role="dialog"
        aria-label={m.whoAvailable}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="cell-picker-head">
          <div className="cell-picker-eyebrow">{completing ? m.handoffRemaining : m.whoAvailable}</div>
          <div className="cell-picker-title">
            {row.name} · {DAY_NAMES[cell.day_index]}
          </div>
          {windowLabel && (
            <div className="cell-picker-sub">
              {windowLabel}
              {completing &&
                ` · ${m.remaining} ${handoffGaps.map((g) => `${g.start}–${g.end}`).join(', ')}`}
            </div>
          )}
        </div>

        {candidates.length === 0 ? (
          <div className="cell-picker-empty">{m.noneAvailable}</div>
        ) : (
          <div className="cell-picker-list">
            {candidates.map(({ guard, cov, missing, remaining }) => (
              <button
                type="button"
                key={guard.id}
                className="cell-picker-cand"
                onClick={() => onPick(guard.id)}
              >
                <span className="cell-picker-cand-name">{guard.full_name}</span>
                <span className="cell-picker-cand-cov" style={{ color: covColor(cov.state) }}>
                  {covLabel(cov.state)}
                </span>
                {missing.length > 0 && (
                  <span className="cell-picker-cand-miss">
                    {m.missing} {missing.map((k) => attrLabel(k)).join(', ')}
                  </span>
                )}
                <span className="cell-picker-cand-rem">
                  {remaining <= 0
                    ? messages.board.pool.usedUp
                    : `${remaining} ${messages.board.pool.hoursSuffix}`}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
