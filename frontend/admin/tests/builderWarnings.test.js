import { describe, it, expect } from 'vitest';
import {
  computeBoardWarnings,
  filterMutedWarnings,
  warnFocusTargets,
  WARNING_POLICY,
} from '../src/utils/warnings';

// ---- builders -------------------------------------------------------------

// One position row. `windows` maps day_index → {start,end}; absent days are
// inactive. `required` are required-attribute keys.
function row(positionId, name, windows, required = [], is_event = false,
            event_required_count = null) {
  const cells = Array.from({ length: 7 }, (_, d) => {
    const w = windows[d];
    return { day_index: d, active: !!w, window: w || null, is_override: false };
  });
  return {
    position_id: positionId,
    name,
    band: 'morning',
    canonical_window: windows[0] || null,
    required_attributes: required,
    is_event,
    event_required_count,
    active_day_count: cells.filter((c) => c.active).length,
    cells,
  };
}

function guard(id, name, availability = {}, roles = []) {
  return { id, full_name: name, roles, availability, remaining_hours: 10 };
}

function assignment(positionId, dayIndex, g) {
  return {
    id: `a-${positionId}-${dayIndex}`,
    position_id: positionId,
    day_index: dayIndex,
    user_id: g.id,
    user_full_name: g.full_name,
    user_roles: g.roles,
  };
}

function byCellFrom(assignments) {
  const map = {};
  for (const a of assignments) {
    (map[`${a.position_id}:${a.day_index}`] ||= []).push(a);
  }
  return map;
}

const M = { start: '07:00', end: '15:00' }; // a morning window

// ---- tests ----------------------------------------------------------------

