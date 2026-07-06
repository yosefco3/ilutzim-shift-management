/**
 * Soft constraint-rule warnings for the ADMIN submissions page.
 *
 * Mirrors the guard-side `computeWarnings` (hooks/useSubmission.js), but operates
 * on the admin "detailed submission" shape returned by
 * `GET /admin/weeks/{id}/submissions/detailed`:
 *
 *   detail.days[] = { date: "YYYY-MM-DD", is_available, shift_windows: [{ shift_type }] }
 *
 * A day counts as "active" when it has at least one shift window. Thresholds come
 * from `GET /submissions/constraint-rules` (admin-editable via /admin/settings).
 * These are informational only — they never block anything.
 */
import { messages } from "./guardMessages.js";

/** Longest run of consecutive calendar days that have at least one shift window. */
function maxConsecutiveActiveDays(days) {
  const activeDates = days
    .filter((d) => d.shift_windows && d.shift_windows.length > 0)
    .map((d) => d.date)
    .filter(Boolean)
    .sort();

  let run = 0;
  let max = 0;
  let prev = null;
  for (const ds of activeDates) {
    const cur = new Date(ds); // "YYYY-MM-DD" parses as UTC midnight
    if (prev && cur - prev === 86400000) {
      run += 1;
    } else {
      run = 1;
    }
    if (run > max) max = run;
    prev = cur;
  }
  return max;
}

/**
 * Build soft warnings for one guard's submission vs. the admin thresholds.
 * @param {{days?: Array}} detail - detailed submission object
 * @param {{min_shifts_per_guard, min_nights, min_evenings, max_consecutive_days}} rules
 * @returns {string[]} human-readable Hebrew warning lines (empty if within limits)
 */
export function computeAdminWarnings(detail, rules) {
  if (!rules || !detail?.days) return [];
  const days = detail.days;

  const total = days.reduce((n, d) => n + (d.shift_windows?.length || 0), 0);
  const nights = days.filter((d) =>
    d.shift_windows?.some((w) => w.shift_type === "night"),
  ).length;
  const evenings = days.filter((d) =>
    d.shift_windows?.some((w) => w.shift_type === "afternoon"),
  ).length; // afternoon = ערב
  const consec = maxConsecutiveActiveDays(days);

  const out = [];
  if (total < rules.min_shifts_per_guard)
    out.push(messages.WARN_MIN_SHIFTS(total, rules.min_shifts_per_guard));
  if (nights < rules.min_nights)
    out.push(messages.WARN_MIN_NIGHTS(nights, rules.min_nights));
  if (evenings < rules.min_evenings)
    out.push(messages.WARN_MIN_EVENINGS(evenings, rules.min_evenings));
  if (consec > rules.max_consecutive_days)
    out.push(messages.WARN_MAX_CONSEC(consec, rules.max_consecutive_days));
  return out;
}
