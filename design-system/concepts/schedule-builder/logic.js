// Pure scheduling helpers for the schedule-builder concept. No React here.
window.SBLogic = (function () {
  // "HH:MM" -> minutes from midnight.
  function toMin(hhmm) {
    const [h, m] = hhmm.split(':').map(Number);
    return h * 60 + m;
  }
  // "HH:MM-HH:MM" -> {s, e} in minutes; night windows (end<=start) wrap +24h.
  function win(range) {
    const [a, b] = range.split('-');
    let s = toMin(a), e = toMin(b);
    if (e <= s) e += 24 * 60;
    return { s, e };
  }
  function len(range) { const w = win(range); return (w.e - w.s) / 60; }

  // Overlap classification of a guard's day-window against a position window.
  // Returns 'full' (covers whole position), 'partial', or 'none'.
  function coverage(guardRange, posRange) {
    if (!guardRange) return 'none';
    const g = win(guardRange), p = win(posRange);
    // align possible midnight-wrap: also test guard shifted +24h
    const variants = [g, { s: g.s + 1440, e: g.e + 1440 }, { s: g.s - 1440, e: g.e - 1440 }];
    let best = 'none';
    for (const gv of variants) {
      const lo = Math.max(gv.s, p.s), hi = Math.min(gv.e, p.e);
      const ov = hi - lo;
      if (ov <= 0) continue;
      if (gv.s <= p.s && gv.e >= p.e) return 'full';
      if (ov > 0) best = 'partial';
    }
    return best;
  }

  function posActive(pos, day) {
    return !pos.activeDays || pos.activeDays.includes(day);
  }

  // Total available hours in the week (sum of daily windows).
  function weeklyBudget(guard) {
    return Object.values(guard.avail).reduce((sum, r) => sum + len(r), 0);
  }

  // Hours assigned to a guard across all current assignments.
  function assignedHours(guardId, assignments, allPositions) {
    let h = 0;
    for (const key in assignments) {
      if (assignments[key] !== guardId) continue;
      const posId = key.split('@')[0];
      const pos = allPositions.find((p) => p.id === posId);
      if (pos) h += len(pos.hours);
    }
    return h;
  }

  // Compute soft (non-blocking) warnings for assigning guard to (pos, day).
  function warnings(guard, pos, day, assignments, allPositions) {
    const out = [];
    const cov = coverage(guard.avail[day], pos.hours);
    if (cov === 'none') out.push({ type: 'avail', text: 'מחוץ לזמינות שדיווח' });
    else if (cov === 'partial') out.push({ type: 'partial', text: 'מכסה רק חלק מהשעות' });

    for (const req of pos.requires) {
      if (!guard.attrs.includes(req)) out.push({ type: 'attr', text: 'חסר: ' + window.SB.ATTRS[req] });
    }

    // double-booking: same guard assigned elsewhere same day with overlapping hours
    for (const key in assignments) {
      if (assignments[key] !== guard.id) continue;
      const [otherPosId, d] = key.split('@');
      if (Number(d) !== day || otherPosId === pos.id) continue;
      const other = allPositions.find((p) => p.id === otherPosId);
      if (!other) continue;
      const a = win(pos.hours), b = win(other.hours);
      if (Math.max(a.s, b.s) < Math.min(a.e, b.e)) {
        out.push({ type: 'double', text: 'שיבוץ כפול: ' + other.name });
      }
    }
    return out;
  }

  return { toMin, win, len, coverage, posActive, weeklyBudget, assignedHours, warnings };
})();
