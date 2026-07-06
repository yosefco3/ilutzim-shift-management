// Soft-warning engine for the schedule builder (task 07).
//
// Pure, client-side: derives every warning from data the BoardPage already holds
// (board + assignmentsByCell + pool), reusing the security-day interval math in
// ./intervals. No network, no DOM. Warnings are *soft* — they inform, never block.
//
// Warning types (see STAGE_B_PROMPTS/07_soft_warnings + 075_one_guard_per_shift):
//   per-cell : out_of_availability, partial_coverage, missing_attribute,
//              double_booking, already_in_shift
//   per-guard: insufficient_rest, over_continuous_hours, over_consecutive_days
// (Empty active cells are surfaced by the board "ריק" coverage stat, not here.)

import { normalize, coverage, toMin } from './intervals';

const DAY_MINUTES = 24 * 60;

// Policy thresholds (locked with the user, 2026-06-29). Tweak here.
export const WARNING_POLICY = {
  restMinutes: 8 * 60, // min rest between two work blocks
  maxConsecutiveDays: 6, // max consecutive assigned days
  maxContinuousMinutes: 12 * 60, // max length of one continuous work block
};

// Severity drives the colour: 'hard' (red) vs 'soft' (orange). Soft = the
// schedule is incomplete but nothing is being violated; hard = an actual rule
// is being bent (always allowed, but it should stand out).
export const WARNING_SEVERITY = {
  out_of_availability: 'hard',
  missing_attribute: 'hard',
  double_booking: 'hard',
  insufficient_rest: 'hard',
  over_continuous_hours: 'hard',
  over_consecutive_days: 'hard',
  partial_coverage: 'soft',
  // Same guard used more than once in one shift (band) on one day. The "no repeat
  // in a shift" rule — soft, because the manager may override it deliberately.
  already_in_shift: 'soft',
  // A fixed-count event (e.g. מועצה = 4) with fewer guards than required. Soft —
  // the event is under-staffed but nothing is being violated.
  understaffed_event: 'soft',
};

// A short human sentence for one warning. `mw` = messages.board.warn; `attrLabel`
// maps an attribute key to its Hebrew label. Kept i18n-free (strings passed in)
// so it stays unit-testable.
export function warningText(w, mw, attrLabel = (k) => k) {
  const who = w.guardName ? `${w.guardName}: ` : '';
  switch (w.type) {
    case 'out_of_availability':
      return `${who}${mw.outOfAvailability}`;
    case 'partial_coverage':
      return `${who}${mw.partialCoverage} ${(w.gaps || [])
        .map((g) => `${g.start}–${g.end}`)
        .join(', ')}`;
    case 'missing_attribute':
      return `${who}${mw.missingAttribute} ${(w.missing || []).map(attrLabel).join(', ')}`;
    case 'double_booking':
      return `${who}${mw.doubleBooking} ${w.otherPosition || ''}`;
    case 'already_in_shift':
      return `${who}${mw.alreadyInShift}`;
    case 'understaffed_event':
      return `${mw.understaffedEvent} (${w.have}/${w.need})`;
    case 'insufficient_rest':
      return `${who}${mw.insufficientRest} (${w.gapHours} ${mw.hoursSuffix})`;
    case 'over_continuous_hours':
      return `${who}${mw.overContinuousHours} (${w.hours} ${mw.hoursSuffix})`;
    case 'over_consecutive_days':
      return `${who}${mw.overConsecutiveDays} (${w.days} ${mw.daysSuffix})`;
    default:
      return '';
  }
}

const lower = (s) => String(s).toLowerCase();

// The window actually worked in a cell: an explicit segment, else the cell window.
function effectiveWindow(assignment, cell) {
  if (assignment.segment_start && assignment.segment_end) {
    return { start: assignment.segment_start, end: assignment.segment_end };
  }
  return cell.window || null;
}

// Do two 'HH:MM'→'HH:MM' windows overlap on the security-day axis?
function windowsOverlap(a, b) {
  const ai = normalize(a.start, a.end);
  const bi = normalize(b.start, b.end);
  for (const [as, ae] of ai) {
    for (const [bs, be] of bi) {
      if (Math.max(as, bs) < Math.min(ae, be)) return true;
    }
  }
  return false;
}

