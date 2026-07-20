import { Fragment, useState, useEffect, useMemo, useCallback, useRef } from 'react';
import messages from '../../utils/messages';
import { DAY_NAMES_SHORT as DAY_NAMES } from '../../utils/guardMessages.js';
import CellHoursPopover from './CellHoursPopover';
import EventCountPopover from './EventCountPopover';

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

// ── Display bands (mirror of backend board_service) ────────────────────────
// A position's band derives from its canonical (most-common) daily start time,
// exactly like the board groups its rows. Cutoffs locked with the user 2026-06-28.
//   🌅 morning  07:00–15:00 · 🌆 evening  15:00–23:00 · 🌙 night  23:00–07:00
const BAND_ORDER = ['morning', 'evening', 'night'];
const _toMin = (hhmm) => {
  const [h, m] = String(hhmm).split(':');
  return Number(h) * 60 + Number(m);
};
const bandForStart = (min) => {
  if (min >= 7 * 60 && min < 15 * 60) return 'morning';
  if (min >= 15 * 60 && min < 23 * 60) return 'evening';
  return 'night';
};
// The most-common {start,end} across active days (ties → earliest day, matching
// the backend's Counter.most_common on day-ordered windows). Empty → 'night'
// (backend maps a windowless row to the night start).
const bandForRow = (daySchedules) => {
  const entries = Object.entries(daySchedules || {})
    .filter(([, w]) => windowActive(w))
    .sort((a, b) => Number(a[0]) - Number(b[0]));
  if (!entries.length) return 'night';
  const counts = new Map();
  let bestStart = entries[0][1].start;
  let bestCount = 0;
  for (const [, w] of entries) {
    const key = `${w.start}|${w.end}`;
    const c = (counts.get(key) || 0) + 1;
    counts.set(key, c);
    if (c > bestCount) {
      bestCount = c;
      bestStart = w.start;
    }
  }
  return bandForStart(_toMin(bestStart));
};

// Variant days: within a row, the "usual" window is the most-common active
// window (mode). Active days whose window differs from that mode are flagged so
// an admin spots the one/two weekly exceptions at a glance. Off days never
// count. Nothing is flagged when the row has <2 active days, when the most-
// common window is a tie (no clear majority to deviate from), or when every
// active day already shares the same window. Recomputed from the WORKING state,
// so the marks update live as hours are toggled/edited.
const winKey = (w) => `${w.start}|${w.end}`;
function variantDaysForRow(daySchedules) {
  const active = [];
  for (const d of DAY_INDICES) {
    const w = daySchedules?.[String(d)];
    if (windowActive(w)) active.push([d, winKey(w)]);
  }
  if (active.length < 2) return new Set();
  const counts = new Map();
  for (const [, k] of active) counts.set(k, (counts.get(k) || 0) + 1);
  // Most-common window + whether that maximum is unique (a clear majority).
  let maxCount = 0;
  let maxKey = null;
  let tie = false;
  for (const [k, c] of counts) {
    if (c > maxCount) {
      maxCount = c;
      maxKey = k;
      tie = false;
    } else if (c === maxCount) {
      tie = true;
    }
  }
  if (tie || maxCount === active.length) return new Set(); // no majority / all same
  const out = new Set();
  for (const [d, k] of active) if (k !== maxKey) out.add(d);
  return out;
}

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

// Stable string id for a cell — step 06 selection/bulk ops key on this.
const cellKey = (posIdx, d) => `${posIdx}:${d}`;

// All cells inside the rectangle between two corners (inclusive) — step 06
// drag-select sweeps the bounding rectangle (simpler & more predictable than a
// freeform swept set).
const rectKeys = (a, c) => {
  const minP = Math.min(a.posIdx, c.posIdx);
  const maxP = Math.max(a.posIdx, c.posIdx);
  const minD = Math.min(a.d, c.d);
  const maxD = Math.max(a.d, c.d);
  const out = [];
  for (let p = minP; p <= maxP; p++) {
    for (let d = minD; d <= maxD; d++) out.push(cellKey(p, d));
  }
  return out;
};

