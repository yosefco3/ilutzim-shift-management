import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  listProfiles,
  listAttributes,
  getNextWeekBoard,
  setWeekProfile,
  getPool,
  getAssignments,
  createAssignment,
  updateAssignmentSegment,
  deleteAssignment,
  reorderPositions,
  deletePosition,
  saveSchedule,
  exportScheduleGrid,
  exportGuardPositions,
  exportSchedulePng,
} from '../../api/builderApiClient';
import { triggerBlobDownload, weeklyExportFilename } from '../../utils/download';
import { useToast } from '../../components/Toast';
import BoardGrid from '../../components/board/BoardGrid';
import GuardPool from '../../components/board/GuardPool';
import ConfirmDialog from '../../components/ConfirmDialog';
import { autoSplitPoint, availabilityClip, segmentsCoverage } from '../../utils/intervals';
import {
  computeBoardWarnings,
  filterMutedWarnings,
  warnFocusTargets,
} from '../../utils/warnings';
import messages from '../../utils/messages';

// Display order for the soft-warning summary chips.
const WARN_ORDER = [
  'out_of_availability',
  'partial_coverage',
  'missing_attribute',
  'double_booking',
  'insufficient_rest',
  'over_continuous_hours',
  'over_consecutive_days',
];

// Per-admin (per-browser) preferences: the global on/off, and the set of
// individually-silenced warning types.
const WARN_PREF_KEY = 'builder.warningsEnabled';
const MUTED_WARN_KEY = 'builder.mutedWarnTypes';
const EMPTY_WARNINGS = { byCell: {}, byGuard: {}, summary: {} };

// Group a flat assignment list into { "positionId:dayIndex": [assignment, …] }.
function groupByCell(assignments) {
  const map = {};
  for (const a of assignments) {
    const key = `${a.position_id}:${a.day_index}`;
    (map[key] ||= []).push(a);
  }
  return map;
}

// The time window of a specific board cell (respects per-day overrides).
function findCellWindow(board, positionId, dayIndex) {
  const row = board?.rows?.find((r) => r.position_id === positionId);
  const cell = row?.cells?.find((c) => c.day_index === dayIndex);
  return cell?.window || null;
}

