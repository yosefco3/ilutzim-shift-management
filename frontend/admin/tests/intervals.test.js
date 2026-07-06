import { describe, it, expect } from 'vitest';
import {
  toMin,
  toHHMM,
  normalize,
  merge,
  coverage,
  segmentsCoverage,
  autoSplitPoint,
  availabilityClip,
} from '../src/utils/intervals';

describe('intervals (security-day math)', () => {
  it('maps the 07:00 anchor to 0 and wraps before it', () => {
    expect(toMin('07:00')).toBe(0);
    expect(toMin('16:30')).toBe(570);
    expect(toMin('01:00')).toBe(18 * 60);
  });

  it('round-trips minutes back to HH:MM', () => {
    expect(toHHMM(0)).toBe('07:00');
    expect(toHHMM(1440)).toBe('07:00');
    expect(toHHMM(960)).toBe('23:00');
  });

  it('normalizes a night window that ends at the anchor to one piece', () => {
    expect(normalize('23:00', '07:00')).toEqual([[960, 1440]]);
  });

  it('merges overlapping windows (union, not sum)', () => {
    const ivs = [...normalize('07:00', '16:30'), ...normalize('15:00', '19:00')];
    expect(merge(ivs)).toEqual([[0, 12 * 60]]); // 07:00–19:00
  });

  describe('coverage', () => {
    it('full when the window is inside availability', () => {
      const cov = coverage('07:00', '15:00', [{ start: '07:00', end: '19:00' }]);
      expect(cov.state).toBe('full');
    });

    it('none when there is no overlap', () => {
      const cov = coverage('19:00', '07:00', [{ start: '07:00', end: '12:00' }]);
      expect(cov.state).toBe('none');
    });

    it('partial reports the uncovered gap', () => {
      // Position 19:00–07:00; guard available 19:00–01:00 → gap 01:00–07:00.
      const cov = coverage('19:00', '07:00', [{ start: '19:00', end: '01:00' }]);
      expect(cov.state).toBe('partial');
      expect(cov.gaps).toEqual([{ start: '01:00', end: '07:00' }]);
    });
  });

  describe('segmentsCoverage (assigned segments vs window)', () => {
    it('full when two segments tile the whole window', () => {
      const cov = segmentsCoverage('06:00', '16:00', [
        { start: '06:00', end: '14:00' },
        { start: '14:00', end: '16:00' },
      ]);
      expect(cov.state).toBe('full');
      expect(cov.gaps).toEqual([]);
    });

    it('partial with a single early segment, gap at the tail', () => {
      const cov = segmentsCoverage('06:00', '16:00', [{ start: '06:00', end: '14:00' }]);
      expect(cov.state).toBe('partial');
      expect(cov.gaps).toEqual([{ start: '14:00', end: '16:00' }]);
    });

    it('full across midnight when two night segments tile the window', () => {
      const cov = segmentsCoverage('19:00', '07:00', [
        { start: '19:00', end: '01:00' },
        { start: '01:00', end: '07:00' },
      ]);
      expect(cov.state).toBe('full');
    });

    it('empty with no segments', () => {
      const cov = segmentsCoverage('06:00', '16:00', []);
      expect(cov.state).toBe('empty');
    });
  });

  describe('autoSplitPoint (initial tiling handoff)', () => {
    it('hands off where guard A stops covering from the window start', () => {
      // Window 06:00–16:00 (straddles the 07:00 anchor); A available 06:00–14:00.
      const split = autoSplitPoint('06:00', '16:00', [{ start: '06:00', end: '14:00' }], [
        { start: '14:00', end: '16:00' },
      ]);
      expect(split).toBe('14:00');
    });

    it('rounds the handoff to the nearest 30 minutes', () => {
      // A covers to 13:40 → rounds to 13:30.
      const split = autoSplitPoint('06:00', '16:00', [{ start: '06:00', end: '13:40' }], []);
      expect(split).toBe('13:30');
    });

    it('falls back to guard B start when A is absent at the window start', () => {
      const split = autoSplitPoint('06:00', '16:00', [], [{ start: '13:00', end: '16:00' }]);
      expect(split).toBe('13:00');
    });

    it('keeps the split strictly inside the window (clamped)', () => {
      // A covers the whole window → can't hand off at the very end.
      const split = autoSplitPoint('06:00', '16:00', [{ start: '06:00', end: '16:00' }], []);
      expect(split).toBe('15:30');
    });

    it('falls back to the window midpoint when neither guard helps', () => {
      const split = autoSplitPoint('06:00', '16:00', [], []);
      expect(split).toBe('11:00'); // 06:00 + 5h
    });

    it('returns null for a window under 60 min (not splittable, F-5)', () => {
      // A 45-min window can't yield two ≥30-min pieces.
      expect(autoSplitPoint('07:00', '07:45', [], [])).toBeNull();
      // Exactly 30 min → also not splittable.
      expect(autoSplitPoint('07:00', '07:30', [], [])).toBeNull();
    });

    it('still splits a window of exactly 60 min', () => {
      // 07:00–08:00 → handoff at 07:30 (two 30-min pieces).
      expect(autoSplitPoint('07:00', '08:00', [], [])).toBe('07:30');
    });
  });

  describe('availabilityClip (clip a placement to declared availability)', () => {
    it('clips to the available tail, gap at the head (the שוהם case)', () => {
      // Window 07:00–10:00; guard available only 08:00–15:00 → covers 08:00–10:00.
      const seg = availabilityClip('07:00', '10:00', [{ start: '08:00', end: '15:00' }]);
      expect(seg).toEqual({ start: '08:00', end: '10:00' });
    });

    it('clips to the available head, gap at the tail', () => {
      const seg = availabilityClip('07:00', '15:00', [{ start: '07:00', end: '12:00' }]);
      expect(seg).toEqual({ start: '07:00', end: '12:00' });
    });

    it('returns null when availability covers the whole window (no segment)', () => {
      expect(availabilityClip('07:00', '15:00', [{ start: '07:00', end: '19:00' }])).toBeNull();
    });

    it('returns null when the guard is unavailable for the window (whole-window)', () => {
      expect(availabilityClip('07:00', '15:00', [{ start: '20:00', end: '23:00' }])).toBeNull();
    });

    it('picks the largest contiguous slice when availability is fragmented', () => {
      // Window 07:00–13:00; available 07:00–08:00 (1h) and 09:00–13:00 (4h) →
      // the larger 09:00–13:00 slice wins.
      const seg = availabilityClip('07:00', '13:00', [
        { start: '07:00', end: '08:00' },
        { start: '09:00', end: '13:00' },
      ]);
      expect(seg).toEqual({ start: '09:00', end: '13:00' });
    });

    it('handles a night window that crosses the 07:00 anchor', () => {
      // Window 22:00–06:00; available only 22:00–02:00 → clips to that head.
      const seg = availabilityClip('22:00', '06:00', [{ start: '22:00', end: '02:00' }]);
      expect(seg).toEqual({ start: '22:00', end: '02:00' });
    });
  });
});
