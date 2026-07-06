// Shared week-resolution helpers. The "publishable" / "current" week is the one
// the publish button belongs to, and the one the publish-preview page must show —
// keeping both in lockstep so the preview never targets a stale older week.

/** Today as an ISO date (YYYY-MM-DD) in the browser's local timezone. */
export function todayIso(now = new Date()) {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

const byStartAsc = (a, b) => (a.start_date || '').localeCompare(b.start_date || '');
const byStartDesc = (a, b) => (b.start_date || '').localeCompare(a.start_date || '');

/**
 * The week the publish button belongs to = the nearest week that has NOT started
 * yet (start_date > today) — the upcoming week guards submitted for, finalized
 * before it goes live. Falls back to the latest week only when no upcoming week
 * exists. Mirrors the backend rule in week_service._is_publishable_week.
 *
 * This is the week the publish-preview must default to: the schedule is always
 * built and broadcast for THIS week, so defaulting to "the first closed week in
 * list order" (weeks arrive unordered from the API) could lock the preview onto
 * an old, possibly wiped week and show an empty/stale schedule.
 */
export function resolvePublishableWeek(weeks, now = new Date()) {
  if (!weeks || !weeks.length) return null;
  const today = todayIso(now);
  const upcoming = weeks.filter((w) => (w.start_date || '') > today).sort(byStartAsc);
  return upcoming[0] || [...weeks].sort(byStartDesc)[0] || null;
}