/**
 * Positions × days matrix (steps 03–06). Step 03 laid out the read-only grid;
 * step 04 made each cell toggle its day on/off, track dirty cells against an
 * immutable load-time snapshot, and save only the changed rows via the step-02
 * bulk endpoint. Step 05 added a per-cell hours popover (start/end) on active
 * cells. Step 06 adds bulk gestures so a whole holiday day is 2 clicks:
 *
 *   • Drag-select (mouse): pointer-down on a cell + drag over others selects the
 *     bounding rectangle (visual outline). Ctrl/Cmd+click adds/removes a single
 *     cell. A plain click still toggles one cell; double-click still opens the
 *     popover; the pencil still works. Click-vs-drag is split by "did the
 *     pointer enter another cell while the button was down" (movement
 *     threshold). A real drag sets a one-shot suppress flag so the click that
 *     follows the pointer-up does NOT also toggle.
 *   • Selection action bar (≥2 selected): כבה / הדלק (step-04 restore order) /
 *     קבע שעות… (one CellHoursPopover; applies to every selected ACTIVE cell —
 *     off cells stay off) / נקה בחירה.
 *   • Day-header chevron menu: כבה את כל היום / הדלק את כל היום / קבע שעות לכל
 *     היום… (same popover, all ACTIVE cells in the column). One menu open at a
 *     time; click-outside closes.
 *
 * Touch/coarse pointers: drag-select would fight the horizontal scroll, so it is
 * mouse-only — on touch a tap still toggles and whole-day ops reach via the
 * header menu (per spec).
 *
 * Everything mutates ONLY the working state — same dirty tint, same single
 * "שמירה (N)", no new server calls.
 *
 * Toggle-ON restore order: the snapshot's hours for that cell → else the
 * position's first active window in the snapshot → else 07:00–15:00. All-days-off
 * for a position is allowed here (no ≥1-day client rule) [EDGE D3].
 *
 * This component owns the working state (snapshot + editable copy + dirty diff
 * + toolbar + selection) and stays self-contained. Saving is delegated up: it
 * calls `onSave` with ONLY the changed rows [EDGE C1], and PositionsPage does
 * the API call, toast, and reload. On success/409 the page reloads positions →
 * this component resets its snapshot; on other failures the page does NOT
 * reload, so the dirty state survives for a retry [EDGE N1]. `onDirtyChange`
 * lets the page guard navigation while there are unsaved changes [EDGE N2].
 *
 * Step 07 turns the header day-label chip into an inline editor: click the chip
 * (or "+ תווית" when none) → an <input maxLength 50>; Enter/blur confirms,
 * Escape cancels. Confirm hands the day + new value up via onSaveDayLabel; the
 * PAGE owns the merge + PATCH + toast + state refresh (label edits are profile
 * meta, NOT part of the grid dirty state, so they save immediately). The label
 * editor joins the overlay-exclusivity family: opening it closes openCell /
 * openMenu / hoursEditor and vice versa. While the input is open, cell clicks
 * and selection keep working — the input stopPropagation's its key/click events
 * (like CellHoursPopover) so Enter/Escape never leak into cell handlers.
 *
 * Props:
 *   positions       — listPositions() result (display_order). The load-time truth.
 *   profile         — the selected ActivationProfile (carries day_labels). Optional.
 *   onSave          — async (items) => 'ok' | 'conflict' | 'error'. items:
 *                     [{ position_id, day_schedules }] for the changed rows only.
 *   onDirtyChange   — (changedPositionCount) => void. Optional.
 *   onSaveDayLabel  — (day, value) => Promise|void. Step 07: persist one day's
 *                     label. The page merges the full day_labels map and PATCHes.
 *                     Optional (no-op when absent, e.g. in tests).
 *   onSaveEventCount — async (positionId, count|null) => 'ok' | 'error'. Persist an
 *                     event row's participant count (event_required_count). On 'ok'
 *                     the matrix updates its own snapshot+working in place (this is
 *                     position META, NOT part of the grid dirty state), so unsaved
 *                     hour edits survive. Optional (no-op when absent).
 */
