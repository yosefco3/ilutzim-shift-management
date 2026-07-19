/**
 * ActualBoardPage — "סידור בפועל": the editable execution copy of a started
 * week's schedule.
 *
 * The planning board freezes when the week starts; this page is where reality
 * gets recorded — a guard replaced day-of, an ad-hoc position for an
 * unforeseen event, a cancelled position. The attendance comparison and the
 * payroll reports read THIS board (behind the backend flag), so what the
 * admin fixes here is what ends up in the reports.
 *
 * Editing is FREE — no time gate (ended weeks stay editable for retro payroll
 * fixes), no availability rules, no two-guard cap. The board surfaces soft
 * warnings instead of blocking. Every mutation persists immediately (the DB
 * is the source of truth here — no snapshot/debounce layer like the planner).
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  createActualAssignment,
  createActualPosition,
  createReinforcement,
  deleteActualAssignment,
  deleteActualPosition,
  deleteReinforcement,
  exportActualScheduleGrid,
  exportActualSchedulePng,
  getActualBoard,
  listAttributes,
  saveActualAsProfile,
  updateActualPosition,
  updateActualSegment,
} from '../api/builderApiClient';
import { fetchGuards } from '../api/adminApiClient';
import { triggerBlobDownload, weeklyExportFilename } from '../utils/download';
import ReinforcementDialog from '../components/actual/ReinforcementDialog';
import BoardGrid from '../components/board/BoardGrid';
import GuardPool from '../components/board/GuardPool';
import ConfirmDialog from '../components/ConfirmDialog';
import PositionEditorModal from '../components/positions/PositionEditorModal';
import { useToast } from '../components/Toast';
import { useWeeks } from '../hooks/useWeeks';
import useBoardFit from '../hooks/useBoardFit';
import { autoSplitPoint } from '../utils/intervals';
import messages from '../utils/messages';

// Group a flat actual-assignment list into { "positionId:dayIndex": [a, …] }.
// The actual rows expose their ActualPosition id as `position_id`, so the
// assignments (which carry `actual_position_id`) are re-keyed to match.
function groupByCell(assignments) {
  const map = {};
  for (const a of assignments) {
    const key = `${a.actual_position_id}:${a.day_index}`;
    (map[key] ||= []).push({ ...a, position_id: a.actual_position_id });
  }
  return map;
}

// Every day covered in full — the pool has no submitted-availability notion,
// so a selected guard paints every active cell as a clean fit (BoardGrid's
// coverage preview reads this; '07:00–07:00' normalises to the whole day).
const FULL_AVAILABILITY = Object.fromEntries(
  Array.from({ length: 7 }, (_, i) => [String(i), [{ start: '07:00', end: '07:00' }]]),
);

const fmtDate = (iso) => {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
};

function findCellWindow(rows, positionId, dayIndex) {
  const row = rows?.find((r) => r.position_id === positionId);
  const cell = row?.cells?.find((c) => c.day_index === dayIndex);
  return cell?.window || null;
}

// Actual-board row (cells) → the position shape the shared editor form seeds
// from ({name, day_schedules, required_attributes, is_event, ...}).
function rowToPosition(row) {
  const day_schedules = {};
  for (const cell of row.cells || []) {
    if (cell.active && cell.window) {
      day_schedules[String(cell.day_index)] = {
        start: cell.window.start,
        end: cell.window.end,
      };
    }
  }
  return {
    id: row.position_id,
    name: row.name,
    day_schedules,
    required_attributes: row.required_attributes || [],
    is_event: row.is_event,
    event_required_count: row.event_required_count,
  };
}

export default function ActualBoardPage() {
  const m = messages.actualBoard;
  const toast = useToast();
  const { weeks, loading: weeksLoading } = useWeeks();
  const [searchParams, setSearchParams] = useSearchParams();

  const todayIso = new Date().toISOString().slice(0, 10);
  // Only weeks that already started have an actual layer; newest first, so the
  // running week is the natural default.
  const startedWeeks = useMemo(
    () =>
      weeks
        .filter((w) => (w.start_date || '') <= todayIso)
        .sort((a, b) => (a.start_date < b.start_date ? 1 : -1)),
    [weeks, todayIso],
  );

  const requestedWeekId = searchParams.get('week');
  const selectedWeekId = useMemo(() => {
    if (requestedWeekId && startedWeeks.some((w) => w.id === requestedWeekId)) {
      return requestedWeekId;
    }
    return startedWeeks[0]?.id || null;
  }, [requestedWeekId, startedWeeks]);

  const [board, setBoard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  // The requirement-attribute vocabulary — feeds the shared position form and
  // the row chips. Best-effort (an empty list just hides the checkboxes).
  const [attributes, setAttributes] = useState([]);
  // Focus mode: board + pool take over the viewport, chrome hidden — the same
  // "מסך מלא" the planning board has. Pure view state.
  const [focusMode, setFocusMode] = useState(false);

  useEffect(() => {
    listAttributes().then(setAttributes).catch(() => {});
  }, []);

  // Layout effect (declared before useBoardFit below): the navbar must be
  // back in the layout before the fit measurement runs on focus-exit.
  useLayoutEffect(() => {
    document.body.classList.toggle('board-focus', focusMode);
    return () => document.body.classList.remove('board-focus');
  }, [focusMode]);

  // The header/warnings banner above the board shifts the panes down — refit
  // their max-height whenever the content above them can change.
  const layoutRef = useBoardFit(focusMode, [loading, board]);

  // The pool: every active guard (no availability math here — day-of reality),
  // sorted by name. The "AHMASH first" grouping is GuardPool's own toggle.
  const [pool, setPool] = useState([]);
  const [selectedGuardId, setSelectedGuardId] = useState(null);
  const [dismissedIds, setDismissedIds] = useState(() => new Set());

  useEffect(() => {
    fetchGuards()
      .then((users) => {
        const list = (Array.isArray(users) ? users : users.items || [])
          .filter((u) => u.is_active !== false)
          .map((u) => ({
            id: u.id,
            full_name: u.full_name || `${u.first_name} ${u.last_name}`,
            roles: u.roles || [],
            notes: u.exemptions_notes || null,
            availability: FULL_AVAILABILITY,
          }))
          .sort((a, b) => a.full_name.localeCompare(b.full_name, 'he'));
        setPool(list);
      })
      .catch((err) => toast.error(err?.message || messages.common.error));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadBoard = useCallback(async (weekId) => {
    setLoadError(null);
    try {
      setBoard(await getActualBoard(weekId));
    } catch (err) {
      setBoard(null);
      setLoadError(err?.message || messages.common.error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedWeekId) {
      setLoading(true);
      loadBoard(selectedWeekId);
    } else if (!weeksLoading) {
      setLoading(false);
    }
  }, [selectedWeekId, weeksLoading, loadBoard]);

  // One refetch refreshes rows + assignments + warnings together.
  const reload = useCallback(
    () => (selectedWeekId ? loadBoard(selectedWeekId) : Promise.resolve()),
    [selectedWeekId, loadBoard],
  );

  const assignmentsByCell = useMemo(
    () => (board ? groupByCell(board.assignments) : {}),
    [board],
  );

  // Team + this week's reinforcements (מתגברים) in one pool: reinforcements
  // are selectable/assignable like anyone, wear a synthetic "מתגבר" chip, and
  // sit at the end (external one-offs, not the scarce organic resource).
  const fullPool = useMemo(() => {
    const cards = (board?.reinforcements || []).map((r) => ({
      id: r.user_id,
      full_name: r.full_name,
      roles: ['REINFORCEMENT'],
      notes: r.note || null,
      availability: FULL_AVAILABILITY,
    }));
    return [...pool, ...cards];
  }, [pool, board]);

  const selectedGuard = useMemo(
    () => fullPool.find((g) => g.id === selectedGuardId) || null,
    [fullPool, selectedGuardId],
  );

  // Esc exits focus mode first (if on); otherwise it clears the selection —
  // the same order as the planning board.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      if (focusMode) setFocusMode(false);
      else setSelectedGuardId(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [focusMode]);

  // ── Assignment editing ────────────────────────────────────────────────────

  const handleAssign = useCallback(
    async (positionId, dayIndex, userId) => {
      if (!selectedWeekId || !board) return;
      const row = board.rows.find((r) => r.position_id === positionId);
      const cellAssignments = assignmentsByCell[`${positionId}:${dayIndex}`] || [];
      try {
        if (!row?.is_event && cellAssignments.length === 1) {
          // A second guard joins a regular cell → tile at the window midpoint
          // (no availability to derive a smarter handoff from); the admin
          // drags the divider to fine-tune. Windows under an hour don't split —
          // both guards simply share the whole window.
          const a = cellAssignments[0];
          const win = findCellWindow(board.rows, positionId, dayIndex);
          const split = win ? autoSplitPoint(win.start, win.end, [], []) : null;
          await createActualAssignment(selectedWeekId, {
            actual_position_id: positionId,
            day_index: dayIndex,
            user_id: userId,
            segment_start: split,
            segment_end: split ? win.end : null,
          });
          if (split) {
            await updateActualSegment(a.id, {
              segment_start: win.start,
              segment_end: split,
            });
          }
        } else {
          // Empty cell / event: the guard takes the whole window.
          await createActualAssignment(selectedWeekId, {
            actual_position_id: positionId,
            day_index: dayIndex,
            user_id: userId,
          });
        }
      } catch (err) {
        toast.error(err?.message || messages.common.error);
      } finally {
        await reload();
      }
    },
    [selectedWeekId, board, assignmentsByCell, reload, toast],
  );

  const handleUnassign = useCallback(
    async (assignmentId) => {
      // Removing one guard from a split cell widens the survivor back to the
      // whole window (matches the planner's convention).
      let sibling = null;
      for (const list of Object.values(assignmentsByCell)) {
        if (list.some((a) => a.id === assignmentId)) {
          const others = list.filter((a) => a.id !== assignmentId);
          if (others.length === 1) [sibling] = others;
          break;
        }
      }
      try {
        await deleteActualAssignment(assignmentId);
        if (sibling && (sibling.segment_start || sibling.segment_end)) {
          await updateActualSegment(sibling.id, {
            segment_start: null,
            segment_end: null,
          });
        }
      } catch (err) {
        toast.error(err?.message || messages.common.error);
      } finally {
        await reload();
      }
    },
    [assignmentsByCell, reload, toast],
  );

  const handleSplitChange = useCallback(
    async (cellAssignments, splitHHMM) => {
      const [a, b] = cellAssignments;
      const win = findCellWindow(board?.rows, a.position_id, a.day_index);
      if (!win) return;
      try {
        await Promise.all([
          updateActualSegment(a.id, { segment_start: win.start, segment_end: splitHHMM }),
          updateActualSegment(b.id, { segment_start: splitHHMM, segment_end: win.end }),
        ]);
      } catch (err) {
        toast.error(err?.message || messages.common.error);
      } finally {
        await reload();
      }
    },
    [board, reload, toast],
  );

  const handlePartialChange = useCallback(
    async (assignment, seg) => {
      const win = findCellWindow(board?.rows, assignment.position_id, assignment.day_index);
      if (!win) return;
      const whole = seg.start === win.start && seg.end === win.end;
      try {
        await updateActualSegment(assignment.id, {
          segment_start: whole ? null : seg.start,
          segment_end: whole ? null : seg.end,
        });
      } catch (err) {
        toast.error(err?.message || messages.common.error);
      } finally {
        await reload();
      }
    },
    [board, reload, toast],
  );

  // ── Position editing ──────────────────────────────────────────────────────

  // null = closed · 'new' = create · a row object = edit that position.
  const [positionDialog, setPositionDialog] = useState(null);
  const [confirmDeletePosition, setConfirmDeletePosition] = useState(null);

  const handleSavePosition = useCallback(
    async (payload) => {
      try {
        if (positionDialog === 'new') {
          await createActualPosition(selectedWeekId, payload);
        } else {
          await updateActualPosition(positionDialog.id, payload);
        }
        setPositionDialog(null);
        toast.success(m.positionSaved);
        await reload();
      } catch (err) {
        toast.error(err?.message || messages.common.error);
      }
    },
    [positionDialog, selectedWeekId, reload, toast, m],
  );

  const handleDeletePosition = useCallback(async () => {
    const target = confirmDeletePosition;
    setConfirmDeletePosition(null);
    if (!target) return;
    try {
      await deleteActualPosition(target.position_id);
      toast.success(m.positionDeleted);
    } catch (err) {
      toast.error(err?.message || messages.common.error);
    } finally {
      await reload();
    }
  }, [confirmDeletePosition, reload, toast, m]);

  // ── Reinforcements (מתגברים) ──────────────────────────────────────────────

  const [reinforcementDialogOpen, setReinforcementDialogOpen] = useState(false);

  const handleAddReinforcement = useCallback(
    async (payload) => {
      try {
        const created = await createReinforcement(selectedWeekId, payload);
        toast.success(m.reinforcements.added(created.full_name));
        await reload();
        return true;
      } catch (err) {
        toast.error(err?.message || messages.common.error);
        return false;
      }
    },
    [selectedWeekId, reload, toast, m],
  );

  const handleRemoveReinforcement = useCallback(
    async (card) => {
      try {
        await deleteReinforcement(card.id);
        setSelectedGuardId((cur) => (cur === card.user_id ? null : cur));
        toast.success(m.reinforcements.removed);
      } catch (err) {
        toast.error(err?.message || messages.common.error);
      } finally {
        await reload();
      }
    },
    [reload, toast, m],
  );

  // ── Exports (Excel / PNG) — same products as the planning board ──────────

  const weekStartDate = useMemo(
    () => startedWeeks.find((w) => w.id === selectedWeekId)?.start_date,
    [startedWeeks, selectedWeekId],
  );

  const handleExportExcel = useCallback(async () => {
    if (!selectedWeekId) return;
    try {
      const blob = await exportActualScheduleGrid(selectedWeekId);
      triggerBlobDownload(
        blob, weeklyExportFilename('actual_schedule', weekStartDate),
      );
    } catch (err) {
      toast.error(err?.message || messages.common.error);
    }
  }, [selectedWeekId, weekStartDate, toast]);

  const handleExportPng = useCallback(async () => {
    if (!selectedWeekId) return;
    try {
      const blob = await exportActualSchedulePng(selectedWeekId);
      triggerBlobDownload(
        blob, weeklyExportFilename('actual_schedule', weekStartDate, 'png'),
      );
    } catch (err) {
      toast.error(err?.message || messages.common.error);
    }
  }, [selectedWeekId, weekStartDate, toast]);

  // ── Save as profile ───────────────────────────────────────────────────────

  const [profileDialogOpen, setProfileDialogOpen] = useState(false);
  const [profileName, setProfileName] = useState('');

  const handleSaveAsProfile = useCallback(async () => {
    const name = profileName.trim();
    if (!name) return;
    try {
      const created = await saveActualAsProfile(selectedWeekId, name);
      setProfileDialogOpen(false);
      setProfileName('');
      toast.success(m.saveAsProfileDone(created.name));
    } catch (err) {
      toast.error(err?.message || messages.common.error);
    }
  }, [profileName, selectedWeekId, toast, m]);

  // ── Render ────────────────────────────────────────────────────────────────

  if (weeksLoading || loading) {
    return (
      <div className="page">
        <div className="loading">{messages.common.loading}</div>
      </div>
    );
  }

  return (
    <div className={`page board-page${focusMode ? ' is-focus' : ''}`}>
      <div className="page-header">
        <h2>
          {m.title}
          <span className="actual-badge">{m.badge}</span>
        </h2>
      </div>
      <p className="page-subtitle">{m.subtitle}</p>

      {startedWeeks.length === 0 ? (
        <div className="empty-state">{m.noStartedWeeks}</div>
      ) : (
        <>
          <div className="actual-toolbar">
            <label htmlFor="actual-week-picker">{m.weekPicker}</label>
            <select
              id="actual-week-picker"
              value={selectedWeekId || ''}
              onChange={(e) => setSearchParams(e.target.value ? { week: e.target.value } : {})}
            >
              {startedWeeks.map((w, i) => (
                <option key={w.id} value={w.id}>
                  {fmtDate(w.start_date)} – {fmtDate(w.end_date)}
                  {i === 0 ? ` · ${m.currentWeek}` : ''}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setPositionDialog('new')}
            >
              ➕ {m.addPosition}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setReinforcementDialogOpen(true)}
            >
              🧩 {m.reinforcements.button}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setProfileDialogOpen(true)}
            >
              💾 {m.saveAsProfile}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleExportExcel}
            >
              ⬇️ {m.exportExcel}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleExportPng}
            >
              🖼️ {m.exportPng}
            </button>
            <Link className="btn btn-secondary btn-sm" to="/actual/report">
              📊 {m.reinforcements.reportTitle}
            </Link>
            <button
              type="button"
              className="btn btn-secondary btn-sm board-focus-toggle"
              onClick={() => setFocusMode(true)}
              title={messages.board.focusHint}
            >
              {messages.board.focusEnter}
            </button>
          </div>

          {loadError && <div className="empty-state">{loadError}</div>}

          {board && (
            <>
              {board.warnings.length > 0 && (
                <div className="actual-warnings-banner">
                  <div>🟧 {m.warningsCount(board.warnings.length)}</div>
                  <ul className="actual-warnings-list">
                    {board.warnings.map((w, i) => (
                      // eslint-disable-next-line react/no-array-index-key
                      <li key={i}>{m.warnLine[w.type] ? m.warnLine[w.type](w) : w.type}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="board-layout" ref={layoutRef}>
                {focusMode && (
                  <button
                    type="button"
                    className="btn btn-secondary board-focus-exit"
                    onClick={() => setFocusMode(false)}
                    title={messages.board.focusHint}
                  >
                    {messages.board.focusExit}
                  </button>
                )}
                <BoardGrid
                  board={board}
                  assignmentsByCell={assignmentsByCell}
                  pool={fullPool}
                  selectedGuard={selectedGuard}
                  onAssign={handleAssign}
                  onUnassign={handleUnassign}
                  onSplitChange={handleSplitChange}
                  onPartialChange={handlePartialChange}
                  onEditPosition={(positionId) => {
                    const row = board.rows.find((r) => r.position_id === positionId);
                    setPositionDialog(row ? rowToPosition(row) : null);
                  }}
                  onDeletePosition={(positionId) => {
                    const row = board.rows.find((r) => r.position_id === positionId);
                    setConfirmDeletePosition({ position_id: positionId, name: row?.name || '' });
                  }}
                />
                <GuardPool
                  guards={fullPool}
                  selectedId={selectedGuardId}
                  onSelect={setSelectedGuardId}
                  dismissedIds={dismissedIds}
                  onDismiss={(id) => {
                    setDismissedIds((prev) => new Set(prev).add(id));
                    setSelectedGuardId((cur) => (cur === id ? null : cur));
                  }}
                  onRestore={(id) =>
                    setDismissedIds((prev) => {
                      const next = new Set(prev);
                      next.delete(id);
                      return next;
                    })
                  }
                  simple
                  subtitle={m.poolSubtitle}
                />
              </div>
            </>
          )}
        </>
      )}

      <PositionEditorModal
        open={positionDialog !== null}
        position={positionDialog === 'new' ? null : positionDialog}
        attributes={attributes}
        onSave={handleSavePosition}
        onCancel={() => setPositionDialog(null)}
        onInvalidDays={() => toast.error(messages.positions.needOneDay)}
      />

      <ReinforcementDialog
        open={reinforcementDialogOpen}
        reinforcements={board?.reinforcements || []}
        onAdd={handleAddReinforcement}
        onRemove={handleRemoveReinforcement}
        onClose={() => setReinforcementDialogOpen(false)}
      />

      {confirmDeletePosition && (
        <ConfirmDialog
          title={m.deletePositionTitle}
          message={m.deletePositionMessage(confirmDeletePosition.name)}
          confirmLabel={messages.common.delete}
          onConfirm={handleDeletePosition}
          onCancel={() => setConfirmDeletePosition(null)}
        />
      )}

      {profileDialogOpen && (
        <div className="modal-overlay" onClick={() => setProfileDialogOpen(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal-title">{m.saveAsProfileTitle}</h3>
            <p>{m.saveAsProfileHint}</p>
            <label className="actual-pos-field">
              {m.saveAsProfileName}
              <input
                type="text"
                value={profileName}
                autoFocus
                onChange={(e) => setProfileName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSaveAsProfile();
                }}
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-primary"
                disabled={!profileName.trim()}
                onClick={handleSaveAsProfile}
              >
                {messages.common.save}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setProfileDialogOpen(false)}
              >
                {messages.common.cancel}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
