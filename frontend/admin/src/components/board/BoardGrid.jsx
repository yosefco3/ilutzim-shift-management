import { Fragment, useEffect, useMemo, useState } from 'react';
import useHoverScroll from '../../hooks/useHoverScroll';
import { DAY_NAMES_SHORT as DAY_NAMES } from '../../utils/guardMessages.js';
import { coverage, segmentsCoverage } from '../../utils/intervals';
import { WARNING_SEVERITY, warningText } from '../../utils/warnings';
import messages from '../../utils/messages';
import CellPicker from './CellPicker';
import CellSplit from './CellSplit';
import CellPartial from './CellPartial';

const WARN_ICON = { hard: '🔴', soft: '🟧' };

const DAY_LETTERS = ['א', 'ב', 'ג', 'ד', 'ה', 'ו', 'ש'];

function windowText(w) {
  return w ? `${w.start}–${w.end}` : '';
}

const cellKey = (positionId, dayIndex) => `${positionId}:${dayIndex}`;

// The explicit time segment of each assignment in a cell — or the whole window
// when a guard has no segment (covers it all). Feeds segmentsCoverage().
function segmentsOf(assignments, window) {
  if (!window) return [];
  return assignments.map((a) =>
    a.segment_start && a.segment_end
      ? { start: a.segment_start, end: a.segment_end }
      : { start: window.start, end: window.end },
  );
}

// Compact active-days label for a non-daily position (e.g. "א–ה", "ו–ש",
// "א–ה, ש"). Empty when the position is active on all 7 days.
function activeDaysLabel(cells) {
  const active = cells.filter((c) => c.active).map((c) => c.day_index);
  if (active.length === 0 || active.length === 7) return '';
  const ranges = [];
  let start = active[0];
  let prev = active[0];
  for (let i = 1; i < active.length; i += 1) {
    if (active[i] === prev + 1) {
      prev = active[i];
      continue;
    }
    ranges.push([start, prev]);
    start = active[i];
    prev = active[i];
  }
  ranges.push([start, prev]);
  return ranges
    .map(([a, b]) => (a === b ? DAY_LETTERS[a] : `${DAY_LETTERS[a]}–${DAY_LETTERS[b]}`))
    .join(', ');
}

// Does the selected guard hold every attribute this position requires?
// Required keys are lower-case vocabulary; guard roles are UPPER enum values.
function guardMeetsAttributes(row, guard) {
  const required = row.required_attributes || [];
  if (!required.length) return true;
  const held = new Set((guard.roles || []).map((r) => r.toLowerCase()));
  return required.every((k) => held.has(String(k).toLowerCase()));
}

// Coverage of the cell window by the selected guard's availability that day.
// Returns null when no guard is selected or the cell has no window. A guard who
// lacks the position's required attribute (e.g. not אחמ"ש) can't fill it, so the
// cell stays uncoloured rather than implying availability.
function cellCoverage(row, cell, selectedGuard) {
  if (!selectedGuard || !cell.window) return null;
  if (!guardMeetsAttributes(row, selectedGuard)) return null;
  const dayWindows = (selectedGuard.availability || {})[String(cell.day_index)] || [];
  return coverage(cell.window.start, cell.window.end, dayWindows);
}

