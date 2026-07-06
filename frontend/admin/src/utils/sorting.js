// Hebrew-aware sorting helpers for guard lists. Sorting at the display layer
// keeps lists ordered alphabetically (א-ב) automatically, including right after
// a new guard is added — no manual re-ordering needed.

// Compares two strings in Hebrew alphabetical order. Missing values sort last.
export function compareHebrew(a, b) {
  const x = (a || '').trim();
  const y = (b || '').trim();
  if (!x && !y) return 0;
  if (!x) return 1;
  if (!y) return -1;
  return x.localeCompare(y, 'he');
}

// Full display name for a guard/user record.
export function guardFullName(g) {
  return `${g.first_name || ''} ${g.last_name || ''}`.trim();
}

// Returns a new array of guards sorted by full name (Hebrew א-ב).
export function sortGuardsByName(guards) {
  return [...guards].sort((a, b) => compareHebrew(guardFullName(a), guardFullName(b)));
}

// True when `name` contains the search term (case-insensitive, trimmed).
// An empty term matches everything, so callers can filter unconditionally.
export function matchesGuardSearch(name, term) {
  const t = (term || '').trim().toLowerCase();
  return !t || (name || '').toLowerCase().includes(t);
}

// Returns a new array of submission rows sorted by guard full name (Hebrew א-ב).
export function sortSubmissionsByName(submissions) {
  return [...submissions].sort((a, b) =>
    compareHebrew(a.full_name || a.user_id, b.full_name || b.user_id),
  );
}
