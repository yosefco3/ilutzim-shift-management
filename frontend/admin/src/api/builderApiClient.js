/**
 * Builder API client — part B (schedule builder).
 *
 * All part-B requests go through this client so the part-A / part-B boundary is
 * explicit on the frontend too. It reuses the shared `request` helper from
 * adminApiClient (single auth / 401 handling path).
 */

import { request } from './adminApiClient';

const BASE = '/admin/builder/profiles';

export function listProfiles() {
  return request(BASE);
}

export function createProfile(body) {
  return request(BASE, { method: 'POST', body: JSON.stringify(body) });
}

export function getProfile(id) {
  return request(`${BASE}/${id}`);
}

// `body` is sent verbatim, so `day_labels` (step 07) and every other profile
// field pass through unchanged — no allow-list to update when adding fields.
export function updateProfile(id, body) {
  return request(`${BASE}/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
}

export function duplicateProfile(id, body = {}) {
  return request(`${BASE}/${id}/duplicate`, { method: 'POST', body: JSON.stringify(body) });
}

// How many weeks/assignments a delete would cascade-wipe → { weeks, assignments, is_last }.
export function getProfileDeleteImpact(id) {
  return request(`${BASE}/${id}/delete-impact`);
}

export function deleteProfile(id) {
  return request(`${BASE}/${id}`, { method: 'DELETE' });
}

// Mark a profile as the default (the board falls back to it). Clears the flag
// on any other profile server-side.
export function setDefaultProfile(id) {
  return request(`${BASE}/${id}/default`, { method: 'POST' });
}

// ── Positions (within a profile) ───────────────────────────────────────

export function listPositions(profileId) {
  return request(`${BASE}/${profileId}/positions`);
}

export function createPosition(profileId, body) {
  return request(`${BASE}/${profileId}/positions`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function getPosition(id) {
  return request(`/admin/builder/positions/${id}`);
}

export function updatePosition(id, body) {
  return request(`/admin/builder/positions/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export function deletePosition(id) {
  return request(`/admin/builder/positions/${id}`, { method: 'DELETE' });
}

// Deep-copy a position into another profile (drag-and-drop in the UI).
export function copyPosition(id, targetProfileId) {
  return request(`/admin/builder/positions/${id}/copy`, {
    method: 'POST',
    body: JSON.stringify({ target_profile_id: targetProfileId }),
  });
}

// Persist a new position order within a profile (drag-and-drop on the board).
// `positionIds` must be the profile's full position set in the desired order.
export function reorderPositions(profileId, positionIds) {
  return request(`${BASE}/${profileId}/positions/order`, {
    method: 'PUT',
    body: JSON.stringify({ position_ids: positionIds }),
  });
}

// Atomic bulk replace of `day_schedules` for a subset of the profile's positions
// (the matrix editor's single Save in step 04 — last-write-wins per position so
// two admins editing different rows don't clobber each other [EDGE C1]).
// `items`: [{ position_id, day_schedules }] — backend validates every id belongs
// to the profile or 409s atomically [EDGE C2].
export function bulkUpdateDaySchedules(profileId, items) {
  return request(`${BASE}/${profileId}/positions/day-schedules`, {
    method: 'PUT',
    body: JSON.stringify({ items }),
  });
}

// ── Requirement-attribute vocabulary ───────────────────────────────────

const ATTRS_BASE = '/admin/builder/attributes';

export function listAttributes() {
  return request(ATTRS_BASE);
}

export function createAttribute(body) {
  return request(ATTRS_BASE, { method: 'POST', body: JSON.stringify(body) });
}

export function updateAttribute(id, body) {
  return request(`${ATTRS_BASE}/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
}

export function deleteAttribute(id) {
  return request(`${ATTRS_BASE}/${id}`, { method: 'DELETE' });
}

// ── Board (week ↔ profile binding + read-only grid) ────────────────────

const WEEKS_BASE = '/admin/builder/weeks';

// Board for the next week (the upcoming week guards submit availability for).
// The backend resolves which week that is — no week id needed.
export function getNextWeekBoard() {
  return request('/admin/builder/board/next');
}

export function getWeekProfile(weekId) {
  return request(`${WEEKS_BASE}/${weekId}/profile`);
}

export function setWeekProfile(weekId, profileId) {
  return request(`${WEEKS_BASE}/${weekId}/profile`, {
    method: 'PUT',
    body: JSON.stringify({ profile_id: profileId }),
  });
}

export function getBoard(weekId) {
  return request(`${WEEKS_BASE}/${weekId}/board`);
}

// ── Manual assignment (pool + cell assign/unassign) ────────────────────

// Guards who submitted availability for the week (the cell-picker source).
export function getPool(weekId) {
  return request(`${WEEKS_BASE}/${weekId}/pool`);
}

export function getAssignments(weekId) {
  return request(`${WEEKS_BASE}/${weekId}/assignments`);
}

// body: { position_id, day_index, user_id, segment_start?, segment_end? }
export function createAssignment(weekId, body) {
  return request(`${WEEKS_BASE}/${weekId}/assignments`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// Set/clear an assignment's time segment. body: { segment_start, segment_end }
// (null/null = back to covering the whole window).
export function updateAssignmentSegment(assignmentId, body) {
  return request(`/admin/builder/assignments/${assignmentId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export function deleteAssignment(assignmentId) {
  return request(`/admin/builder/assignments/${assignmentId}`, { method: 'DELETE' });
}

// ── Saved schedule (frozen snapshot per week) ──────────────────────────

// Snapshot the current live board + assignments for the week (upsert).
export function saveSchedule(weekId) {
  return request(`${WEEKS_BASE}/${weekId}/save-schedule`, { method: 'POST' });
}

// Metadata for every saved snapshot — which weeks have a downloadable schedule.
export function listSavedSchedules() {
  return request('/admin/builder/saved-schedules');
}

// Download the saved-schedule xlsx. The path contains '/export/', so the shared
// request() helper returns a Blob (see adminApiClient). Returns a Blob.
export function downloadSavedSchedule(weekId) {
  return request(`/admin/builder/export/saved-schedule/${weekId}`);
}

// Download the built-schedule grid xlsx (positions × days). Path contains
// '/export/' → the shared request() helper returns a Blob.
export function exportScheduleGrid(weekId) {
  return request(`/admin/export/schedule/${weekId}`);
}

// Download the ACTUAL schedule (סידור בפועל) grid xlsx — same layout, read
// from the week's editable execution copy ("what really happened"). Only
// meaningful for weeks that already started. Blob response.
export function exportActualScheduleGrid(weekId) {
  return request(`/admin/export/actual-schedule/${weekId}`);
}

// The actual schedule as a PNG image (same renderer as the planned PNG).
// Path contains '/export/' → Blob response.
export function exportActualSchedulePng(weekId) {
  return request(`/admin/export/actual-schedule-png/${weekId}`);
}

// ── Actual schedule (סידור בפועל) — the editable execution board ────────

// The full actual board for a started week (lazy-seeds on first read):
// rows + assignments + soft warnings.
export function getActualBoard(weekId) {
  return request(`/admin/actual/${weekId}/board`);
}

// Place a guard on an actual cell (free editing; soft warnings only).
export function createActualAssignment(weekId, payload) {
  return request(`/admin/actual/${weekId}/assignments`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

// Set/clear an actual assignment's time segment (null/null = whole window).
export function updateActualSegment(assignmentId, payload) {
  return request(`/admin/actual/assignments/${assignmentId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteActualAssignment(assignmentId) {
  return request(`/admin/actual/assignments/${assignmentId}`, { method: 'DELETE' });
}

// Add an ad-hoc position mid-week (the unforeseen-event story).
export function createActualPosition(weekId, payload) {
  return request(`/admin/actual/${weekId}/positions`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateActualPosition(positionId, payload) {
  return request(`/admin/actual/positions/${positionId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteActualPosition(positionId) {
  return request(`/admin/actual/positions/${positionId}`, { method: 'DELETE' });
}

// Promote the week's actual board to a new reusable activation profile.
export function saveActualAsProfile(weekId, name) {
  return request(`/admin/actual/${weekId}/save-as-profile`, {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

// Add a one-off external reinforcement guard (מתגבר) to this week's pool.
export function createReinforcement(weekId, payload) {
  return request(`/admin/actual/${weekId}/reinforcements`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

// Remove a reinforcement card (deletes its one-off guard + assignments too).
export function deleteReinforcement(cardId) {
  return request(`/admin/actual/reinforcements/${cardId}`, { method: 'DELETE' });
}

// Download the reinforcements report xlsx (names, work dates, hours) for a
// period. Path contains '/export/' → Blob response.
export function exportReinforcementsReport(startIso, endIso) {
  return request(`/admin/actual/export/reinforcements?start=${startIso}&end=${endIso}`);
}

// Download the per-guard "positions" xlsx (guard-grouped). Blob response.
export function exportGuardPositions(weekId) {
  return request(`/admin/export/guard-positions/${weekId}`);
}

// Download the built-schedule grid as a PNG image — the same layout guards
// receive on publish. Path contains '/export/' → Blob response.
export function exportSchedulePng(weekId) {
  return request(`/admin/export/schedule-png/${weekId}`);
}
