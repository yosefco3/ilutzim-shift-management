import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import messages from '../../utils/messages';
import { DAY_NAMES_SHORT as DAY_NAMES } from '../../utils/guardMessages.js';
import CellHoursPopover from './CellHoursPopover';

// The 7 day indices in canonical Sunday→Saturday order. The app is dir=rtl, so a
// plain <table> renders the first column (position name) on the right and ראשון
// naturally to its left — no direction fighting, no column reversing.
const DAY_INDICES = [0, 1, 2, 3, 4, 5, 6];

// Toggle-ON fallback when neither the snapshot cell nor any snapshot day has a
// usable window [EDGE: step 04 restore order (c)].
const DEFAULT_WINDOW = { start: '07:00', end: '15:00' };

// Deep, independent copy of the positions list so the editable working copy can
// mutate day_schedules without touching the load-time snapshot or the prop. The
// payload is plain JSON (strings/numbers/bools), so JSON clone is exact here.
const clonePositions = (ps) => JSON.parse(JSON.stringify(ps ?? []));

// A day is "active" when it carries a usable {start, end} window — same test the
// read-only render in step 03 used.
const windowActive = (w) => !!w && !!w.start && !!w.end;

// Two windows are equal only if both are active with identical hours, or both
// inactive (absent/empty). Drives per-cell dirty highlight and per-row diffing.
function windowsEqual(a, b) {
  const ak = windowActive(a) ? `${a.start}|${a.end}` : null;
  const bk = windowActive(b) ? `${b.start}|${b.end}` : null;
  return ak === bk;
}

// Has this position's day map drifted from the load-time snapshot?
function scheduleChanged(snapMap, workMap) {
  for (const d of DAY_INDICES) {
    if (!windowsEqual(snapMap?.[String(d)], workMap?.[String(d)])) return true;
  }
  return false;
}

/**
 * Positions × days matrix (steps 03–05). Step 03 laid out the read-only grid;
 * step 04 made each cell toggle its day on/off, track dirty cells against an
 * immutable load-time snapshot, and save only the changed rows via the step-02
 * bulk endpoint. Step 05 adds a per-cell hours popover (start/end) on active
 * cells — pencil or double-click opens it; confirm writes the window into the
 * working row through the same dirty/save pipeline (no server call from the
 * popover). Multi-select / label editing land in 06–07.
 *
 * Toggle-ON restore order: the snapshot's hours for that cell → else the
 * position's first active window in the snapshot → else 07:00–15:00. All-days-off
 * for a position is allowed here (no ≥1-day client rule) [EDGE D3].
 *
 * This component owns the working state (snapshot + editable copy + dirty diff
 * + toolbar) and stays self-contained. Saving is delegated up: it calls `onSave`
 * with ONLY the changed rows [EDGE C1], and PositionsPage does the API call,
 * toast, and reload. On success/409 the page reloads positions → this component
 * resets its snapshot; on other failures the page does NOT reload, so the dirty
 * state survives for a retry [EDGE N1]. `onDirtyChange` lets the page guard
 * navigation while there are unsaved changes [EDGE N2].
 *
 * Props:
 *   positions     — listPositions() result (display_order). The load-time truth.
 *   profile       — the selected ActivationProfile (carries day_labels). Optional.
 *   onSave        — async (items) => 'ok' | 'conflict' | 'error'. items:
 *                   [{ position_id, day_schedules }] for the changed rows only.
 *   onDirtyChange — (changedPositionCount) => void. Optional.
 */