describe('computeBoardWarnings — per-cell', () => {
  it('flags a guard assigned outside their availability that day', () => {
    const g = guard('g1', 'דנה', { 0: [] }); // submitted, but not available Sunday
    const board = { rows: [row('p1', 'שער', { 0: M })] };
    const { byCell, summary } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('p1', 0, g)]),
      pool: [g],
    });
    expect(byCell['p1:0'].map((w) => w.type)).toContain('out_of_availability');
    expect(summary.out_of_availability).toBe(1);
  });

  it('does NOT flag availability warnings on an event (non-splitting) position', () => {
    const g = guard('g1', 'דנה', { 0: [] }); // not available Sunday
    const board = { rows: [row('ev1', 'רענון', { 0: M }, [], true)] };
    const { byCell, summary } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('ev1', 0, g)]),
      pool: [g],
    });
    expect(byCell['ev1:0']).toBeUndefined();
    expect(summary.out_of_availability).toBeUndefined();
    expect(summary.partial_coverage).toBeUndefined();
  });

  it('flags a fixed-count event short of its required participants', () => {
    const g1 = guard('g1', 'דנה', { 0: [M] });
    const g2 = guard('g2', 'אבי', { 0: [M] });
    // מועצה needs 4; only 2 assigned → understaffed_event (have 2 / need 4).
    const board = { rows: [row('ev1', 'מועצה', { 0: M }, [], true, 4)] };
    const { byCell, summary } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([
        assignment('ev1', 0, g1),
        assignment('ev1', 0, g2),
      ]),
      pool: [g1, g2],
    });
    const w = byCell['ev1:0'].find((x) => x.type === 'understaffed_event');
    expect(w).toBeTruthy();
    expect(w.have).toBe(2);
    expect(w.need).toBe(4);
    expect(summary.understaffed_event).toBe(1);
  });

  it('does NOT flag a fixed-count event that is fully staffed', () => {
    const g1 = guard('g1', 'דנה', { 0: [M] });
    const g2 = guard('g2', 'אבי', { 0: [M] });
    const board = { rows: [row('ev1', 'מועצה', { 0: M }, [], true, 2)] };
    const { byCell } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([
        assignment('ev1', 0, g1),
        assignment('ev1', 0, g2),
      ]),
      pool: [g1, g2],
    });
    expect(byCell['ev1:0']).toBeUndefined();
  });

  it('does NOT flag an unlimited event (no required count)', () => {
    const g1 = guard('g1', 'דנה', { 0: [M] });
    const board = { rows: [row('ev1', 'רענון', { 0: M }, [], true, null)] };
    const { byCell } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('ev1', 0, g1)]),
      pool: [g1],
    });
    expect(byCell['ev1:0']).toBeUndefined();
  });

  it('flags partial coverage with the uncovered gap', () => {
    const g = guard('g1', 'דנה', { 0: [{ start: '07:00', end: '12:00' }] });
    const board = { rows: [row('p1', 'שער', { 0: M })] }; // needs 07:00–15:00
    const { byCell } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('p1', 0, g)]),
      pool: [g],
    });
    const w = byCell['p1:0'].find((x) => x.type === 'partial_coverage');
    expect(w).toBeTruthy();
    expect(w.gaps).toEqual([{ start: '12:00', end: '15:00' }]);
  });

  it('flags a missing required attribute (case-insensitive role match)', () => {
    const g = guard('g1', 'דנה', { 0: [M] }, ['UNARMED']);
    const board = { rows: [row('p1', 'שער חמוש', { 0: M }, ['armed'])] };
    const { byCell, summary } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('p1', 0, g)]),
      pool: [g],
    });
    const w = byCell['p1:0'].find((x) => x.type === 'missing_attribute');
    expect(w.missing).toEqual(['armed']);
    expect(summary.missing_attribute).toBe(1);
  });

  it('does NOT flag a held attribute (ARMED satisfies armed)', () => {
    const g = guard('g1', 'דנה', { 0: [M] }, ['ARMED']);
    const board = { rows: [row('p1', 'שער חמוש', { 0: M }, ['armed'])] };
    const { byCell } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('p1', 0, g)]),
      pool: [g],
    });
    expect((byCell['p1:0'] || []).some((w) => w.type === 'missing_attribute')).toBe(false);
  });

  it('does NOT warn on an empty active cell (surfaced by the "ריק" stat instead)', () => {
    const board = { rows: [row('p1', 'שער', { 0: M })] };
    const { byCell, summary } = computeBoardWarnings({ board, assignmentsByCell: {}, pool: [] });
    expect(byCell['p1:0']).toBeUndefined();
    expect(summary.empty_position).toBeUndefined();
  });

  it('flags overlapping same-day assignments as a double booking on both cells', () => {
    const g = guard('g1', 'דנה', { 0: [{ start: '07:00', end: '17:00' }] });
    const board = {
      rows: [
        row('p1', 'שער א', { 0: { start: '07:00', end: '15:00' } }),
        row('p2', 'שער ב', { 0: { start: '14:00', end: '16:00' } }),
      ],
    };
    const { byCell, summary } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('p1', 0, g), assignment('p2', 0, g)]),
      pool: [g],
    });
    expect(byCell['p1:0'].some((w) => w.type === 'double_booking')).toBe(true);
    expect(byCell['p2:0'].some((w) => w.type === 'double_booking')).toBe(true);
    expect(summary.double_booking).toBe(2); // one per affected cell
  });

  it('flags a double booking between a splitting position and an overlapping event', () => {
    const g = guard('g1', 'דנה', { 0: [{ start: '07:00', end: '15:00' }] });
    const board = {
      rows: [
        row('p1', 'ארנונה', { 0: { start: '07:00', end: '15:00' } }),          // normal
        row('ev1', 'רענון', { 0: { start: '07:00', end: '15:00' } }, [], true), // event
      ],
    };
    const { byCell } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('p1', 0, g), assignment('ev1', 0, g)]),
      pool: [g],
    });
    expect(byCell['p1:0'].some((w) => w.type === 'double_booking')).toBe(true);
    expect(byCell['ev1:0'].some((w) => w.type === 'double_booking')).toBe(true);
  });

  it('flags a double booking between two overlapping events with the same guard', () => {
    const g = guard('g1', 'דנה', { 0: [{ start: '07:00', end: '15:00' }] });
    const board = {
      rows: [
        row('ev1', 'רענון', { 0: { start: '07:00', end: '12:00' } }, [], true),
        row('ev2', 'ישיבת מועצה', { 0: { start: '10:00', end: '15:00' } }, [], true),
      ],
    };
    const { byCell } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('ev1', 0, g), assignment('ev2', 0, g)]),
      pool: [g],
    });
    expect(byCell['ev1:0'].some((w) => w.type === 'double_booking')).toBe(true);
    expect(byCell['ev2:0'].some((w) => w.type === 'double_booking')).toBe(true);
  });
});