// Longest run of consecutive day indices in a set (e.g. [0,1,2,4] → 3).
function longestConsecutiveRun(days) {
  const sorted = [...new Set(days)].sort((a, b) => a - b);
  let best = 0;
  let run = 0;
  let prev = null;
  for (const d of sorted) {
    run = prev !== null && d === prev + 1 ? run + 1 : 1;
    if (run > best) best = run;
    prev = d;
  }
  return best;
}

// Drop every warning whose `type` is in `muted` (a Set of type keys) from a
// computed warnings object — so a manager can silence one *kind* of warning
// (e.g. "partial_coverage") without losing the others. Returns a new object;
// the input is untouched. Empty/absent `muted` returns the input as-is.
export function filterMutedWarnings(warnings, muted) {
  if (!warnings || !muted || muted.size === 0) return warnings;
  const keep = (list) => list.filter((w) => !muted.has(w.type));
  const prune = (src) => {
    const out = {};
    for (const [key, list] of Object.entries(src || {})) {
      const filtered = keep(list);
      if (filtered.length) out[key] = filtered;
    }
    return out;
  };
  const summary = {};
  for (const [type, count] of Object.entries(warnings.summary || {})) {
    if (type !== 'total' && !muted.has(type)) summary[type] = count;
  }
  return { byCell: prune(warnings.byCell), byGuard: prune(warnings.byGuard), summary };
}

// Ordered jump targets per warning type, for the summary-bar "focus next" nav.
// Given computed `warnings` and the board's position display order, returns
// { type: [cellKey, ...] } sorted by day then row, so repeated clicks on a
// summary chip walk the occurrences top-to-bottom, left-to-right.
//
// The per-type list length matches the summary count: each per-cell occurrence is
// one target, and each per-guard warning contributes ONE representative anchor —
// the earliest-ranked cell it involves. Per-guard warnings with no cell anchor
// (over_consecutive_days) contribute nothing, so their chip stays non-focusable.
export function warnFocusTargets(warnings, positionOrder = []) {
  const rowIndex = new Map((positionOrder || []).map((pid, i) => [pid, i]));
  // A single sortable number: day dominates, row breaks ties; unknown rows sort last.
  const rank = (key) => {
    const [pid, di] = key.split(':');
    return Number(di) * 1e6 + (rowIndex.get(pid) ?? 1e5);
  };
  const targets = {};
  const push = (type, key) => (targets[type] ||= []).push(key);
  for (const [key, list] of Object.entries(warnings?.byCell || {})) {
    for (const w of list) push(w.type, key);
  }
  for (const list of Object.values(warnings?.byGuard || {})) {
    for (const w of list) {
      const cells = w.cells || [];
      if (!cells.length) continue;
      const anchor = cells.reduce((best, k) => (rank(k) < rank(best) ? k : best));
      push(w.type, anchor);
    }
  }
  for (const list of Object.values(targets)) list.sort((a, b) => rank(a) - rank(b));
  return targets;
}