export default function BoardPage() {
  const toast = useToast();
  const navigate = useNavigate();
  const m = messages.board;

  const [profiles, setProfiles] = useState([]);
  const [attributes, setAttributes] = useState([]);
  const [board, setBoard] = useState(null);
  const [pool, setPool] = useState([]);
  const [assignmentsByCell, setAssignmentsByCell] = useState({});
  const [selectedGuardId, setSelectedGuardId] = useState(null);
  // Focus mode: the board + pool expand to fill the whole viewport and the
  // chrome (navbar, header, controls, warnings, legend) is hidden. Pure view
  // state — nothing about the schedule changes.
  const [focusMode, setFocusMode] = useState(false);
  const [noWeek, setNoWeek] = useState(false);
  // The message shown in the empty state when the board can't load. Defaults to
  // the "next week not created" guidance, but a different failure (e.g. no
  // profile configured) overrides it so the empty state isn't misleading.
  const [loadError, setLoadError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [confirmDeletePosition, setConfirmDeletePosition] = useState(null);
  // Admin can mute the soft warnings; the choice persists per browser.
  const [warningsEnabled, setWarningsEnabled] = useState(() => {
    try {
      return localStorage.getItem(WARN_PREF_KEY) !== 'false';
    } catch {
      return true;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(WARN_PREF_KEY, String(warningsEnabled));
    } catch {
      /* storage unavailable — keep the in-memory choice */
    }
  }, [warningsEnabled]);

  // Specific warning types the admin chose to silence (keeps the rest visible).
  const [mutedWarnTypes, setMutedWarnTypes] = useState(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem(MUTED_WARN_KEY) || '[]'));
    } catch {
      return new Set();
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(MUTED_WARN_KEY, JSON.stringify([...mutedWarnTypes]));
    } catch {
      /* storage unavailable — keep the in-memory choice */
    }
  }, [mutedWarnTypes]);

  const muteWarnType = useCallback((type) => {
    setMutedWarnTypes((prev) => new Set(prev).add(type));
  }, []);

  const restoreWarnType = useCallback((type) => {
    setMutedWarnTypes((prev) => {
      const next = new Set(prev);
      next.delete(type);
      return next;
    });
  }, []);

  const attrLabel = useMemo(
    () => (key) => attributes.find((a) => a.key === key)?.label || key,
    [attributes],
  );

  const selectedGuard = useMemo(
    () => pool.find((g) => g.id === selectedGuardId) || null,
    [pool, selectedGuardId],
  );

  // Focus mode hides the app chrome too (navbar, page header), which live
  // outside this component — so we flag it on <body> and let CSS hide them.
  // Cleared on unmount so leaving the page never leaves the app stuck hidden.
  useEffect(() => {
    document.body.classList.toggle('board-focus', focusMode);
    return () => document.body.classList.remove('board-focus');
  }, [focusMode]);

  // Esc exits focus mode first (if on); otherwise it clears the current
  // selection (the board stops being coloured). The cell picker keeps its own
  // Esc handler while it's open; both can coexist.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      if (focusMode) setFocusMode(false);
      else setSelectedGuardId(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [focusMode]);

  // Guards the admin hid from the pool for this working session (not a data
  // change — just removed from view; restorable).
  const [dismissedIds, setDismissedIds] = useState(() => new Set());
  const dismissGuard = useCallback(
    (id) => {
      setDismissedIds((prev) => new Set(prev).add(id));
      setSelectedGuardId((cur) => (cur === id ? null : cur));
    },
    [],
  );
  const restoreGuard = useCallback((id) => {
    setDismissedIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }, []);

  // Live coverage counters over active cells, honouring tiling (085): a cell is
  // covered only when its assigned segments fill the whole window; a lone partial
  // guard or a not-yet-completed split counts as partial.
  const coverageStats = useMemo(() => {
    let covered = 0;
    let partial = 0;
    let empty = 0;
    for (const row of board?.rows || []) {
      // Event positions have no coverage requirement — an empty event cell is a
      // valid state, so they never count toward covered/partial/empty.
      if (row.is_event) continue;
      for (const cell of row.cells) {
        if (!cell.active) continue;
        const list = assignmentsByCell[`${row.position_id}:${cell.day_index}`] || [];
        if (!list.length) {
          empty += 1;
          continue;
        }
        if (!cell.window) {
          covered += 1;
          continue;
        }
        const segs = list.map((a) =>
          a.segment_start && a.segment_end
            ? { start: a.segment_start, end: a.segment_end }
            : { start: cell.window.start, end: cell.window.end },
        );
        const { state } = segmentsCoverage(cell.window.start, cell.window.end, segs);
        if (state === 'full') covered += 1;
        else if (state === 'partial') partial += 1;
        else empty += 1;
      }
    }
    return { covered, partial, empty };
  }, [board, assignmentsByCell]);

  // Live soft warnings over every existing assignment (out-of-availability,
  // missing attribute, double booking, rest/continuity policy, empty cells).
  // Computed client-side from data already loaded — informs, never blocks.
  const warnings = useMemo(
    () => computeBoardWarnings({ board, assignmentsByCell, pool }),
    [board, assignmentsByCell, pool],
  );

  // Downstream (banner, cell badges, pool) sees: nothing when warnings are off
  // globally; otherwise the computed set minus any individually-muted types.
  const effectiveWarnings = useMemo(
    () => (warningsEnabled ? filterMutedWarnings(warnings, mutedWarnTypes) : EMPTY_WARNINGS),
    [warningsEnabled, warnings, mutedWarnTypes],
  );

  // Warning types present (count > 0), in a stable display order for the banner.
  const warnTypes = useMemo(
    () => WARN_ORDER.filter((t) => (effectiveWarnings.summary[t] || 0) > 0),
    [effectiveWarnings],
  );

  // Muted types that still occur in the data — shown as restorable chips so the
  // admin can see what they silenced and bring it back.
  const mutedTypes = useMemo(
    () => WARN_ORDER.filter((t) => mutedWarnTypes.has(t) && (warnings.summary[t] || 0) > 0),
    [mutedWarnTypes, warnings],
  );

  // Ordered jump targets per warning type, backing the "focus next" chip nav.
  const warnTargets = useMemo(
    () => warnFocusTargets(effectiveWarnings, (board?.rows || []).map((r) => r.position_id)),
    [effectiveWarnings, board],
  );

  // Per-type cursor (how far the admin has walked a type's occurrences) and the
  // cell currently flashed. `nonce` re-triggers the flash even on the same cell.
  const [warnCursor, setWarnCursor] = useState({});
  const [flashCell, setFlashCell] = useState({ key: null, nonce: 0 });

  // A board edit recomputes the targets — restart every walk from the top.
  useEffect(() => {
    setWarnCursor({});
  }, [warnTargets]);

  // Advance a type's cursor, scroll its next offending cell into view, and flash it.
  const focusNextWarn = useCallback(
    (type) => {
      const list = warnTargets[type] || [];
      if (!list.length) return;
      const next = ((warnCursor[type] ?? -1) + 1) % list.length;
      setWarnCursor((c) => ({ ...c, [type]: next }));
      setFlashCell((f) => ({ key: list[next], nonce: f.nonce + 1 }));
    },
    [warnTargets, warnCursor],
  );

  // Scroll the flashed cell into view once it's the active target.
  useEffect(() => {
    if (!flashCell.key) return;
    const el = document.querySelector(`[data-cell-id="${flashCell.key}"]`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
  }, [flashCell]);

  // The board always targets the *next week* — the same upcoming week guards
  // submit availability for. The backend resolves it (no week picker here).
  const loadBoard = useCallback(async () => {
    try {
      const data = await getNextWeekBoard();
      setBoard(data);
      setNoWeek(false);
      setLoadError(null);
      // The pool + existing assignments are scoped to the resolved week.
      const weekId = data.week.id;
      const [poolGuards, assignments] = await Promise.all([
        getPool(weekId),
        getAssignments(weekId),
      ]);
      setPool(poolGuards);
      setAssignmentsByCell(groupByCell(assignments));
    } catch (err) {
      // The board couldn't load. Usually the next week doesn't exist yet, but it
      // can also be a config problem (e.g. no profile) — show the real reason
      // rather than always blaming the missing week.
      setBoard(null);
      setNoWeek(true);
      setLoadError(err.message || null);
      toast.error(err.message || messages.common.error);
    }
  }, [toast]);

  // Reload assignments AND the pool — remaining hours shift on every mutation.
  const reloadAssignments = useCallback(async () => {
    if (!board?.week?.id) return;
    const [assignments, poolGuards] = await Promise.all([
      getAssignments(board.week.id),
      getPool(board.week.id),
    ]);
    setAssignmentsByCell(groupByCell(assignments));
    setPool(poolGuards);
  }, [board]);

  // Auto-save the downloadable snapshot after edits settle. Assignments already
  // persist live on every mutation; this just keeps the frozen snapshot (used by
  // the Weeks-page download, and otherwise refreshed on publish) in sync without
  // a manual button. Debounced so a burst of edits collapses into one save.
  // Silent on success — only a failed save surfaces a message.
  const autoSaveTimer = useRef(null);
  // Week id of a snapshot save that is scheduled but hasn't run yet — used to
  // flush it on unmount so a last-second edit isn't lost (F-3).
  const pendingSave = useRef(null);
  const scheduleAutoSave = useCallback(() => {
    const weekId = board?.week?.id;
    if (!weekId) return;
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
    pendingSave.current = weekId;
    autoSaveTimer.current = setTimeout(async () => {
      try {
        await saveSchedule(weekId);
      } catch (err) {
        toast.error(err.message || messages.common.error);
      } finally {
        pendingSave.current = null;
      }
    }, 1500);
  }, [board, toast]);

  // Flush any pending snapshot save when leaving the page so a last-second edit
  // still lands in the snapshot (the live assignments are already persisted
  // regardless). We cancel the timer and fire the save immediately — the request
  // outlives the unmounting component; a failure has nowhere to surface, so it is
  // swallowed rather than toasted (F-3).
  useEffect(
    () => () => {
      if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
      if (pendingSave.current) {
        saveSchedule(pendingSave.current).catch(() => {});
        pendingSave.current = null;
      }
    },
    [],
  );

  const handleAssign = useCallback(
    async (positionId, dayIndex, userId) => {
      if (!board?.week?.id) return;
      const row = board.rows?.find((r) => r.position_id === positionId);
      const cellAssignments = assignmentsByCell[`${positionId}:${dayIndex}`] || [];
      try {
        if (row?.is_event) {
          // Event (non-splitting) position: every guard covers the whole window
          // simultaneously — no tiling, no availability clip, no ≤2 cap. The
          // assignment carries no time segment.
          await createAssignment(board.week.id, {
            position_id: positionId,
            day_index: dayIndex,
            user_id: userId,
          });
        } else if (cellAssignments.length === 1) {
          // A second guard joins the cell → auto-tile the window. The handoff is
          // derived from guard A's continuous availability; the admin can then
          // drag the divider (085·05) to fine-tune it.
          const a = cellAssignments[0];
          const win = findCellWindow(board, positionId, dayIndex);
          const guardA = pool.find((g) => g.id === a.user_id);
          const guardB = pool.find((g) => g.id === userId);
          const split = win
            ? autoSplitPoint(
                win.start,
                win.end,
                guardA?.availability?.[String(dayIndex)] || [],
                guardB?.availability?.[String(dayIndex)] || [],
              )
            : null;
          await createAssignment(board.week.id, {
            position_id: positionId,
            day_index: dayIndex,
            user_id: userId,
            segment_start: split,
            segment_end: split ? win.end : null,
          });
          if (split) {
            await updateAssignmentSegment(a.id, {
              segment_start: win.start,
              segment_end: split,
            });
          }
        } else {
          // Empty cell: clip the guard to the hours they're actually available
          // for, so a partial-availability placement lands as a real segment +
          // gap (the admin can then drag the divider to extend them past their
          // availability). Full or no availability → whole window (segment null),
          // unchanged. A full cell falls here too and the server returns 409.
          const win = findCellWindow(board, positionId, dayIndex);
          const guard = pool.find((g) => g.id === userId);
          const seg = win
            ? availabilityClip(win.start, win.end, guard?.availability?.[String(dayIndex)] || [])
            : null;
          const payload = { position_id: positionId, day_index: dayIndex, user_id: userId };
          if (seg) {
            payload.segment_start = seg.start;
            payload.segment_end = seg.end;
          }
          await createAssignment(board.week.id, payload);
        }
        scheduleAutoSave();
        toast.success(m.cell.assigned);
      } catch (err) {
        toast.error(err.message || messages.common.error);
      } finally {
        // Always resync with the server — a multi-step mutation (create + sibling
        // segment) can leave the server ahead of the UI if the 2nd call fails (F-4).
        await reloadAssignments();
      }
    },
    [board, assignmentsByCell, pool, reloadAssignments, scheduleAutoSave, toast, m],
  );

  const handleUnassign = useCallback(
    async (assignmentId) => {
      // If removing one guard from a split cell leaves exactly one behind, that
      // guard goes back to covering the whole window (segment → null).
      let sibling = null;
      for (const list of Object.values(assignmentsByCell)) {
        if (list.some((a) => a.id === assignmentId)) {
          const others = list.filter((a) => a.id !== assignmentId);
          if (others.length === 1) [sibling] = others;
          break;
        }
      }
      try {
        await deleteAssignment(assignmentId);
        if (sibling && (sibling.segment_start || sibling.segment_end)) {
          await updateAssignmentSegment(sibling.id, {
            segment_start: null,
            segment_end: null,
          });
        }
        scheduleAutoSave();
        toast.success(m.cell.unassigned);
      } catch (err) {
        toast.error(err.message || messages.common.error);
      } finally {
        // delete + sibling-widen is two calls; resync regardless of outcome (F-4).
        await reloadAssignments();
      }
    },
    [assignmentsByCell, reloadAssignments, scheduleAutoSave, toast, m],
  );

  // The admin dragged the divider in a split cell → save the new handoff on both
  // assignments (A gets [start, split], B gets [split, end]). Two PATCH calls run
  // only on pointer-up, so this is cheap and atomic-enough.
  const handleSplitChange = useCallback(
    async (cellAssignments, splitHHMM) => {
      const [a, b] = cellAssignments;
      const win = findCellWindow(board, a.position_id, a.day_index);
      if (!win) return;
      try {
        await Promise.all([
          updateAssignmentSegment(a.id, { segment_start: win.start, segment_end: splitHHMM }),
          updateAssignmentSegment(b.id, { segment_start: splitHHMM, segment_end: win.end }),
        ]);
        scheduleAutoSave();
      } catch (err) {
        toast.error(err.message || messages.common.error);
      } finally {
        // Two PATCHes; if one fails the segments diverge — resync regardless (F-4).
        await reloadAssignments();
      }
    },
    [board, reloadAssignments, scheduleAutoSave, toast],
  );

  // The admin dragged the divider of a lone partial guard (CellPartial) → save
  // their new segment. Dragging to both window edges = whole-window cover, which
  // we persist as segment → null (matches the unassign-sibling convention).
  const handlePartialChange = useCallback(
    async (assignment, seg) => {
      const win = findCellWindow(board, assignment.position_id, assignment.day_index);
      if (!win) return;
      const whole = seg.start === win.start && seg.end === win.end;
      try {
        await updateAssignmentSegment(assignment.id, {
          segment_start: whole ? null : seg.start,
          segment_end: whole ? null : seg.end,
        });
        await reloadAssignments();
        scheduleAutoSave();
      } catch (err) {
        toast.error(err.message || messages.common.error);
      }
    },
    [board, reloadAssignments, scheduleAutoSave, toast],
  );

  // The admin dragged a position row to a new place within its band. The grid
  // sends the profile's full position-id list in the new order; persist it and
  // reload so the board reflects the new display_order.
  const handleReorderPositions = useCallback(
    async (orderedIds) => {
      const profileId = board?.profile?.id;
      if (!profileId) return;
      try {
        await reorderPositions(profileId, orderedIds);
        await loadBoard();
        scheduleAutoSave();
        toast.success(m.reordered);
      } catch (err) {
        toast.error(err.message || messages.common.error);
      }
    },
    [board, loadBoard, scheduleAutoSave, toast, m],
  );

  // Jump to the Positions editor for a specific position, on the board's own
  // effective profile. PositionsPage reads these params and auto-opens its editor.
  const handleEditPosition = useCallback(
    (positionId) => {
      const profileId = board?.profile?.id;
      if (!profileId) return;
      navigate(`/builder/positions?profile=${profileId}&edit=${positionId}`);
    },
    [board, navigate],
  );

  // Delete-position flow: the trash icon opens a confirm; confirming deletes the
  // position (and its assignments, backend-cascaded) and reloads the board.
  const handleDeletePositionRequest = useCallback(
    (positionId) => {
      const row = board?.rows?.find((r) => r.position_id === positionId);
      setConfirmDeletePosition({ id: positionId, name: row?.name || '' });
    },
    [board],
  );

  const handleDeletePosition = useCallback(async () => {
    const target = confirmDeletePosition;
    setConfirmDeletePosition(null);
    if (!target) return;
    try {
      await deletePosition(target.id);
      toast.success(m.positionDeleted);
      await loadBoard();
      scheduleAutoSave();
    } catch (err) {
      toast.error(err.message || messages.common.error);
    }
  }, [confirmDeletePosition, loadBoard, scheduleAutoSave, toast, m]);

  // Initial load: profiles + attributes (for the picker/chips) + the board.
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [profs, attrs] = await Promise.all([listProfiles(), listAttributes()]);
        setProfiles(profs);
        setAttributes(attrs);
      } catch (err) {
        toast.error(err.message || messages.common.error);
      }
      await loadBoard();
      setLoading(false);
    })();
  }, [toast, loadBoard]);

  const handleProfileChange = async (profileId) => {
    if (!board?.week?.id || !profileId) return;
    try {
      await setWeekProfile(board.week.id, profileId);
      toast.success(m.profileChanged);
      await loadBoard();
      scheduleAutoSave();
    } catch (err) {
      toast.error(err.message || messages.common.error);
    }
  };

  // Download the built-schedule grid (positions × days) as xlsx.
  const handleExportSchedule = async () => {
    if (!board?.week?.id) return;
    try {
      const blob = await exportScheduleGrid(board.week.id);
      triggerBlobDownload(blob, weeklyExportFilename('schedule', board.week.start_date));
    } catch (err) {
      toast.error(err.message || m.exportScheduleError);
    }
  };

  // Download the per-guard "positions" overview as xlsx.
  const handleExportGuardPositions = async () => {
    if (!board?.week?.id) return;
    try {
      const blob = await exportGuardPositions(board.week.id);
      triggerBlobDownload(blob, weeklyExportFilename('guard-positions', board.week.start_date));
    } catch (err) {
      toast.error(err.message || m.exportGuardPositionsError);
    }
  };

  // Download the built-schedule grid as a PNG — exactly what guards receive on
  // publish, so the admin can preview it before broadcasting.
  const handleExportSchedulePng = async () => {
    if (!board?.week?.id) return;
    try {
      const blob = await exportSchedulePng(board.week.id);
      triggerBlobDownload(
        blob, weeklyExportFilename('schedule', board.week.start_date, 'png'),
      );
    } catch (err) {
      toast.error(err.message || m.exportSchedulePngError);
    }
  };

  return (
    <div className={`page board-page${focusMode ? ' is-focus' : ''}`}>
      <header className="page-header">
        <div>
          <h1>{m.title}</h1>
          <p className="page-subtitle">{m.subtitle}</p>
        </div>
      </header>

      {loading ? (
        <p>{messages.common.loading}</p>
      ) : noWeek || !board ? (
        <p className="empty-state">{loadError || m.noNextWeek}</p>
      ) : (
        <>
          <div className="board-controls">
            <div className="board-control">
              <span>{m.nextWeek}</span>
              <strong className="board-week-label">
                📅 {board.week.start_date} — {board.week.end_date}
              </strong>
            </div>

            <label className="board-control">
              <span>{m.profile}</span>
              <select
                value={board.profile?.id || ''}
                onChange={(e) => handleProfileChange(e.target.value)}
              >
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>

            {board.is_default_fallback && (
              <span className="board-fallback-note">{m.defaultFallback}</span>
            )}

            <button
              type="button"
              className="btn btn-secondary board-export-schedule"
              onClick={handleExportSchedule}
            >
              {m.exportSchedule}
            </button>

            <button
              type="button"
              className="btn btn-secondary board-export-schedule"
              onClick={handleExportGuardPositions}
            >
              {m.exportGuardPositions}
            </button>

            <button
              type="button"
              className="btn btn-secondary board-export-schedule"
              onClick={handleExportSchedulePng}
            >
              {m.exportSchedulePng}
            </button>

            <button
              type="button"
              className="btn btn-secondary board-focus-toggle"
              onClick={() => setFocusMode(true)}
              title={m.focusHint}
            >
              {m.focusEnter}
            </button>

            <div className="board-coverage" role="status">
              <span className="cov-pill cov-pill-covered">
                {coverageStats.covered} {m.coverage.covered}
              </span>
              <span className="cov-pill cov-pill-partial">
                {coverageStats.partial} {m.coverage.partial}
              </span>
              <span className="cov-pill cov-pill-empty">
                {coverageStats.empty} {m.coverage.empty}
              </span>
            </div>
          </div>

          {board.rows.length > 0 && (
            <div className="board-summary" role="status">
              <span className="board-summary-title">⚠️ {m.warn.summaryTitle}</span>
              {!warningsEnabled ? (
                <span className="board-summary-none">{m.warn.disabled}</span>
              ) : warnTypes.length === 0 ? (
                <span className="board-summary-none">{m.warn.none}</span>
              ) : (
                warnTypes.map((type) => {
                  const targets = warnTargets[type] || [];
                  const count = effectiveWarnings.summary[type];
                  const cursor = warnCursor[type];
                  const label = m.warn.summary[type];
                  return (
                    <span key={type} className="board-summary-chip">
                      {targets.length > 0 ? (
                        <button
                          type="button"
                          className="board-summary-chip-focus"
                          title={m.warn.focusHint}
                          onClick={() => focusNextWarn(type)}
                        >
                          {label}{' '}
                          <strong>{cursor != null ? `${cursor + 1}/${targets.length}` : count}</strong>
                        </button>
                      ) : (
                        <span className="board-summary-chip-label">
                          {label} <strong>{count}</strong>
                        </span>
                      )}
                      <button
                        type="button"
                        className="board-summary-chip-mute"
                        aria-label={`${m.warn.mute}: ${label}`}
                        title={m.warn.mute}
                        onClick={(e) => {
                          e.stopPropagation();
                          muteWarnType(type);
                        }}
                      >
                        ×
                      </button>
                    </span>
                  );
                })
              )}

              {warningsEnabled && mutedTypes.length > 0 && (
                <span className="board-summary-muted">
                  <span className="board-summary-muted-label">{m.warn.mutedLabel}</span>
                  {mutedTypes.map((type) => (
                    <button
                      key={type}
                      type="button"
                      className="board-summary-chip is-muted"
                      title={m.warn.restore}
                      onClick={() => restoreWarnType(type)}
                    >
                      {m.warn.summary[type]} ↺
                    </button>
                  ))}
                </span>
              )}

              <label className="board-warn-toggle">
                <input
                  type="checkbox"
                  checked={warningsEnabled}
                  onChange={(e) => setWarningsEnabled(e.target.checked)}
                />
                {m.warn.toggle}
              </label>
            </div>
          )}

          {board.rows.length === 0 ? (
            <p className="empty-state">{m.empty}</p>
          ) : (
            <div className="board-layout">
              {focusMode && (
                <button
                  type="button"
                  className="btn btn-secondary board-focus-exit"
                  onClick={() => setFocusMode(false)}
                  title={m.focusHint}
                >
                  {m.focusExit}
                </button>
              )}
              <GuardPool
                guards={pool}
                selectedId={selectedGuardId}
                onSelect={setSelectedGuardId}
                attrLabel={attrLabel}
                guardWarnings={effectiveWarnings.byGuard}
                dismissedIds={dismissedIds}
                onDismiss={dismissGuard}
                onRestore={restoreGuard}
              />
              <BoardGrid
                board={board}
                attrLabel={attrLabel}
                pool={pool}
                assignmentsByCell={assignmentsByCell}
                selectedGuard={selectedGuard}
                onAssign={handleAssign}
                onUnassign={handleUnassign}
                onSplitChange={handleSplitChange}
                onPartialChange={handlePartialChange}
                onReorderPositions={handleReorderPositions}
                onEditPosition={handleEditPosition}
                onDeletePosition={handleDeletePositionRequest}
                warnings={effectiveWarnings}
                flashCell={flashCell}
              />
            </div>
          )}

          {board.rows.length > 0 && (
            <div className="board-legend" aria-hidden="true">
              <span>{m.legend.full}</span>
              <span>{m.legend.partial}</span>
              <span>{m.legend.expanded}</span>
              <span>{m.legend.warn}</span>
              <span>{m.legend.available}</span>
              <span>{m.legend.event}</span>
              <span>{m.legend.inactive}</span>
            </div>
          )}
        </>
      )}

      <ConfirmDialog
        open={!!confirmDeletePosition}
        title={m.deletePositionTitle}
        message={m.deletePositionMsg}
        confirmLabel={m.deletePosition}
        onConfirm={handleDeletePosition}
        onCancel={() => setConfirmDeletePosition(null)}
      />
    </div>
  );
}