describe('computeBoardWarnings — already_in_shift (075)', () => {
  // row() hardcodes band 'morning'; override the band for cross-shift cases.
  const withBand = (r, band) => ({ ...r, band });

  it('flags the same guard placed twice in one shift+day, even without overlap', () => {
    // Two morning positions, non-overlapping windows (07–11, 11–15) → not a
    // double_booking, but still a repeat within the morning shift.
    const g = guard('g1', 'דנה', { 0: [{ start: '07:00', end: '15:00' }] });
    const board = {
      rows: [
        row('p1', 'שער א', { 0: { start: '07:00', end: '11:00' } }),
        row('p2', 'שער ב', { 0: { start: '11:00', end: '15:00' } }),
      ],
    };
    const { byCell, summary } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('p1', 0, g), assignment('p2', 0, g)]),
      pool: [g],
    });
    expect(byCell['p1:0'].some((w) => w.type === 'already_in_shift')).toBe(true);
    expect(byCell['p2:0'].some((w) => w.type === 'already_in_shift')).toBe(true);
    expect(byCell['p1:0'].some((w) => w.type === 'double_booking')).toBe(false);
    expect(summary.already_in_shift).toBe(2); // one per affected cell
  });

  it('does NOT flag the same guard in a different shift the same day', () => {
    const g = guard('g1', 'דנה', {
      0: [{ start: '07:00', end: '23:00' }],
    });
    const board = {
      rows: [
        withBand(row('p1', 'בוקר', { 0: { start: '07:00', end: '15:00' } }), 'morning'),
        withBand(row('p2', 'ערב', { 0: { start: '15:00', end: '23:00' } }), 'evening'),
      ],
    };
    const { byCell } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('p1', 0, g), assignment('p2', 0, g)]),
      pool: [g],
    });
    expect((byCell['p1:0'] || []).some((w) => w.type === 'already_in_shift')).toBe(false);
    expect((byCell['p2:0'] || []).some((w) => w.type === 'already_in_shift')).toBe(false);
  });

  it('does NOT flag the same shift on different days', () => {
    const g = guard('g1', 'דנה', {
      0: [{ start: '07:00', end: '15:00' }],
      1: [{ start: '07:00', end: '15:00' }],
    });
    const board = { rows: [row('p1', 'שער', { 0: M, 1: M })] };
    const { byCell } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('p1', 0, g), assignment('p1', 1, g)]),
      pool: [g],
    });
    expect((byCell['p1:0'] || []).some((w) => w.type === 'already_in_shift')).toBe(false);
    expect((byCell['p1:1'] || []).some((w) => w.type === 'already_in_shift')).toBe(false);
  });
});

describe('computeBoardWarnings — per-guard policy', () => {
  it('flags less than 8h rest between two work blocks the same day', () => {
    // 07:00–15:00 then 20:00–23:00 → 5h gap < 8h.
    const g = guard('g1', 'דנה', { 0: [{ start: '07:00', end: '23:00' }] });
    const board = {
      rows: [
        row('p1', 'בוקר', { 0: { start: '07:00', end: '15:00' } }),
        row('p2', 'ערב', { 0: { start: '20:00', end: '23:00' } }),
      ],
    };
    const { byGuard, summary } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('p1', 0, g), assignment('p2', 0, g)]),
      pool: [g],
    });
    const w = byGuard.g1.find((x) => x.type === 'insufficient_rest');
    expect(w.gapHours).toBe(5);
    expect(summary.insufficient_rest).toBe(1);
  });

  it('flags a continuous block longer than 12h', () => {
    const g = guard('g1', 'דנה', { 0: [{ start: '07:00', end: '23:00' }] });
    const board = { rows: [row('p1', 'משמרת ארוכה', { 0: { start: '07:00', end: '22:00' } })] };
    const { byGuard } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('p1', 0, g)]),
      pool: [g],
    });
    const w = byGuard.g1.find((x) => x.type === 'over_continuous_hours');
    expect(w.hours).toBe(15);
  });

  it('flags more than 6 consecutive assigned days', () => {
    const g = guard('g1', 'דנה', {});
    const windows = {};
    for (let d = 0; d < 7; d += 1) windows[d] = M;
    const board = { rows: [row('p1', 'שער', windows)] };
    const assigns = Array.from({ length: 7 }, (_, d) => assignment('p1', d, g));
    const { byGuard, summary } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom(assigns),
      pool: [g],
    });
    const w = byGuard.g1.find((x) => x.type === 'over_consecutive_days');
    expect(w.days).toBe(7);
    expect(summary.over_consecutive_days).toBe(1);
  });

  it('produces no warnings for a clean, fully-covered, attributed assignment', () => {
    const g = guard('g1', 'דנה', { 0: [M] }, ['armed']);
    const board = { rows: [row('p1', 'שער חמוש', { 0: M }, ['armed'])] };
    const { byCell, byGuard, summary } = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('p1', 0, g)]),
      pool: [g],
    });
    expect(byCell['p1:0']).toBeUndefined();
    expect(byGuard.g1).toBeUndefined();
    expect(summary.total).toBe(0);
  });

  it('exposes the locked policy thresholds', () => {
    expect(WARNING_POLICY).toEqual({
      restMinutes: 480,
      maxConsecutiveDays: 6,
      maxContinuousMinutes: 720,
    });
  });
});

