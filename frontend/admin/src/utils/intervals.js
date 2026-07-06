// Security-day interval math (mirror of backend app/schedule_builder/utils/intervals.py).
// The security day runs 07:00 → 07:00; all math is in minutes-from-07:00 (0..1440).
// Used to colour board cells by a selected guard's availability — instantly,
// client-side, without a round trip per cell.

const DAY_MINUTES = 24 * 60; // 1440
const ANCHOR = 7 * 60; // 07:00

export function toMin(hhmm) {
  const [h, m] = hhmm.split(':').map(Number);
  return (((h * 60 + m - ANCHOR) % DAY_MINUTES) + DAY_MINUTES) % DAY_MINUTES;
}

export function toHHMM(minute) {
  const abs = (((minute + ANCHOR) % DAY_MINUTES) + DAY_MINUTES) % DAY_MINUTES;
  const h = Math.floor(abs / 60);
  const m = abs % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

// A window 'HH:MM'→'HH:MM' as 1–2 linear sub-intervals within [0, 1440].
export function normalize(start, end) {
  const s = toMin(start);
  const e = toMin(end);
  if (s === e) return [[0, DAY_MINUTES]]; // whole day
  if (e > s) return [[s, e]];
  return e === 0 ? [[s, DAY_MINUTES]] : [[s, DAY_MINUTES], [0, e]];
}

export function merge(intervals) {
  if (!intervals.length) return [];
  const ordered = [...intervals].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const out = [ordered[0].slice()];
  for (let i = 1; i < ordered.length; i += 1) {
    const [s, e] = ordered[i];
    const last = out[out.length - 1];
    if (s <= last[1]) last[1] = Math.max(last[1], e);
    else out.push([s, e]);
  }
  return out;
}

function intersect(windowIvs, availIvs) {
  const w = merge(windowIvs);
  const a = merge(availIvs);
  const out = [];
  for (const [ws, we] of w) {
    for (const [as, ae] of a) {
      const lo = Math.max(ws, as);
      const hi = Math.min(we, ae);
      if (lo < hi) out.push([lo, hi]);
    }
  }
  return merge(out);
}

function subtract(windowIvs, availIvs) {
  const w = merge(windowIvs);
  const a = merge(availIvs);
  const out = [];
  for (const [ws, we] of w) {
    let cursor = ws;
    for (const [as, ae] of a) {
      if (ae <= cursor || as >= we) continue;
      if (as > cursor) out.push([cursor, Math.min(as, we)]);
      cursor = Math.max(cursor, ae);
      if (cursor >= we) break;
    }
    if (cursor < we) out.push([cursor, we]);
  }
  return out;
}

const duration = (ivs) => merge(ivs).reduce((sum, [s, e]) => sum + (e - s), 0);

// Build a guard's availability intervals for one day from [{start,end}, …].
function availIntervals(windows) {
  return merge((windows || []).flatMap((w) => normalize(w.start, w.end)));
}

// Classify how a guard's day-availability covers a position window.
// Returns { state: 'full'|'partial'|'none', gaps: [{start,end}, …] }.
export function coverage(windowStart, windowEnd, dayWindows) {
  const win = normalize(windowStart, windowEnd);
  const avail = availIntervals(dayWindows);
  const total = duration(win);
  const covered = duration(intersect(win, avail));
  if (covered === 0) return { state: 'none', gaps: [] };
  if (covered >= total) return { state: 'full', gaps: [] };
  const gaps = subtract(win, avail).map(([s, e]) => ({ start: toHHMM(s), end: toHHMM(e) }));
  return { state: 'partial', gaps };
}

// Coverage of a position window by the UNION of a cell's *assigned* time
// segments — distinct from coverage() above, which measures a single guard's
// *availability*. Both are needed; don't merge them.
//   segments = [{start, end}, …] — one explicit segment per guard. A guard with
//   no explicit segment should be passed by the caller as the whole window.
// Returns { state: 'full'|'partial'|'empty', gaps: [{start, end}, …] }.
export function segmentsCoverage(windowStart, windowEnd, segments) {
  const win = normalize(windowStart, windowEnd);
  const covered = merge((segments || []).flatMap((s) => normalize(s.start, s.end)));
  const total = duration(win);
  const got = duration(intersect(win, covered));
  if (got >= total) return { state: 'full', gaps: [] };
  const gaps = subtract(win, covered).map(([s, e]) => ({ start: toHHMM(s), end: toHHMM(e) }));
  return { state: got === 0 ? 'empty' : 'partial', gaps };
}

// Clip a guard's placement to the part of a position window they are actually
// available for. Given the window and the guard's availability windows that day,
// returns the largest contiguous *available* slice as { start, end } ('HH:MM'),
// or `null` when the guard covers the whole window (assign whole-window, no
// segment) or none of it (assign whole-window; a soft out-of-availability warning
// follows). Works in window-relative offsets, so windows crossing the 07:00
// anchor (e.g. 22:00–06:00) are handled — mirrors autoSplitPoint's approach.
export function availabilityClip(windowStart, windowEnd, dayWindows) {
  const win = normalize(windowStart, windowEnd);
  const winLen = duration(win);
  const wsMin = toMin(windowStart);
  const toOffset = (abs) => (((abs - wsMin) % DAY_MINUTES) + DAY_MINUTES) % DAY_MINUTES;
  const avail = merge((dayWindows || []).flatMap((w) => normalize(w.start, w.end)));
  const pieces = intersect(win, avail);
  if (!pieces.length) return null; // covers nothing → whole window
  const offs = merge(
    pieces.map(([s, e]) => {
      const so = toOffset(s);
      let eo = toOffset(e);
      if (eo <= so) eo = winLen; // end wrapped to/past the window end
      return [so, eo];
    }),
  );
  const covered = offs.reduce((sum, [s, e]) => sum + (e - s), 0);
  if (covered >= winLen) return null; // covers all → whole window, no segment
  let best = offs[0];
  for (const cur of offs) {
    if (cur[1] - cur[0] > best[1] - best[0]) best = cur;
  }
  return {
    start: toHHMM((wsMin + best[0]) % DAY_MINUTES),
    end: toHHMM((wsMin + best[1]) % DAY_MINUTES),
  };
}

// Initial handoff point for tiling a window between guard A (the earlier
// segment) and guard B (the later one). Preference order:
//   1. the end of A's *continuous* availability from the window start;
//   2. the start of B's availability inside the window;
//   3. the window midpoint.
// Locked to 30-minute steps and kept strictly inside the window
// (returns 'HH:MM' on the 07:00 axis). All math is in window-relative minutes,
// so windows that straddle the 07:00 anchor (e.g. 06:00–16:00) are handled.
export function autoSplitPoint(windowStart, windowEnd, aWindows, bWindows) {
  const win = normalize(windowStart, windowEnd);
  const winLen = duration(win);
  // A split needs two pieces of ≥30 min each; a window under 60 min cannot be
  // split without a degenerate or too-short segment (F-5). Return null so the
  // caller places the second guard on the whole window (segment null/null) rather
  // than sending a degenerate segment_start == segment_end the backend now rejects.
  if (winLen < 60) return null;
  const wsMin = toMin(windowStart);
  const toOffset = (abs) => (((abs - wsMin) % DAY_MINUTES) + DAY_MINUTES) % DAY_MINUTES;
  // A guard's covered offsets within the window, as [from,to] from window start.
  const coveredOffsets = (windows) => {
    const avail = merge((windows || []).flatMap((w) => normalize(w.start, w.end)));
    const pieces = intersect(win, avail);
    return merge(
      pieces.map(([s, e]) => {
        const so = toOffset(s);
        let eo = toOffset(e);
        if (eo <= so) eo = winLen; // end wrapped to/past the window end
        return [so, eo];
      }),
    );
  };

  const aOff = coveredOffsets(aWindows);
  let split;
  if (aOff.length && aOff[0][0] === 0) {
    split = aOff[0][1]; // A covers from the start → hand off where A stops
  } else {
    const bOff = coveredOffsets(bWindows);
    const bStart = bOff.find(([s]) => s > 0);
    split = bStart ? bStart[0] : winLen / 2;
  }
  split = Math.round(split / 30) * 30;
  split = Math.max(30, Math.min(winLen - 30, split));
  return toHHMM((wsMin + split) % DAY_MINUTES);
}