// One active cell. Three interaction modes, in order:
//  1. a guard is selected in the pool → the cell is coloured by their coverage
//     and clicking an empty cell assigns them (the primary task-06 flow);
//  2. no guard selected but `onAssign` provided → the hover ＋ in-cell picker (05);
//  3. no handlers → read-only (04).
function BoardCell({
  row,
  cell,
  assignments,
  cellWarnings = [],
  attrLabel,
  selectedGuard,
  inShiftAlready = false,
  onAssign,
  onUnassign,
  onOpenPicker,
  onSplitChange,
  onPartialChange,
  flashKey = null,
  flashNonce = 0,
  m,
}) {
  const interactive = typeof onAssign === 'function';
  const [dragOver, setDragOver] = useState(false);

  // Brief highlight when the summary-bar "focus next" nav targets this cell. Driven
  // by nonce (not just key) so clicking a chip re-flashes the same cell each time.
  const myKey = cellKey(row.position_id, cell.day_index);
  const [flashing, setFlashing] = useState(false);
  useEffect(() => {
    if (flashKey !== myKey) return undefined;
    setFlashing(true);
    const t = setTimeout(() => setFlashing(false), 1400);
    return () => clearTimeout(t);
  }, [flashNonce, flashKey, myKey]);

  // An event (non-splitting) position: guards share the whole window — no
  // time-tiling, no coverage colour. An event may carry a FIXED participant count
  // (e.g. מועצה = 4): the cell then fills into that many slots and shows the
  // missing ones. Without a count (רענון) it stays unlimited.
  const isEvent = !!row.is_event;
  const requiredCount = isEvent && row.event_required_count ? row.event_required_count : null;

  // Cap on how many guards fill the cell: fixed-count event → its count; normal
  // → two (time-tiling); unlimited event → none. A count short of full renders
  // "חסר מאבטח" slots.
  const full = isEvent
    ? requiredCount != null && assignments.length >= requiredCount
    : assignments.length >= 2;
  const understaffed = requiredCount != null && assignments.length < requiredCount;
  const missingSlots = understaffed ? requiredCount - assignments.length : 0;
  const assignedIds = new Set(assignments.map((a) => a.user_id));

  const cov = cellCoverage(row, cell, selectedGuard);
  // Coverage by the segments actually assigned (vs `cov`, the selected guard's
  // availability preview on an empty cell). Drives the colour of an occupied cell.
  // Events have no coverage notion, so their cells are never washed by coverage.
  const segCov =
    !isEvent && assignments.length && cell.window
      ? segmentsCoverage(cell.window.start, cell.window.end, segmentsOf(assignments, cell.window))
      : null;
  // A single guard covering only part of the window → render the draggable
  // guard-vs-gap divider (CellPartial) instead of a plain name + "נותר" label.
  const lonePartial =
    interactive && !isEvent && !!cell.window && assignments.length === 1 && segCov?.state === 'partial';
  // Any guard placed outside their declared availability — fully (out_of_availability)
  // or partly (partial_coverage) — wears a distinct "outside availability" hatch so
  // the deliberate override stands out from a clean cover, whatever the window
  // coverage looks like.
  const outsideAvailability =
    !isEvent &&
    cellWarnings.some((w) => w.type === 'partial_coverage' || w.type === 'out_of_availability');
  // A lone guard stretched to cover the *whole* window despite being only partly
  // available for it: the cell is fully covered (a deliberate override), so the
  // soft "partial coverage" note is no longer the story. We suppress that note
  // (its detail lives on in the cell tooltip); the hatch above is the marker.
  const expandedCover =
    outsideAvailability &&
    assignments.length === 1 &&
    segCov?.state === 'full' &&
    cellWarnings.some((w) => w.type === 'partial_coverage');
  const selecting = !!selectedGuard && interactive;
  // The selected guard is already used in this shift today, in another cell. Their
  // coverage colour disappears here, but placement stays allowed as a deliberate
  // override (075) — it just raises a soft `already_in_shift` warning afterwards.
  const takenInShift = selecting && inShiftAlready && !assignedIds.has(selectedGuard.id);
  // A selected guard can be placed in any non-full cell they don't already fill.
  // Soft rules — out of availability, missing a required attribute — never block
  // the placement (they only raise a warning afterwards), matching the drag-drop
  // path below. The manager places whom they choose; the board flags the override.
  const canPlaceSelected =
    selecting &&
    !full &&
    !assignedIds.has(selectedGuard.id);
  // The guard doesn't actually cover this window — no availability overlap
  // (cov.state === 'none') or they lack a required attribute (cellCoverage → null),
  // or they're already used in this shift. Placement stays allowed as a deliberate
  // override, but wears the warning styling so it stands out rather than the blue
  // "good fit" wash. Events carry no coverage notion, so any placement there is fine.
  const placeIsOverride =
    !isEvent && (takenInShift || !cov || cov.state === 'none');
  // When no guard is selected, clicking an active cell that isn't full opens the
  // modal picker (to place a first guard, or to complete the coverage with a second).
  const canOpenPicker = interactive && !selecting && !full;
  // A cell that isn't full is a drop target for a guard dragged from the pool (08).
  // Soft rules don't block the drop — the server only rejects the hard cap (409).
  const canDrop = interactive && !full;

  // Soft warnings on this cell's existing assignments. The tooltip always spells
  // out every warning; the visible badges hide the partial-coverage note once the
  // cell reads as a deliberate expanded cover (its detail stays in the tooltip).
  const warnTitle = cellWarnings.map((w) => warningText(w, m.warn, attrLabel)).join('\n');
  const badges = expandedCover
    ? cellWarnings.filter((w) => w.type !== 'partial_coverage')
    : cellWarnings;
  const hasHardWarn = badges.some((w) => WARNING_SEVERITY[w.type] === 'hard');

  // Occupied cells are washed by their *segment* coverage; empty cells preview
  // the selected guard's availability (suppressed when already used this shift).
  // Events carry no coverage colour; a normal occupied cell is washed by its
  // segment coverage, an empty one by the selected guard's availability preview.
  const covClass = isEvent
    ? ''
    : outsideAvailability
      ? ' cov-expanded'
      : segCov
        ? ` cov-${segCov.state}`
        : cov && !takenInShift
          ? ` cov-${cov.state}`
          : '';
  const warnClass = badges.length ? (hasHardWarn ? ' has-warn-hard' : ' has-warn-soft') : '';
  // The blue availability preview is only painted on empty cells. An occupied cell
  // keeps its real coverage colour (green when fully covered, yellow when partial)
  // so already-staffed slots aren't washed over — placement stays allowed via click.
  const placeClass =
    canPlaceSelected && !assignments.length
      ? placeIsOverride
        ? ' placeable-warn'
        : ' placeable'
      : '';
  const onClick = canPlaceSelected
    ? () => onAssign(row.position_id, cell.day_index, selectedGuard.id)
    : canOpenPicker
      ? () => onOpenPicker(row, cell)
      : undefined;

  return (
    <td
      data-cell-id={myKey}
      className={`board-cell active${isEvent ? ' board-cell-event' : ''}${understaffed ? ' board-cell-understaffed' : ''}${covClass}${warnClass}${placeClass}${canOpenPicker ? ' clickable' : ''}${dragOver ? ' drag-over' : ''}${flashing ? ' board-cell-flash' : ''}`}
      onClick={onClick}
      onDragOver={
        canDrop
          ? (e) => {
              e.preventDefault();
              e.dataTransfer.dropEffect = 'copy';
              setDragOver(true);
            }
          : undefined
      }
      onDragLeave={canDrop ? () => setDragOver(false) : undefined}
      onDrop={
        canDrop
          ? (e) => {
              e.preventDefault();
              setDragOver(false);
              const id = e.dataTransfer.getData('text/plain');
              if (id) onAssign(row.position_id, cell.day_index, id);
            }
          : undefined
      }
      title={
        warnTitle ||
        (takenInShift
          ? m.cell.inShift
          : selecting && cov && cov.state === 'none'
            ? m.cell.unavailablePlace
            : undefined)
      }
    >
      {cell.is_override && (
        <span className="board-cell-override">🕐 {windowText(cell.window)}</span>
      )}

      {assignments.length === 2 && interactive && cell.window && !isEvent ? (
        <CellSplit
          cellWindow={cell.window}
          assignments={assignments}
          onCommit={(split) => onSplitChange(assignments, split)}
          onUnassign={onUnassign}
          m={m}
        />
      ) : lonePartial ? (
        <CellPartial
          cellWindow={cell.window}
          assignment={assignments[0]}
          onCommit={(seg) => onPartialChange(assignments[0], seg)}
          onUnassign={onUnassign}
          m={m}
        />
      ) : (
        assignments.map((a, idx) => {
        // Compact tiling label: two guards → "עד {handoff}" / "מ-{handoff}";
        // a single guard with an explicit partial segment → its window.
        let segLabel = '';
        if (assignments.length >= 2) {
          if (idx === 0 && a.segment_end) segLabel = `${m.cell.until} ${a.segment_end}`;
          else if (idx === 1 && a.segment_start) segLabel = `${m.cell.from}${a.segment_start}`;
        } else if (a.segment_start && a.segment_end) {
          segLabel = `${a.segment_start}–${a.segment_end}`;
        }
        return (
        <span key={a.id} className="board-cell-guard" title={(a.user_roles || []).join(' · ')}>
          <span className="board-cell-guard-name">{a.user_full_name}</span>
          {segLabel && <span className="board-cell-guard-seg">{segLabel}</span>}
          {interactive && (
            <button
              type="button"
              className="board-cell-guard-x"
              aria-label={m.cell.remove}
              onClick={(e) => {
                e.stopPropagation();
                onUnassign(a.id);
              }}
            >
              ×
            </button>
          )}
        </span>
        );
      })
      )}

      {/* Fixed-count event short of its required participants → one amber
          "חסר מאבטח" placeholder per missing slot, matching the schedule Excel. */}
      {missingSlots > 0 &&
        Array.from({ length: missingSlots }).map((_, i) => (
          <span key={`missing-${i}`} className="board-cell-slot-missing">
            {m.cell.missingSlot}
          </span>
        ))}

      {/* Soft-warning badges for the placed guard(s) — informative, not blocking. */}
      {badges.length > 0 && (
        <span className="board-cell-warns">
          {badges.map((w, idx) => (
            <span
              key={`${w.type}-${idx}`}
              className={`board-warn board-warn-${WARNING_SEVERITY[w.type]}`}
              title={warningText(w, m.warn, attrLabel)}
            >
              {WARN_ICON[WARNING_SEVERITY[w.type]]} {warningText(w, m.warn, attrLabel)}
            </span>
          ))}
        </span>
      )}

      {/* "נותר" for an occupied cell whose assigned segments don't yet cover the
          whole window (one half of a not-yet-tiled split, or a read-only lone
          partial — the interactive lone case renders its own gap zone via CellPartial). */}
      {!isEvent && !lonePartial && segCov && segCov.state === 'partial' && segCov.gaps.length > 0 && (
        <span className="board-cell-gap">
          {m.cell.remaining} {segCov.gaps.map((g) => `${g.start}–${g.end}`).join(', ')}
        </span>
      )}

      {/* Partial-coverage gap label for the selected guard on an empty cell
          (hidden once the colour is suppressed because the guard is used this shift). */}
      {!isEvent && selecting && !takenInShift && !assignments.length && cov && cov.state === 'partial' && cov.gaps.length > 0 && (
        <span className="board-cell-gap">
          {m.cell.remaining} {cov.gaps.map((g) => `${g.start}–${g.end}`).join(', ')}
        </span>
      )}

      {/* ＋ hint on empty cells (opens the modal picker via the cell click). */}
      {canOpenPicker && (
        <button
          type="button"
          className="board-cell-add"
          aria-label={m.cell.add}
          onClick={(e) => {
            e.stopPropagation();
            onOpenPicker(row, cell);
          }}
        >
          ＋
        </button>
      )}
    </td>
  );
}