export default function ProfileMatrix({ positions, profile, onSave, onDirtyChange }) {
  const m = messages.positions;
  const labels = profile?.day_labels || {};

  // Load-time snapshot (immutable truth for the dirty diff and toggle restore)
  // and the editable working copy. Both reset whenever `positions` changes
  // (initial load, post-save reload, post-409 reload, profile switch).
  const [snapshot, setSnapshot] = useState(() => clonePositions(positions));
  const [working, setWorking] = useState(() => clonePositions(positions));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setSnapshot(clonePositions(positions));
    setWorking(clonePositions(positions));
  }, [positions]);

  // Changed positions (rows whose day map differs from the snapshot) — drives the
  // toolbar count and the save payload [EDGE C1: only changed rows are sent].
  const changedPositions = useMemo(
    () => working.filter((p, i) => scheduleChanged(snapshot[i]?.day_schedules, p.day_schedules)),
    [working, snapshot],
  );
  const changedCount = changedPositions.length;

  // Report dirtiness up so the page can guard tab/profile/route changes. Fires
  // only when the count actually changes (memoized dep).
  useEffect(() => {
    onDirtyChange?.(changedCount);
  }, [changedCount, onDirtyChange]);

  // The window to restore when toggling a day back ON (restore order a→b→c).
  const restoreWindow = useCallback((snapPos, d) => {
    const snapDS = snapPos?.day_schedules || {};
    const cell = snapDS[String(d)];
    if (windowActive(cell)) return { start: cell.start, end: cell.end };
    for (const dd of DAY_INDICES) {
      const w = snapDS[String(dd)];
      if (windowActive(w)) return { start: w.start, end: w.end };
    }
    return { ...DEFAULT_WINDOW };
  }, []);

  const toggle = useCallback(
    (posIdx, d) => {
      setWorking((cur) => {
        // Copy the row + its day map so the snapshot and other rows stay untouched.
        const next = cur.map((p, i) =>
          i === posIdx ? { ...p, day_schedules: { ...(p.day_schedules || {}) } } : p,
        );
        const ds = next[posIdx].day_schedules;
        const key = String(d);
        if (windowActive(ds[key])) {
          delete ds[key]; // ON → OFF
        } else {
          ds[key] = restoreWindow(snapshot[posIdx], d); // OFF → ON (restored)
        }
        return next;
      });
    },
    [snapshot, restoreWindow],
  );

  const handleSave = async () => {
    const items = changedPositions.map(({ id, day_schedules }) => ({
      position_id: id,
      day_schedules,
    }));
    setSaving(true);
    try {
      await onSave?.(items);
    } finally {
      setSaving(false);
    }
  };

  // Revert the working copy to the snapshot (no server call).
  const handleDiscard = () => {
    setWorking(clonePositions(snapshot));
  };

  // ── Step 05: per-cell hours popover ───────────────────────────────────
  // One popover at a time; opening another simply replaces `openCell`.
  const [openCell, setOpenCell] = useState(null); // { posIdx, d } | null

  // The cell's working window captured on the FIRST click of a double-click.
  // A double-click fires two toggles first (off→on, restored from the snapshot);
  // onDoubleClick reverts the cell to this captured value so the admin edits the
  // window they actually saw — including any unsaved (dirty) edit, which must
  // not be silently lost.
  const dblCapture = useRef(null);

  const openPopover = (posIdx, d) => setOpenCell({ posIdx, d });
  const closePopover = () => setOpenCell(null);

  // Popover confirm → write the window into the WORKING row only, then close.
  // Same dirty/save path as a toggle (no server call here).
  const setCellWindow = (posIdx, d, { start, end }) => {
    setWorking((cur) => {
      const next = cur.map((p, i) =>
        i === posIdx ? { ...p, day_schedules: { ...(p.day_schedules || {}) } } : p,
      );
      next[posIdx].day_schedules[String(d)] = { start, end };
      return next;
    });
    setOpenCell(null);
  };

  // Single click = toggle (kept synchronous — snappy, and the step-04 tests
  // assert the change immediately after the click). On the first click of a
  // possible double-click we also remember the pre-click window (see above).
  const handleCellClick = (posIdx, d, e) => {
    if (e?.detail === 1) {
      const w = working[posIdx]?.day_schedules?.[String(d)];
      dblCapture.current = { posIdx, d, win: w ? { ...w } : null };
    }
    toggle(posIdx, d);
  };

  // Double-click = open the popover. Revert the two toggles to the captured
  // window first, then open on the (now restored) active cell.
  const handleCellDblClick = (posIdx, d) => {
    const cap = dblCapture.current;
    dblCapture.current = null;
    const captured = cap && cap.posIdx === posIdx && cap.d === d;
    if (captured) {
      setWorking((cur) => {
        const next = cur.map((p, i) =>
          i === posIdx ? { ...p, day_schedules: { ...(p.day_schedules || {}) } } : p,
        );
        const key = String(d);
        if (cap.win && windowActive(cap.win)) next[posIdx].day_schedules[key] = { ...cap.win };
        else delete next[posIdx].day_schedules[key];
        return next;
      });
    }
    // Open only when the (post-revert) cell is active. Double-clicking an OFF
    // cell must not park a hidden openCell that would pop the popover the next
    // time the cell is toggled on.
    const win = captured ? cap.win : working[posIdx]?.day_schedules?.[String(d)];
    if (windowActive(win)) setOpenCell({ posIdx, d });
    else setOpenCell(null);
  };

  return (
    <div className="profile-matrix-scroll">
      <div className="profile-matrix-toolbar">
        <button
          type="button"
          className="btn btn-primary"
          disabled={changedCount === 0 || saving}
          onClick={handleSave}
        >
          {m.matrixSave(changedCount)}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={changedCount === 0 || saving}
          onClick={handleDiscard}
        >
          {m.matrixDiscard}
        </button>
      </div>
      <table className="profile-matrix">
        <thead>
          <tr>
            <th scope="col" className="profile-matrix-col-name">
              {m.matrixPositionCol}
            </th>
            {DAY_INDICES.map((d) => (
              <th key={d} scope="col" className="profile-matrix-col-day">
                <span className="profile-matrix-day-name">{DAY_NAMES[d]}</span>
                {labels[String(d)] ? (
                  <span className="profile-matrix-day-label">{labels[String(d)]}</span>
                ) : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {working.map((p, posIdx) => (
            <tr key={p.id}>
              <th scope="row" className="profile-matrix-row-name">
                <span className="profile-matrix-name-text">{p.name}</span>
                {p.is_event && (
                  <span className="position-event-badge">
                    {p.event_required_count != null
                      ? `${m.eventBadge} · ${p.event_required_count}`
                      : m.eventBadge}
                  </span>
                )}
              </th>
              {DAY_INDICES.map((d) => {
                const win = p.day_schedules?.[String(d)];
                const active = windowActive(win);
                const snapWin = snapshot[posIdx]?.day_schedules?.[String(d)];
                const snapActive = windowActive(snapWin);
                const dirty =
                  active !== snapActive ||
                  (active && snapActive && (win.start !== snapWin.start || win.end !== snapWin.end));
                const cellOpen = active && openCell?.posIdx === posIdx && openCell?.d === d;
                return (
                  <td
                    key={d}
                    role="button"
                    tabIndex={0}
                    aria-pressed={active}
                    aria-label={`${p.name}, ${DAY_NAMES[d]}, ${active ? m.active : m.matrixOff}`}
                    className={`profile-matrix-cell${active ? '' : ' is-off'}${dirty ? ' is-dirty' : ''}`}
                    title={active ? undefined : m.matrixOff}
                    onClick={(e) => handleCellClick(posIdx, d, e)}
                    onDoubleClick={() => handleCellDblClick(posIdx, d)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        toggle(posIdx, d);
                      }
                    }}
                  >
                    {active ? (
                      <>
                        <span className="profile-matrix-cell-label">
                          {m.matrixHours(win.start, win.end)}
                        </span>
                        <button
                          type="button"
                          className="profile-matrix-cell-edit"
                          aria-label={m.matrixEditHours}
                          title={m.matrixEditHours}
                          onClick={(e) => {
                            // Never toggle — the pencil only opens the popover.
                            e.stopPropagation();
                            openPopover(posIdx, d);
                          }}
                          onKeyDown={(e) => e.stopPropagation()}
                        >
                          ✎
                        </button>
                        {cellOpen && (
                          <CellHoursPopover
                            start={win.start}
                            end={win.end}
                            onConfirm={(w) => setCellWindow(posIdx, d, w)}
                            onCancel={closePopover}
                          />
                        )}
                      </>
                    ) : (
                      <span className="profile-matrix-cell-label">✕</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
