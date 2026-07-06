import { describe, it, expect } from 'vitest';
import { computeWarnings } from '../src/hooks/useSubmission';

const RULES = {
  min_shifts_per_guard: 5,
  min_nights: 2,
  min_evenings: 2,
  max_consecutive_days: 6,
};

/** Build a day with the given active shift types (e.g. ['morning','night']). */
function day(index, ...active) {
  const shifts = {
    morning: { active: false },
    afternoon: { active: false },
    night: { active: false },
  };
  for (const t of active) shifts[t].active = true;
  return { day_index: index, blocked: false, shifts };
}

describe('computeWarnings', () => {
  it('returns no warnings when rules are not loaded yet', () => {
    expect(computeWarnings([day(0, 'morning')], null)).toEqual([]);
  });

  it('flags every rule when the form is nearly empty', () => {
    const days = [day(0, 'morning'), day(1, 'morning')]; // 2 shifts, 0 nights, 0 evenings
    const w = computeWarnings(days, RULES);
    expect(w).toHaveLength(3); // min shifts + min nights + min evenings (not consecutive)
    expect(w.some((m) => m.includes('משמרות'))).toBe(true);
    expect(w.some((m) => m.includes('לילות'))).toBe(true);
    expect(w.some((m) => m.includes('ערבים'))).toBe(true);
  });

  it('returns no warnings when all thresholds are met', () => {
    const days = [
      day(0, 'night'),
      day(1, 'night'),
      day(2, 'afternoon'),
      day(3, 'afternoon'),
      day(5, 'morning'), // gap at 4 keeps consecutive run <= 6; total = 5 shifts
    ];
    expect(computeWarnings(days, RULES)).toEqual([]);
  });

  it('warns on 7 consecutive availability days vs max 6', () => {
    const days = Array.from({ length: 7 }, (_, i) =>
      day(i, 'morning', 'night', 'afternoon'),
    );
    const w = computeWarnings(days, RULES);
    expect(w.some((m) => m.includes('רצופים'))).toBe(true);
    expect(w.some((m) => m.includes('7'))).toBe(true);
  });

  it('counts afternoon as evening, not as night', () => {
    // 2 evenings (afternoon), 0 nights, plus padding to satisfy min shifts
    const days = [
      day(0, 'afternoon'),
      day(1, 'afternoon'),
      day(3, 'morning'),
      day(4, 'morning'),
      day(6, 'morning'),
    ];
    const w = computeWarnings(days, RULES);
    expect(w.some((m) => m.includes('ערבים'))).toBe(false); // evenings satisfied
    expect(w.some((m) => m.includes('לילות'))).toBe(true); // nights still 0
  });
});