// Move `id` within `ids` to sit where `targetId` is — the standard array-move
// used on drop: dragging down lands *after* the target, dragging up lands
// *before* it, so the dragged row ends where the cursor released.
function moveWithinOrder(ids, id, targetId) {
  const from = ids.indexOf(id);
  const to = ids.indexOf(targetId);
  if (from === -1 || to === -1 || from === to) return ids;
  const next = ids.filter((x) => x !== id);
  const insertAt = from < to ? next.indexOf(targetId) + 1 : next.indexOf(targetId);
  next.splice(insertAt, 0, id);
  return next;
}

// Positions × days grid. Rows arrive already ordered by the backend (band →
// display_order); this component renders the band group headers and the cells.
// When `pool`/`onAssign`/`onUnassign` are supplied, active cells become
// interactive (pick a guard / remove a guard); otherwise the grid is read-only.
// When `onReorderPositions` is supplied, position rows are draggable to reorder
// them **within their band** (band is derived from hours, so cross-band drops
// are rejected).
export default function BoardGrid({
  board,
  attrLabel = (k) => k,
  pool = [],
  assignmentsByCell = {},
  dayLabels = {},
  selectedGuard = null,
  onAssign,
  onUnassign,
  onSplitChange,
  onPartialChange,
  onReorderPositions,
  onEditPosition,
  onDeletePosition,
  warnings = { byCell: {}, byGuard: {} },
  flashCell = null,
}) {
  const m = messages.board;
  const { days, rows } = board;
  const colCount = days.length + 1;
  const [pickerCell, setPickerCell] = useState(null);
  // Arrow keys scroll the grid while the pointer is over it (04·nav).
  const { ref: scrollRef, handlers: scrollHandlers } = useHoverScroll();

  // Row drag-and-drop reorder state: the position being dragged and the row it
  // is currently hovering (for the drop indicator).
  const canReorder = typeof onReorderPositions === 'function';
  const [dragId, setDragId] = useState(null);
  const [dragOverId, setDragOverId] = useState(null);
  const bandByPosition = useMemo(
    () => new Map(rows.map((r) => [r.position_id, r.band])),
    [rows],
  );
  // A drop is allowed only onto a different row in the SAME band.
  const canDropOnRow = (targetId) =>
    canReorder &&
    dragId &&
    dragId !== targetId &&
    bandByPosition.get(dragId) === bandByPosition.get(targetId);

  const handleRowDrop = (targetId) => {
    if (!canDropOnRow(targetId)) return;
    const nextOrder = moveWithinOrder(
      rows.map((r) => r.position_id),
      dragId,
      targetId,
    );
    setDragId(null);
    setDragOverId(null);
    onReorderPositions(nextOrder);
  };

  // Shifts (band+day) the selected guard already occupies. A guard is never
  // placed twice in one shift on one day (075), so once they're used in a shift
  // their coverage colour is suppressed across the rest of that shift's cells —
  // they stay placeable elsewhere (other shift same day / same shift other day).
  const occupiedShifts = useMemo(() => {
    const set = new Set();
    if (!selectedGuard) return set;
    const bandByPos = new Map(rows.map((r) => [r.position_id, r.band]));
    for (const [key, list] of Object.entries(assignmentsByCell)) {
      if (!list.some((a) => a.user_id === selectedGuard.id)) continue;
      const [positionId, dayIndex] = key.split(':');
      const band = bandByPos.get(positionId);
      if (band) set.add(`${band}:${dayIndex}`);
    }
    return set;
  }, [rows, assignmentsByCell, selectedGuard]);

  // Guards already used somewhere in the clicked cell's shift (band+day). A guard
  // is never placed twice in one shift (075), so the picker must exclude everyone
  // already in that shift — not just whoever's in this exact cell — while keeping
  // them available for other shifts on the same day.
  const pickerAssignedIds = useMemo(() => {
    const ids = new Set();
    if (!pickerCell) return ids;
    const { band } = pickerCell.row;
    const dayIndex = String(pickerCell.cell.day_index);
    const bandByPos = new Map(rows.map((r) => [r.position_id, r.band]));
    for (const [key, list] of Object.entries(assignmentsByCell)) {
      const [positionId, di] = key.split(':');
      if (di !== dayIndex || bandByPos.get(positionId) !== band) continue;
      for (const a of list) ids.add(a.user_id);
    }
    return ids;
  }, [pickerCell, rows, assignmentsByCell]);

  // When the picker opens on a cell that already has one guard, the remaining
  // (uncovered) window — so the picker can hint what the second guard completes.
  const pickerHandoffGaps = useMemo(() => {
    if (!pickerCell) return [];
    const existing =
      assignmentsByCell[cellKey(pickerCell.row.position_id, pickerCell.cell.day_index)] || [];
    const win = pickerCell.cell.window;
    if (!existing.length || !win) return [];
    return segmentsCoverage(win.start, win.end, segmentsOf(existing, win)).gaps;
  }, [pickerCell, assignmentsByCell]);

  // Merge per-cell warnings with the per-guard policy warnings, attached to each
  // cell they involve, so a cell shows everything relevant to it.
  const warnByCell = useMemo(() => {
    const map = {};
    for (const [key, list] of Object.entries(warnings.byCell || {})) map[key] = [...list];
    for (const list of Object.values(warnings.byGuard || {})) {
      for (const w of list) {
        for (const key of w.cells || []) (map[key] ||= []).push(w);
      }
    }
    return map;
  }, [warnings]);

  const handlePick = (userId) => {
    if (pickerCell && userId) {
      onAssign(pickerCell.row.position_id, pickerCell.cell.day_index, userId);
    }
    setPickerCell(null);
  };

  return (
    <div className="board-grid-wrap" ref={scrollRef} {...scrollHandlers}>
      <table className="board-grid">
        <thead>
          <tr>
            <th className="board-corner">{m.position}</th>
            {days.map((d) => (
              <th key={d.index} className="board-day-head">
                <span className="board-day-name">
                  {DAY_NAMES[d.index]}
                  {/* Step 07: the assigned profile's per-day label (e.g. "ט׳ באב"),
                      purely presentational here — no editing on the board. */}
                  {dayLabels[String(d.index)] ? (
                    <span className="board-day-label">{dayLabels[String(d.index)]}</span>
                  ) : null}
                </span>
                <span className="board-day-date">{d.date.slice(5)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const prev = rows[i - 1];
            const bandChanged = !prev || prev.band !== row.band;
            const daysLabel = activeDaysLabel(row.cells);
            const isDragging = dragId === row.position_id;
            const isDropTarget = dragOverId === row.position_id && canDropOnRow(row.position_id);
            return (
              <Fragment key={row.position_id}>
                {bandChanged && (
                  <tr className="board-band-head">
                    <td colSpan={colCount}>
                      {m.bands[row.band]}
                      <span className="board-band-count">
                        · {rows.filter((r) => r.band === row.band).length} {m.positionsCount}
                      </span>
                    </td>
                  </tr>
                )}
                <tr
                  className={`board-row${isDragging ? ' pos-dragging' : ''}${isDropTarget ? ' pos-drop-target' : ''}`}
                >
                  <th
                    className={`board-pos-head${canReorder ? ' pos-draggable' : ''}${typeof onEditPosition === 'function' || typeof onDeletePosition === 'function' ? ' pos-editable' : ''}`}
                    scope="row"
                    draggable={canReorder || undefined}
                    onDragStart={
                      canReorder
                        ? (e) => {
                            setDragId(row.position_id);
                            e.dataTransfer.effectAllowed = 'move';
                            // Custom type only — never a cell-usable text/plain id,
                            // so a stray drop on a cell no-ops (BoardCell guards it).
                            e.dataTransfer.setData('application/x-board-position', row.position_id);
                          }
                        : undefined
                    }
                    onDragOver={
                      canReorder
                        ? (e) => {
                            if (!canDropOnRow(row.position_id)) return;
                            e.preventDefault();
                            e.dataTransfer.dropEffect = 'move';
                            setDragOverId(row.position_id);
                          }
                        : undefined
                    }
                    onDragLeave={
                      canReorder
                        ? () => setDragOverId((cur) => (cur === row.position_id ? null : cur))
                        : undefined
                    }
                    onDrop={
                      canReorder
                        ? (e) => {
                            e.preventDefault();
                            handleRowDrop(row.position_id);
                          }
                        : undefined
                    }
                    onDragEnd={
                      canReorder
                        ? () => {
                            setDragId(null);
                            setDragOverId(null);
                          }
                        : undefined
                    }
                  >
                    {canReorder && (
                      <span className="board-pos-grip" aria-hidden="true" title={m.reorderHint}>
                        ⠿
                      </span>
                    )}
                    {typeof onEditPosition === 'function' && (
                      <button
                        type="button"
                        className="board-pos-edit"
                        aria-label={m.editPosition}
                        title={m.editPosition}
                        draggable={false}
                        onClick={(e) => {
                          e.stopPropagation();
                          onEditPosition(row.position_id);
                        }}
                      >
                        ✏️
                      </button>
                    )}
                    {typeof onDeletePosition === 'function' && (
                      <button
                        type="button"
                        className="board-pos-delete"
                        aria-label={m.deletePosition}
                        title={m.deletePosition}
                        draggable={false}
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeletePosition(row.position_id);
                        }}
                      >
                        🗑️
                      </button>
                    )}
                    <span className="board-pos-name">{row.name}</span>
                    {row.is_adhoc && (
                      <span className="board-pos-adhoc" title={m.adhocTitle}>
                        {m.adhocTag}
                      </span>
                    )}
                    {daysLabel && <span className="board-pos-days">{daysLabel}</span>}
                    {row.canonical_window && (
                      <span className="board-pos-hours">
                        {windowText(row.canonical_window)}
                      </span>
                    )}
                    {row.required_attributes.length > 0 && (
                      <span className="board-pos-attrs">
                        {row.required_attributes.map((key) => (
                          <span key={key} className="board-attr-chip">
                            {attrLabel(key)}
                          </span>
                        ))}
                      </span>
                    )}
                  </th>
                  {row.cells.map((cell) =>
                    cell.active ? (
                      <BoardCell
                        key={cell.day_index}
                        row={row}
                        cell={cell}
                        assignments={assignmentsByCell[cellKey(row.position_id, cell.day_index)] || []}
                        cellWarnings={warnByCell[cellKey(row.position_id, cell.day_index)] || []}
                        attrLabel={attrLabel}
                        selectedGuard={selectedGuard}
                        inShiftAlready={occupiedShifts.has(`${row.band}:${cell.day_index}`)}
                        onAssign={onAssign}
                        onUnassign={onUnassign}
                        onSplitChange={onSplitChange}
                        onPartialChange={onPartialChange}
                        onOpenPicker={(r, c) => setPickerCell({ row: r, cell: c })}
                        flashKey={flashCell?.key ?? null}
                        flashNonce={flashCell?.nonce ?? 0}
                        m={m}
                      />
                    ) : (
                      <td
                        key={cell.day_index}
                        className="board-cell blocked"
                        aria-label={m.inactive}
                      >
                        ╳
                      </td>
                    ),
                  )}
                </tr>
              </Fragment>
            );
          })}
        </tbody>
      </table>

      {pickerCell && (
        <CellPicker
          row={pickerCell.row}
          cell={pickerCell.cell}
          pool={pool}
          assignedIds={pickerAssignedIds}
          attrLabel={attrLabel}
          handoffGaps={pickerHandoffGaps}
          onPick={handlePick}
          onClose={() => setPickerCell(null)}
        />
      )}
    </div>
  );
}