export function computeBoardWarnings({
  board,
  assignmentsByCell = {},
  pool = [],
  policy = WARNING_POLICY,
} = {}) {
  const byCell = {};
  const byGuard = {};
  const poolById = new Map((pool || []).map((g) => [g.id, g]));
  // Per-guard placements, for the cross-cell rules below.
  const guardItems = new Map(); // gid → [{ key, dayIndex, window, positionName, guardName }]

  const pushCell = (key, w) => {
    (byCell[key] ||= []).push(w);
  };
  const pushGuard = (gid, w) => {
    (byGuard[gid] ||= []).push(w);
  };

  // ── Night-shift continuation (pre-pass) ──────────────────────────────────
  // A guard who works a shift ending exactly at the 07:00 security-day anchor on
  // day d may keep working, *continuously*, into day d+1's early morning — one
  // unbroken shift — for up to `maxContinuousMinutes` from that night's start
  // (23:00→07:00 may run on to 11:00; 21:00→07:00 to 09:00). The forms cap
  // availability at 07:00, so that morning placement has no declared coverage and
  // would otherwise look `out_of_availability`. We record the per-guard, per-day
  // continuation ceiling here so the coverage check below can recognise the case
  // and skip that one false warning. The 12h ceiling is still enforced by
  // `over_continuous_hours`, and a real break still trips `insufficient_rest`.
  const contCapByGuardDay = new Map(); // gid → Map<continuationDay, capMinFromAnchor>
  for (const row of board?.rows || []) {
    for (const cell of row.cells) {
      if (!cell.active) continue;
      for (const a of assignmentsByCell[`${row.position_id}:${cell.day_index}`] || []) {
        const win = effectiveWindow(a, cell);
        if (!win) continue;
        const startMin = toMin(win.start);
        // Ends exactly at the anchor (07:00 → 0) and starts later in the security
        // day → a night shift butting up against the boundary.
        if (toMin(win.end) !== 0 || startMin === 0) continue;
        const cap = startMin - (DAY_MINUTES - policy.maxContinuousMinutes);
        const contDay = cell.day_index + 1;
        if (cap <= 0 || contDay > 6) continue;
        let perDay = contCapByGuardDay.get(a.user_id);
        if (!perDay) contCapByGuardDay.set(a.user_id, (perDay = new Map()));
        perDay.set(contDay, Math.max(perDay.get(contDay) || 0, cap));
      }
    }
  }

  // Is this cell window a legitimate continuous continuation of the guard's night
  // shift — starting at the anchor (adjacent, no gap) and ending within the 12h
  // ceiling? Only then is "out of availability" a false alarm to suppress.
  const isNightContinuation = (gid, win, dayIndex) => {
    const cap = contCapByGuardDay.get(gid)?.get(dayIndex);
    if (!cap) return false;
    const ivs = normalize(win.start, win.end);
    return ivs.length === 1 && ivs[0][0] === 0 && ivs[0][1] <= cap;
  };

  for (const row of board?.rows || []) {
    // An event (non-splitting) position has no coverage notion — guards attend
    // the whole window together — so it never raises out-of-availability /
    // partial-coverage warnings.
    const isEvent = !!row.is_event;
    // Fixed-count events (e.g. מועצה = 4) warn when under-staffed. Unlimited
    // events (רענון) carry no count and never do.
    const requiredCount = isEvent ? row.event_required_count : null;
    for (const cell of row.cells) {
      if (!cell.active) continue;
      const key = `${row.position_id}:${cell.day_index}`;
      const assigns = assignmentsByCell[key] || [];
      // A happening fixed-count event day (≥1 guard) short of its required count
      // raises one soft warning — a 0-guard day means the event isn't happening.
      if (requiredCount && assigns.length >= 1 && assigns.length < requiredCount) {
        pushCell(key, {
          type: 'understaffed_event',
          need: requiredCount,
          have: assigns.length,
        });
      }
      // Empty active cells are surfaced by the "ריק" coverage stat, so we don't
      // raise a (duplicate) soft warning for them.
      if (assigns.length === 0) continue;
      for (const a of assigns) {
        const guard = poolById.get(a.user_id);
        const guardName = a.user_full_name || guard?.full_name || '';
        const win = effectiveWindow(a, cell);

        // Coverage vs the guard's availability that day. The guard comes from the
        // pool (everyone assignable submitted availability); if somehow absent we
        // skip availability checks rather than raise a false alarm.
        if (!isEvent && guard && win) {
          const dayWindows = (guard.availability || {})[String(cell.day_index)] || [];
          const cov = coverage(win.start, win.end, dayWindows);
          // A night shift that continues, unbroken and within 12h, into this
          // morning is legitimate even with no declared morning availability —
          // don't flag it as out-of-availability / partial.
          if (cov.state !== 'full' && isNightContinuation(a.user_id, win, cell.day_index)) {
            // intentionally no warning
          } else if (cov.state === 'none') {
            pushCell(key, { type: 'out_of_availability', guardId: a.user_id, guardName });
          } else if (cov.state === 'partial') {
            pushCell(key, {
              type: 'partial_coverage',
              guardId: a.user_id,
              guardName,
              gaps: cov.gaps,
            });
          }
        }

        // Required attribute the guard lacks. Position keys are lowercase
        // ("armed"); guard roles are the upper enum ("ARMED") — compare lowered.
        const held = new Set((a.user_roles || guard?.roles || []).map(lower));
        const missing = (row.required_attributes || []).filter((k) => !held.has(lower(k)));
        if (missing.length) {
          pushCell(key, { type: 'missing_attribute', guardId: a.user_id, guardName, missing });
        }

        if (win) {
          if (!guardItems.has(a.user_id)) guardItems.set(a.user_id, []);
          guardItems.get(a.user_id).push({
            key,
            dayIndex: cell.day_index,
            window: win,
            positionName: row.name,
            guardName,
            band: row.band,
          });
        }
      }
    }
  }

  // Cross-cell rules, per guard.
  for (const [gid, items] of guardItems) {
    const guardName = items[0]?.guardName || '';

    // double_booking — same guard, same day, overlapping windows.
    const byDay = new Map();
    for (const it of items) {
      if (!byDay.has(it.dayIndex)) byDay.set(it.dayIndex, []);
      byDay.get(it.dayIndex).push(it);
    }
    for (const dayItems of byDay.values()) {
      for (let i = 0; i < dayItems.length; i += 1) {
        for (let j = i + 1; j < dayItems.length; j += 1) {
          if (windowsOverlap(dayItems[i].window, dayItems[j].window)) {
            pushCell(dayItems[i].key, {
              type: 'double_booking',
              guardId: gid,
              guardName,
              otherPosition: dayItems[j].positionName,
            });
            pushCell(dayItems[j].key, {
              type: 'double_booking',
              guardId: gid,
              guardName,
              otherPosition: dayItems[i].positionName,
            });
          }
        }
      }
    }

    // already_in_shift — same guard placed in 2+ cells of one shift (band) on one
    // day. The "no repeat in a shift" rule (075). Soft and independent of window
    // overlap, so it also catches a within-shift split (07–11 + 11–15) that
    // double_booking (overlap-based) would miss.
    const byShift = new Map();
    for (const it of items) {
      const sk = `${it.dayIndex}:${it.band}`;
      if (!byShift.has(sk)) byShift.set(sk, []);
      byShift.get(sk).push(it);
    }
    for (const shiftItems of byShift.values()) {
      if (shiftItems.length < 2) continue;
      for (const it of shiftItems) {
        pushCell(it.key, { type: 'already_in_shift', guardId: gid, guardName });
      }
    }

    // Build a week-long timeline of work intervals (absolute minutes from the
    // week's 07:00 anchor) and merge into continuous work blocks, tracking which
    // cells feed each block. The security day already absorbs the midnight
    // rollover, so day d's intervals live in [d*1440, (d+1)*1440].
    const tagged = items
      .flatMap((it) =>
        normalize(it.window.start, it.window.end).map(([s, e]) => ({
          s: it.dayIndex * DAY_MINUTES + s,
          e: it.dayIndex * DAY_MINUTES + e,
          key: it.key,
        })),
      )
      .sort((a, b) => a.s - b.s || a.e - b.e);

    const blocks = [];
    for (const iv of tagged) {
      const last = blocks[blocks.length - 1];
      if (last && iv.s <= last.e) {
        last.e = Math.max(last.e, iv.e);
        last.keys.add(iv.key);
      } else {
        blocks.push({ s: iv.s, e: iv.e, keys: new Set([iv.key]) });
      }
    }

    // over_continuous_hours — a single block longer than the cap.
    for (const b of blocks) {
      if (b.e - b.s > policy.maxContinuousMinutes) {
        pushGuard(gid, {
          type: 'over_continuous_hours',
          guardId: gid,
          guardName,
          hours: (b.e - b.s) / 60,
          cells: [...b.keys],
        });
      }
    }

    // insufficient_rest — gap between two consecutive blocks shorter than the min.
    for (let i = 1; i < blocks.length; i += 1) {
      const gap = blocks[i].s - blocks[i - 1].e;
      if (gap > 0 && gap < policy.restMinutes) {
        pushGuard(gid, {
          type: 'insufficient_rest',
          guardId: gid,
          guardName,
          gapHours: gap / 60,
          cells: [...blocks[i - 1].keys, ...blocks[i].keys],
        });
      }
    }

    // over_consecutive_days — too many consecutive assigned days.
    const run = longestConsecutiveRun(items.map((it) => it.dayIndex));
    if (run > policy.maxConsecutiveDays) {
      pushGuard(gid, { type: 'over_consecutive_days', guardId: gid, guardName, days: run });
    }
  }

  // Summary counts (each per-cell occurrence and each per-guard warning count 1).
  const summary = { total: 0 };
  const bump = (type) => {
    summary[type] = (summary[type] || 0) + 1;
    summary.total += 1;
  };
  for (const list of Object.values(byCell)) for (const w of list) bump(w.type);
  for (const list of Object.values(byGuard)) for (const w of list) bump(w.type);

  return { byCell, byGuard, summary };
}

export default computeBoardWarnings;