describe('filterMutedWarnings', () => {
  const warnings = {
    byCell: {
      'p1:0': [
        { type: 'partial_coverage', guardId: 'g1' },
        { type: 'missing_attribute', guardId: 'g1' },
      ],
      'p2:0': [{ type: 'partial_coverage', guardId: 'g2' }],
    },
    byGuard: {
      g1: [{ type: 'insufficient_rest', guardId: 'g1' }],
    },
    summary: {
      partial_coverage: 2,
      missing_attribute: 1,
      insufficient_rest: 1,
      total: 4,
    },
  };

  it('returns the input untouched when nothing is muted', () => {
    expect(filterMutedWarnings(warnings, new Set())).toBe(warnings);
  });

  it('drops only the muted type across byCell, byGuard and summary', () => {
    const out = filterMutedWarnings(warnings, new Set(['partial_coverage']));
    // The cell that had ONLY partial_coverage disappears entirely.
    expect(out.byCell['p2:0']).toBeUndefined();
    // The cell with a second warning keeps it.
    expect(out.byCell['p1:0'].map((w) => w.type)).toEqual(['missing_attribute']);
    // Untouched types survive.
    expect(out.byGuard.g1).toHaveLength(1);
    expect(out.summary.partial_coverage).toBeUndefined();
    expect(out.summary.missing_attribute).toBe(1);
  });

  it('can mute several types at once', () => {
    const out = filterMutedWarnings(
      warnings,
      new Set(['partial_coverage', 'missing_attribute', 'insufficient_rest']),
    );
    expect(out.byCell).toEqual({});
    expect(out.byGuard).toEqual({});
    expect(out.summary).toEqual({});
  });
});

// ---- night-shift continuation ---------------------------------------------
// A shift that ends exactly at the 07:00 security-day anchor may continue,
// unbroken, into the next morning as ONE shift, up to 12h from the night start
// (23:00→07:00 may run on to 11:00; 21:00→07:00 to 09:00). The forms cap
// availability at 07:00, so such a morning placement has no declared coverage —
// but it is legitimate and must not be flagged. The 12h ceiling is still
// enforced by over_continuous_hours; a real break still trips insufficient_rest.
describe('computeBoardWarnings — night-shift continuation', () => {
  const nightRow = (id, windows) => {
    const r = row(id, 'לילה', windows);
    r.band = 'night';
    return r;
  };

  it('23:00→07:00 then morning 07:00→11:00 is legal — NO warnings', () => {
    const g = guard('g1', 'דני', { 0: [{ start: '23:00', end: '07:00' }] });
    const board = {
      rows: [nightRow('night', { 0: { start: '23:00', end: '07:00' } }), row('morn', 'בוקר', { 1: { start: '07:00', end: '11:00' } })],
    };
    const out = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('night', 0, g), assignment('morn', 1, g)]),
      pool: [g],
    });
    expect(out.byCell).toEqual({});
    expect(out.byGuard).toEqual({});
    expect(out.summary.total || 0).toBe(0);
  });

  it('21:00→07:00 then morning 07:00→09:00 is legal — NO warnings (9h ceiling)', () => {
    const g = guard('g1', 'דני', { 0: [{ start: '21:00', end: '07:00' }] });
    const board = {
      rows: [nightRow('night', { 0: { start: '21:00', end: '07:00' } }), row('morn', 'בוקר', { 1: { start: '07:00', end: '09:00' } })],
    };
    const out = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('night', 0, g), assignment('morn', 1, g)]),
      pool: [g],
    });
    expect(out.byCell).toEqual({});
    expect(out.byGuard).toEqual({});
  });

  it('continuation PAST 12h (23:00→07:00 then morning 07:00→15:00) still warns', () => {
    const g = guard('g1', 'דני', { 0: [{ start: '23:00', end: '07:00' }] });
    const board = {
      rows: [nightRow('night', { 0: { start: '23:00', end: '07:00' } }), row('morn', 'בוקר', { 1: { start: '07:00', end: '15:00' } })],
    };
    const out = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('night', 0, g), assignment('morn', 1, g)]),
      pool: [g],
    });
    expect(out.byCell['morn:1'].map((w) => w.type)).toContain('out_of_availability');
    expect(out.byGuard['g1'].map((w) => w.type)).toContain('over_continuous_hours');
  });

  it('morning 07:00→11:00 with NO preceding night still warns (no continuation)', () => {
    const g = guard('g1', 'דני', { 1: [] });
    const board = { rows: [row('morn', 'בוקר', { 1: { start: '07:00', end: '11:00' } })] };
    const out = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('morn', 1, g)]),
      pool: [g],
    });
    expect(out.byCell['morn:1'].map((w) => w.type)).toContain('out_of_availability');
  });

  it('morning that does NOT start at the anchor (08:00→11:00) is not a continuation', () => {
    const g = guard('g1', 'דני', { 0: [{ start: '23:00', end: '07:00' }] });
    const board = {
      rows: [nightRow('night', { 0: { start: '23:00', end: '07:00' } }), row('morn', 'בוקר', { 1: { start: '08:00', end: '11:00' } })],
    };
    const out = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('night', 0, g), assignment('morn', 1, g)]),
      pool: [g],
    });
    expect(out.byCell['morn:1'].map((w) => w.type)).toContain('out_of_availability');
    expect(out.byGuard['g1'].map((w) => w.type)).toContain('insufficient_rest');
  });
});