export default function ProfileMatrix({
  positions,
  profile,
  onSave,
  onDirtyChange,
  onSaveDayLabel,
  onSaveEventCount,
  onDeletePosition,
}) {
  const m = messages.positions;
  const labels = profile?.day_labels || {};

  // Load-time snapshot (immutable truth for the dirty diff and toggle restore)
  // and the editable working copy. Both reset whenever `positions` changes
  // (initial load, post-save reload, post-409 reload, profile switch).
  const [snapshot, setSnapshot] = useState(() => clonePositions(positions));
  const [working, setWorking] = useState(() => clonePositions(positions));
  const [saving, setSaving] = useState(false);

  // ── Step 06: multi-select + column operations ──────────────────────────
  // selection  — Set of "posIdx:d" strings (rectangle drag + ctrl/cmd-click).
  // openMenu   — the day index whose header chevron menu is open, or null.
  // hoursEditor — one shared CellHoursPopover for bulk "קבע שעות", anchored to
  //               the action bar (kind 'bar') or a day header (kind 'col').
  const [selection, setSelection] = useState(() => new Set());
  const [openMenu, setOpenMenu] = useState(null);
  const [hoursEditor, setHoursEditor] = useState(null);
  // Row index whose event participant-count editor is open (event rows only), or null.
  const [eventEditor, setEventEditor] = useState(null);

  // In-flight drag state (anchor cell + whether the pointer has entered another
  // cell = "it became a drag") and the one-shot flag that swallows the click a
  // browser fires right after a drag's pointer-up.
  const drag = useRef({ anchor: null, dragging: false });
  const suppressClick = useRef(false);
  const menuRef = useRef(null);

  useEffect(() => {
    setSnapshot(clonePositions(positions));
    setWorking(clonePositions(positions));
    // A positions reload invalidates positional selection indices and any open
    // overlay — reset all step-06 UI state too.
    setSelection(new Set());
    setOpenMenu(null);
    setHoursEditor(null);
    setOpenCell(null);
    setEditingDay(null);
    setEventEditor(null);
  }, [positions]);

  // Changed positions (rows whose day map differs from the snapshot) — drives the
  // toolbar count and the save payload [EDGE C1: only changed rows are sent].
  const changedPositions = useMemo(
    () => working.filter((p, i) => scheduleChanged(snapshot[i]?.day_schedules, p.day_schedules)),
    [working, snapshot],
  );
  const changedCount = changedPositions.length;

  // Per-row display band + per-band totals, for the band group headers that
  // separate morning/evening/night — mirroring the board (תצוגה כמו בלוח).
  const rowBands = useMemo(
    () => working.map((p) => bandForRow(p.day_schedules)),
    [working],
  );
  // Per-row set of "variant" day indices (active days whose hours differ from
  // the row's most-common window) — drives the small exception-day marker.
  const rowVariants = useMemo(
    () => working.map((p) => variantDaysForRow(p.day_schedules)),
    [working],
  );
  const bandCounts = useMemo(() => {
    const c = {};
    for (const b of rowBands) c[b] = (c[b] || 0) + 1;
    return c;
  }, [rowBands]);

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

  // Apply `mutate(dayMap, posIdx, d)` to each cell in `keys`, cloning ONLY the
  // touched rows so unchanged rows keep their identity (and scheduleChanged
  // stays a clean value compare). Used by every step-06 bulk gesture.
  const applyToCells = useCallback((keys, mutate) => {
    setWorking((cur) => {
      const byRow = new Map(); // posIdx → Set<d>
      for (const k of keys) {
        const sep = k.indexOf(':');
        const p = Number(k.slice(0, sep));
        const d = Number(k.slice(sep + 1));
        if (!byRow.has(p)) byRow.set(p, new Set());
        byRow.get(p).add(d);
      }
      const next = cur.slice();
      for (const [posIdx, days] of byRow) {
        const orig = cur[posIdx];
        if (!orig) continue;
        const ds = { ...(orig.day_schedules || {}) };
        for (const d of days) mutate(ds, posIdx, d);
        next[posIdx] = { ...orig, day_schedules: ds };
      }
      return next;
    });
  }, []);

  // Prefill for the bulk-hours popover: the first ACTIVE target cell's window,
  // else the standard 07:00–15:00. Deterministic + friendly.
  const firstActiveWin = useCallback(
    (keys) => {
      for (const k of keys) {
        const sep = k.indexOf(':');
        const p = Number(k.slice(0, sep));
        const d = Number(k.slice(sep + 1));
        const w = working[p]?.day_schedules?.[String(d)];
        if (windowActive(w)) return { start: w.start, end: w.end };
      }
      return { ...DEFAULT_WINDOW };
    },
    [working],
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

  // ── Step 07: header day-label editor ───────────────────────────────────
  // editingDay = the day index whose label chip is currently an <input>, or null.
  // labelDraft = the in-flight input value. `labelClosed` is a one-shot guard:
  // Enter/Escape deliberately close the editor, and the <input>'s trailing blur
  // would otherwise re-confirm — the guard makes that blur a no-op (no double
  // PATCH, and Escape stays a true cancel).
  const [editingDay, setEditingDay] = useState(null);
  const [labelDraft, setLabelDraft] = useState('');
  const labelClosed = useRef(false);

  // The cell's working window captured on the FIRST click of a double-click.
  // A double-click fires two toggles first (off→on, restored from the snapshot);
  // onDoubleClick reverts the cell to this captured value so the admin edits the
  // window they actually saw — including any unsaved (dirty) edit, which must
  // not be silently lost.
  const dblCapture = useRef(null);

  // Opening any overlay closes the others — only one popover/menu/editor at a
  // time. Step 07 adds the label editor to this exclusivity family.
  const openPopover = (posIdx, d) => {
    setOpenMenu(null);
    setHoursEditor(null);
    setEditingDay(null);
    setEventEditor(null);
    setOpenCell({ posIdx, d });
  };
  const closePopover = () => setOpenCell(null);

  // ── Event participant-count editor (row header, event rows only) ───────
  // Opening it joins the overlay-exclusivity family. Confirm persists via the
  // page, then patches the count into BOTH snapshot and working IN PLACE — the
  // count is position meta, not part of the grid dirty diff (which compares only
  // day_schedules), so any unsaved hour edits survive.
  const openEventEditor = (posIdx) => {
    setOpenMenu(null);
    setHoursEditor(null);
    setOpenCell(null);
    setEditingDay(null);
    setEventEditor(posIdx);
  };
  const closeEventEditor = () => setEventEditor(null);
  const confirmEventCount = async (posIdx, count) => {
    const pos = working[posIdx];
    setEventEditor(null);
    if (!pos) return;
    const res = await onSaveEventCount?.(pos.id, count);
    if (res && res !== 'ok') return; // save failed — keep the old value
    const patch = (arr) =>
      arr.map((p, i) => (i === posIdx ? { ...p, event_required_count: count } : p));
    setSnapshot(patch);
    setWorking(patch);
  };

  // ── Step 07: header day-label editor helpers ──────────────────────────
  // Open: seed the draft from the current label (or '') and arm the close-guard.
  const openLabelEditor = (d) => {
    setOpenMenu(null);
    setHoursEditor(null);
    setOpenCell(null);
    setEventEditor(null);
    labelClosed.current = false;
    setLabelDraft(labels[String(d)] || '');
    setEditingDay(d);
  };
  // Cancel (Escape): drop the draft, never PATCH. Arm the guard so the input's
  // unmount-blur doesn't turn this into a confirm.
  const cancelLabel = () => {
    labelClosed.current = true;
    setEditingDay(null);
  };
  // Confirm (Enter/blur): hand the day + raw draft up to the page (it trims,
  // merges the full map, PATCHes). Skip the round-trip when nothing changed.
  const commitLabel = (d) => {
    if (labelClosed.current) return; // already closed by Enter/Escape — ignore blur
    labelClosed.current = true;
    const existing = labels[String(d)] || '';
    const next = labelDraft.trim();
    setEditingDay(null);
    if (next === existing) return; // unchanged → no PATCH (end-state identical)
    onSaveDayLabel?.(d, labelDraft);
  };

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

  // ── Step 06: bulk hours editor (selection bar / day header) ───────────
  // Same CellHoursPopover as the per-cell editor; on confirm it writes the
  // chosen window to every ACTIVE cell among `keys` (off cells stay off).
  const openHoursEditor = (kind, keys, extra = {}) => {
    const pre = firstActiveWin(keys);
    setOpenCell(null);
    setOpenMenu(null);
    setEditingDay(null);
    setEventEditor(null);
    setHoursEditor({ kind, keys, start: pre.start, end: pre.end, ...extra });
  };
  const confirmHoursEditor = (w) => {
    if (!hoursEditor) return;
    applyToCells(hoursEditor.keys, (ds, _p, d) => {
      if (windowActive(ds[String(d)])) ds[String(d)] = { start: w.start, end: w.end };
    });
    setHoursEditor(null);
  };
  const cancelHoursEditor = () => setHoursEditor(null);

  // ── Step 06: drag-select gestures ────────────────────────────────────
  const onCellPointerDown = (posIdx, d, e) => {
    // Touch/pen would fight the matrix's horizontal scroll; on coarse pointers
    // selection reaches via the day-header menu (per spec). Mouse (and the test
    // runner, whose pointer events carry no pointerType) drives the drag.
    if (e.pointerType && e.pointerType !== 'mouse') return;
    if (e.button != null && e.button !== 0) return; // primary button only
    if (e.ctrlKey || e.metaKey) return; // ctrl/cmd-click is handled by the click
    // The pencil owns its own pointerdown — don't start a drag from it.
    if (e.target?.closest?.('.profile-matrix-cell-edit')) return;
    drag.current = { anchor: { posIdx, d }, dragging: false };
    const finish = () => {
      if (drag.current.dragging) suppressClick.current = true; // swallow the click
      drag.current = { anchor: null, dragging: false };
    };
    document.addEventListener('pointerup', finish, { once: true });
  };

  const onCellPointerEnter = (posIdx, d) => {
    const st = drag.current;
    if (!st.anchor) return;
    // Entering another cell while the button is held = it's a drag (threshold).
    if (st.anchor.posIdx === posIdx && st.anchor.d === d) return;
    st.dragging = true;
    setSelection(new Set(rectKeys(st.anchor, { posIdx, d })));
  };

  // ── Step 06: selection action-bar actions ────────────────────────────
  const selOff = () =>
    applyToCells([...selection], (ds, _p, d) => {
      delete ds[String(d)];
    });
  const selOn = () =>
    applyToCells([...selection], (ds, p, d) => {
      ds[String(d)] = restoreWindow(snapshot[p], d);
    });
  const selClear = () => {
    setSelection(new Set());
    setHoursEditor(null);
  };

  // ── Step 06: column (day-header) actions ─────────────────────────────
  const colKeys = useCallback(
    (d) => working.map((_, p) => cellKey(p, d)),
    [working],
  );
  const applyColumnOff = (d) =>
    applyToCells(colKeys(d), (ds, _p, dd) => {
      delete ds[String(dd)];
    });
  const applyColumnOn = (d) =>
    applyToCells(colKeys(d), (ds, p, dd) => {
      ds[String(dd)] = restoreWindow(snapshot[p], dd);
    });
  const openColumnHours = (d) => openHoursEditor('col', colKeys(d), { d });

  // Single click = toggle (kept synchronous — snappy, and the step-04 tests
  // assert the change immediately after the click). Step 06 layers on top:
  //   • after a real drag → swallow (suppressClick) so the drag isn't also a toggle
  //   • ctrl/cmd-click → toggle the cell's membership in the selection (no on/off)
  //   • plain click → clear any selection first, then toggle
  // On the first click of a possible double-click we also remember the pre-click
  // window (see dblCapture).
  const handleCellClick = (posIdx, d, e) => {
    if (suppressClick.current) {
      suppressClick.current = false;
      return;
    }
    if (e?.ctrlKey || e?.metaKey) {
      const key = cellKey(posIdx, d);
      setSelection((cur) => {
        const next = new Set(cur);
        if (next.has(key)) next.delete(key);
        else next.add(key);
        return next;
      });
      return;
    }
    if (selection.size > 0) setSelection(new Set());
    if (e?.detail === 1) {
      const w = working[posIdx]?.day_schedules?.[String(d)];
      dblCapture.current = { posIdx, d, win: w ? { ...w } : null };
    }
    toggle(posIdx, d);
  };

  // Double-click = open the popover. Revert the two toggles to the captured
  // window first, then open on the (now restored) active cell.
  const handleCellDblClick = (posIdx, d) => {
    setOpenMenu(null);
    setHoursEditor(null);
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

  // Click-outside closes the open day-header menu (only one is open at a time,
  // so a single ref is enough). The chevron toggles via its own onClick; when
  // the menu is open a click on the chevron is outside menuRef → the listener
  // closes it, and the chevron's toggle (closed→null) agrees.
  useEffect(() => {
    if (openMenu === null) return undefined;
    const onDown = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setOpenMenu(null);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [openMenu]);

  // Any selection change invalidates an open selection-bar hours editor (its
  // keys were a snapshot of the previous selection). Column editors are tied to
  // a day, not the selection, so they are left alone.
  useEffect(() => {
    if (hoursEditor?.kind === 'bar') setHoursEditor(null);
  }, [selection]);

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

      {/* Step 06: selection action bar — only when ≥2 cells are selected. */}
      {selection.size >= 2 && (
        <div className="profile-matrix-selbar" role="toolbar" aria-label={m.matrixSelBar}>
          <span className="profile-matrix-selbar-count">{m.matrixSelCount(selection.size)}</span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={selOff}>
            {m.matrixSelOff}
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={selOn}>
            {m.matrixSelOn}
          </button>
          <span className="profile-matrix-hours-wrap">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => openHoursEditor('bar', [...selection])}
            >
              {m.matrixSelHours}
            </button>
            {hoursEditor?.kind === 'bar' && (
              <CellHoursPopover
                start={hoursEditor.start}
                end={hoursEditor.end}
                onConfirm={confirmHoursEditor}
                onCancel={cancelHoursEditor}
              />
            )}
          </span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={selClear}>
            {m.matrixSelClear}
          </button>
        </div>
      )}

      <table className="profile-matrix">
        <thead>
          <tr>
            <th scope="col" className="profile-matrix-col-name">
              {m.matrixPositionCol}
            </th>
            {DAY_INDICES.map((d) => (
              <th key={d} scope="col" className="profile-matrix-col-day">
                <span className="profile-matrix-day-name">{DAY_NAMES[d]}</span>
                {/* Step 07: editable day-label. Click the chip (or "+ תווית" when
                    none) → inline input; Enter/blur confirm, Escape cancels. */}
                {editingDay === d ? (
                  <input
                    type="text"
                    className="profile-matrix-day-label-input"
                    value={labelDraft}
                    maxLength={50}
                    autoFocus
                    aria-label={`${DAY_NAMES[d]} · ${m.matrixEditDayLabel}`}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => setLabelDraft(e.target.value)}
                    onKeyDown={(e) => {
                      e.stopPropagation();
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        commitLabel(d);
                      } else if (e.key === 'Escape') {
                        e.preventDefault();
                        cancelLabel();
                      }
                    }}
                    onBlur={() => commitLabel(d)}
                  />
                ) : labels[String(d)] ? (
                  <button
                    type="button"
                    className="profile-matrix-day-label"
                    aria-label={`${DAY_NAMES[d]} · ${m.matrixEditDayLabel}`}
                    title={`${DAY_NAMES[d]} · ${m.matrixEditDayLabel}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      openLabelEditor(d);
                    }}
                  >
                    {labels[String(d)]}
                  </button>
                ) : (
                  <button
                    type="button"
                    className="profile-matrix-day-label profile-matrix-day-label-add"
                    aria-label={`${DAY_NAMES[d]} · ${m.matrixAddDayLabel}`}
                    title={`${DAY_NAMES[d]} · ${m.matrixAddDayLabel}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      openLabelEditor(d);
                    }}
                  >
                    {m.matrixAddDayLabel}
                  </button>
                )}
                {/* Step 06: per-day header menu (aria-label includes the day). */}
                <button
                  type="button"
                  className="profile-matrix-day-menu-btn"
                  aria-label={`${DAY_NAMES[d]} · ${m.matrixDayMenu}`}
                  aria-haspopup="true"
                  aria-expanded={openMenu === d}
                  onClick={() => {
                    setEditingDay(null);
                    setOpenMenu((cur) => (cur === d ? null : d));
                  }}
                >
                  ▾
                </button>
                {openMenu === d && (
                  <div className="profile-matrix-day-menu" ref={menuRef} role="menu">
                    <button
                      type="button"
                      role="menuitem"
                      className="btn btn-ghost btn-sm"
                      onClick={() => {
                        applyColumnOff(d);
                        setOpenMenu(null);
                      }}
                    >
                      {m.matrixDayOff}
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      className="btn btn-ghost btn-sm"
                      onClick={() => {
                        applyColumnOn(d);
                        setOpenMenu(null);
                      }}
                    >
                      {m.matrixDayOn}
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      className="btn btn-ghost btn-sm"
                      onClick={() => openColumnHours(d)}
                    >
                      {m.matrixDayHours}
                    </button>
                  </div>
                )}
                {/* Bulk-hours popover for the whole column (menu closes first). */}
                {hoursEditor?.kind === 'col' && hoursEditor.d === d && (
                  <CellHoursPopover
                    start={hoursEditor.start}
                    end={hoursEditor.end}
                    onConfirm={confirmHoursEditor}
                    onCancel={cancelHoursEditor}
                  />
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {working.map((p, posIdx) => {
            // A band group header prints once, above the first row of each band —
            // a small morning/evening/night separation, like the board.
            const band = rowBands[posIdx];
            const bandChanged = posIdx === 0 || rowBands[posIdx - 1] !== band;
            return (
            <Fragment key={p.id}>
              {bandChanged && (
                <tr className="profile-matrix-band-head">
                  <td colSpan={1 + DAY_INDICES.length}>
                    {messages.board.bands[band]}
                    <span className="profile-matrix-band-count">
                      {' · '}
                      {bandCounts[band]} {messages.board.positionsCount}
                    </span>
                  </td>
                </tr>
              )}
            <tr>
              <th scope="row" className="profile-matrix-row-name">
                <span className="profile-matrix-name-text">{p.name}</span>
                {typeof onDeletePosition === 'function' && (
                  <button
                    type="button"
                    className="profile-matrix-row-delete"
                    aria-label={`${p.name} · ${m.matrixDeletePosition}`}
                    title={m.matrixDeletePosition}
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeletePosition(p);
                    }}
                  >
                    🗑
                  </button>
                )}
                {p.is_event && (
                  <button
                    type="button"
                    className="position-event-badge position-event-badge-btn"
                    aria-label={`${p.name} · ${m.matrixEditEventCount}`}
                    title={m.matrixEditEventCount}
                    onClick={(e) => {
                      e.stopPropagation();
                      openEventEditor(posIdx);
                    }}
                  >
                    {p.event_required_count != null
                      ? `${m.eventBadge} · ${p.event_required_count}`
                      : m.eventBadge}
                    <span className="position-event-badge-pencil" aria-hidden="true">✎</span>
                  </button>
                )}
                {eventEditor === posIdx && (
                  <EventCountPopover
                    count={p.event_required_count ?? null}
                    onConfirm={(count) => confirmEventCount(posIdx, count)}
                    onCancel={closeEventEditor}
                  />
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
                const selected = selection.has(cellKey(posIdx, d));
                // Active day whose hours differ from the row's usual window.
                const variant = active && rowVariants[posIdx]?.has(d);
                return (
                  <td
                    key={d}
                    role="button"
                    tabIndex={0}
                    aria-pressed={active}
                    aria-label={`${p.name}, ${DAY_NAMES[d]}, ${active ? m.active : m.matrixOff}${
                      variant ? ` · ${m.matrixVariantDay}` : ''
                    }`}
                    className={`profile-matrix-cell${active ? '' : ' is-off'}${
                      dirty ? ' is-dirty' : ''
                    }${selected ? ' is-selected' : ''}${variant ? ' is-variant' : ''}`}
                    title={active ? (variant ? m.matrixVariantDay : undefined) : m.matrixOff}
                    onClick={(e) => handleCellClick(posIdx, d, e)}
                    onDoubleClick={() => handleCellDblClick(posIdx, d)}
                    onPointerDown={(e) => onCellPointerDown(posIdx, d, e)}
                    onPointerEnter={() => onCellPointerEnter(posIdx, d)}
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
            </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
