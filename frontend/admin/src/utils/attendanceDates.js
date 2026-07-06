/**
 * Date-range helpers for the attendance views (stage 3).
 * Weeks are Israeli: Sunday → Saturday.
 */

const iso = (d) => d.toLocaleDateString('sv-SE'); // YYYY-MM-DD, local tz

export function weekRange(dateStr) {
  const d = new Date(`${dateStr}T00:00:00`);
  const start = new Date(d);
  start.setDate(d.getDate() - d.getDay()); // getDay(): Sunday = 0
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  return { from: iso(start), to: iso(end) };
}

export function monthRange(dateStr) {
  const d = new Date(`${dateStr}T00:00:00`);
  const start = new Date(d.getFullYear(), d.getMonth(), 1);
  const end = new Date(d.getFullYear(), d.getMonth() + 1, 0);
  return { from: iso(start), to: iso(end) };
}

// Shift a range by ±1 period. view: 'week' | 'month'.
export function shiftRange(dateStr, view, direction) {
  const d = new Date(`${dateStr}T00:00:00`);
  if (view === 'month') {
    d.setMonth(d.getMonth() + direction, 1);
  } else {
    d.setDate(d.getDate() + 7 * direction);
  }
  return iso(d);
}

export function rangeFor(dateStr, view) {
  return view === 'month' ? monthRange(dateStr) : weekRange(dateStr);
}

const HEB_DAYS = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת'];

export function hebDayName(dateStr) {
  return HEB_DAYS[new Date(`${dateStr}T00:00:00`).getDay()];
}

export function minutesLabel(min) {
  const h = Math.floor(min / 60);
  const m = min % 60;
  return `${h}:${String(m).padStart(2, '0')}`;
}

// Human label for the picked period: week = "28.06 — 04.07", month = "יולי 2026".
export function periodLabel(dateStr, view) {
  if (view === 'month') {
    return new Date(`${dateStr}T00:00:00`).toLocaleDateString('he-IL', {
      month: 'long',
      year: 'numeric',
    });
  }
  const { from, to } = weekRange(dateStr);
  const fmt = (d) =>
    new Date(`${d}T00:00:00`).toLocaleDateString('he-IL', {
      day: '2-digit',
      month: '2-digit',
    });
  return `${fmt(from)} — ${fmt(to)}`;
}