describe('warnFocusTargets', () => {
  it('returns {} for empty / missing input', () => {
    expect(warnFocusTargets(null)).toEqual({});
    expect(warnFocusTargets({ byCell: {}, byGuard: {}, summary: {} })).toEqual({});
  });

  it('lists one target per per-cell occurrence, ordered by day then row', () => {
    // Two out-of-availability guards: p2 on day 0, p1 on day 2. Result ordered by
    // day first (0 before 2), then row order (p1 before p2) within a day.
    const g = guard('g1', 'דנה', { 0: [], 2: [] }); // available neither day
    const board = { rows: [row('p1', 'שער', { 2: M }), row('p2', 'לובי', { 0: M })] };
    const warnings = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('p1', 2, g), assignment('p2', 0, g)]),
      pool: [g],
    });
    const targets = warnFocusTargets(warnings, ['p1', 'p2']);
    expect(targets.out_of_availability).toEqual(['p2:0', 'p1:2']);
    expect(targets.out_of_availability.length).toBe(warnings.summary.out_of_availability);
  });

  it('within a day, orders per-cell occurrences by row display order', () => {
    const g1 = guard('g1', 'דנה', { 0: [] });
    const g2 = guard('g2', 'רון', { 0: [] });
    const board = { rows: [row('p1', 'שער', { 0: M }), row('p2', 'לובי', { 0: M })] };
    const warnings = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('p2', 0, g2), assignment('p1', 0, g1)]),
      pool: [g1, g2],
    });
    // p1 declared before p2 → p1:0 comes first even though p2 was assigned first.
    expect(warnFocusTargets(warnings, ['p1', 'p2']).out_of_availability).toEqual([
      'p1:0',
      'p2:0',
    ]);
  });

  it('gives a per-guard warning one representative anchor (matches summary count)', () => {
    // 07:00–15:00 then 20:00–23:00 → one insufficient_rest warning spanning both cells.
    const g = guard('g1', 'דנה', { 0: [{ start: '07:00', end: '23:00' }] });
    const board = {
      rows: [
        row('p1', 'בוקר', { 0: { start: '07:00', end: '15:00' } }),
        row('p2', 'ערב', { 0: { start: '20:00', end: '23:00' } }),
      ],
    };
    const warnings = computeBoardWarnings({
      board,
      assignmentsByCell: byCellFrom([assignment('p1', 0, g), assignment('p2', 0, g)]),
      pool: [g],
    });
    const targets = warnFocusTargets(warnings, ['p1', 'p2']);
    // One target, matching the single summary occurrence, anchored on the earlier cell.
    expect(targets.insufficient_rest).toEqual(['p1:0']);
    expect(targets.insufficient_rest.length).toBe(warnings.summary.insufficient_rest);
  });

  it('omits per-guard warnings that carry no cell anchor (over_consecutive_days)', () => {
    const g = guard('g1', 'דנה', {});
    const windows = {};
    for (let d = 0; d < 7; d += 1) windows[d] = M;
    const board = { rows: [row('p1', 'שער', windows)] };
    const assigns = Array.from({ length: 7 }, (_, d) => assignment('p1', d, g));
    const warnings = computeBoardWarnings({ board, assignmentsByCell: byCellFrom(assigns), pool: [g] });
    expect(warnings.summary.over_consecutive_days).toBe(1); // present in the summary…
    expect(warnFocusTargets(warnings, ['p1']).over_consecutive_days).toBeUndefined(); // …but not focusable
  });
});
