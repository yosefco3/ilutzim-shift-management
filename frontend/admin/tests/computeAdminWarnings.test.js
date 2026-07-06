import { describe, it, expect } from 'vitest';
import { computeAdminWarnings } from '../src/utils/submissionWarnings';

const RULES = {
  min_shifts_per_guard: 5,
  min_nights: 2,
  min_evenings: 2,
  max_consecutive_days: 6,
};

// Week of Sun 2026-06-21 … Sat 2026-06-27.
const WEEK = [
  '2026-06-21', '2026-06-22', '2026-06-23', '2026-06-24',
  '2026-06-25', '2026-06-26', '2026-06-27',
];

/** Build a detail day for the given offset with the listed active shift types. */
function day(offset, ...shiftTypes) {
  return {
    date: WEEK[offset],
    is_available: shiftTypes.length > 0,
    shift_windows: shiftTypes.map((t) => ({ shift_type: t })),
  };
}

const detail = (days) => ({ days });

describe('computeAdminWarnings', () => {
  it('returns no warnings when rules are not loaded yet', () => {
    expect(computeAdminWarnings(detail([day(0, 'morning')]), null)).toEqual([]);
  });

  it('returns no warnings for a missing detail', () => {
    expect(computeAdminWarnings(undefined, RULES)).toEqual([]);
  });

  it('flags min-shifts, min-nights and min-evenings when nearly empty', () => {
    const w = computeAdminWarnings(detail([day(0, 'morning'), day(1, 'morning')]), RULES);
    expect(w).toHaveLength(3);
    expect(w.some((m) => m.includes('משמרות'))).toBe(true);
    expect(w.some((m) => m.includes('לילות'))).toBe(true);
    expect(w.some((m) => m.includes('ערבים'))).toBe(true);
    expect(w.some((m) => m.includes('רצופים'))).toBe(false);
  });

  it('returns no warnings when all thresholds are met', () => {
    const days = [
      day(0, 'night'),
      day(1, 'night'),
      day(2, 'afternoon'),
      day(3, 'afternoon'),
      day(5, 'morning'), // gap at index 4 keeps the consecutive run <= 6; total = 5
    ];
    expect(computeAdminWarnings(detail(days), RULES)).toEqual([]);
  });

  it('warns on 7 consecutive availability days vs max 6', () => {
    const days = WEEK.map((_, i) => day(i, 'morning', 'afternoon', 'night'));
    const w = computeAdminWarnings(detail(days), RULES);
    expect(w.some((m) => m.includes('רצופים'))).toBe(true);
    expect(w.some((m) => m.includes('7'))).toBe(true);
  });

  it('counts afternoon as evening, not as night', () => {
    const days = [
      day(0, 'afternoon'),
      day(1, 'afternoon'),
      day(3, 'morning'),
      day(4, 'morning'),
      day(6, 'morning'),
    ];
    const w = computeAdminWarnings(detail(days), RULES);
    expect(w.some((m) => m.includes('ערבים'))).toBe(false); // evenings satisfied
    expect(w.some((m) => m.includes('לילות'))).toBe(true); // nights still 0
  });

  it('does not count a non-active day (no shift windows) toward the run', () => {
    // 6 consecutive active days, a gap, then one more — longest run is 6, no warning.
    const days = [
      day(0, 'morning'), day(1, 'morning'), day(2, 'morning'),
      day(3, 'morning'), day(4, 'morning'), day(5, 'morning'),
      day(6), // empty
    ];
    const w = computeAdminWarnings(detail(days), RULES);
    expect(w.some((m) => m.includes('רצופים'))).toBe(false);
  });
});
