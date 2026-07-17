/**
 * Admin API client — thin wrapper around fetch for the admin dashboard.
 * Dev: requests go through the Vite proxy (/api → localhost:8000).
 * Prod (single origin): built with VITE_API_URL='' so requests hit the backend
 * at the same origin root (/auth, /admin, …). `??` keeps an explicit empty value.
 */

const API_BASE = import.meta.env.VITE_API_URL ?? '/api';

function getToken() {
  return localStorage.getItem('admin_token');
}

export function isLoggedIn() {
  return !!getToken();
}

function setToken(token) {
  localStorage.setItem('admin_token', token);
}

function clearToken() {
  localStorage.removeItem('admin_token');
}

export async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };

  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    clearToken();
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    // FastAPI HTTPException uses `detail`; app exceptions use `error`.
    const message = body.detail || body.error || `HTTP ${res.status}`;
    const error = new Error(message);
    // Surface the HTTP status so callers can branch (e.g. publish 409 → offer
    // rebroadcast, generate 503 → "service unavailable") without parsing Hebrew
    // message strings. Additive only — existing callers read err.message.
    error.status = res.status;
    throw error;
  }

  // Handle 204 No Content (e.g. DELETE responses)
  if (res.status === 204) {
    return null;
  }

  // Handle blob responses (Excel export)
  if (endpoint.includes('/export/')) {
    return res.blob();
  }

  return res.json();
}

// ──── Auth ────
export function adminLogin(username, password) {
  return request('/auth/admin/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  }).then((data) => {
    setToken(data.access_token);
    return data;
  });
}

export function adminLogout() {
  clearToken();
}

// Change the logged-in admin's own password. The backend takes the admin id
// from the JWT, never from the body.
export function changeAdminPassword(currentPassword, newPassword) {
  return request('/auth/admin/change-password', {
    method: 'POST',
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
}

export function getAdminProfile() {
  return request('/auth/admin/me');
}

// ──── Guards (Users) ────
export function fetchGuards(params = {}) {
  const query = new URLSearchParams(params).toString();
  return request(`/admin/users?${query}`);
}

export function fetchGuard(id) {
  return request(`/admin/users/${id}`);
}

export function createGuard(data) {
  return request('/admin/users', { method: 'POST', body: JSON.stringify(data) });
}

export function updateGuard(id, data) {
  return request(`/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
}

export function deleteGuard(id) {
  return request(`/admin/users/${id}`, { method: 'DELETE' });
}

// ──── Weeks ────
export function fetchWeeks(params = {}) {
  const query = new URLSearchParams(params).toString();
  return request(`/admin/weeks?${query}`);
}

export function fetchWeek(id) {
  return request(`/admin/weeks/${id}`);
}

export function createWeek(data) {
  return request('/admin/weeks', { method: 'POST', body: JSON.stringify(data) });
}

export function updateWeekStatus(id, status) {
  return request(`/admin/weeks/${id}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
}

export function sendWeekReminders(id) {
  return request(`/admin/notifications/remind/${id}`, { method: 'POST' });
}

// Close the submission window: open → closed (reopenable). Mirrors the auto-lock time.
export function lockWeek(id) {
  return updateWeekStatus(id, 'closed');
}

export function unlockWeek(id) {
  return updateWeekStatus(id, 'open');
}

// Open a week for submission (closed → open). Sends guard notifications.
export function openWeek(id) {
  return request(`/admin/weeks/${id}/open`, { method: 'POST' });
}

// "Publish" broadcasts each guard their personal schedule. A first publish
// (CLOSED) also finalizes the week → LOCKED (terminal) and creates the next week;
// a re-publish (LOCKED, still current) only re-sends. Returns a summary
// { sent, skipped, total, republished }.
export function publishWeek(id) {
  return request(`/admin/weeks/${id}/publish`, { method: 'POST' });
}

export function deleteWeek(id) {
  return request(`/admin/weeks/${id}`, { method: 'DELETE' });
}

// Dry run of publish: returns the personal-schedule Telegram message each guard
// WOULD receive, without sending anything. Powers the publish-preview page.
// Each item: { user_name, phone_number, telegram_id, would_send, message }.
export function previewPublish(weekId) {
  return request(`/admin/weeks/${weekId}/publish-preview`);
}

// ──── Submissions ────
export function fetchSubmissions(weekId) {
  return request(`/admin/weeks/${weekId}/submissions`);
}

export function fetchSubmissionsDetailed(weekId) {
  return request(`/admin/weeks/${weekId}/submissions/detailed`);
}

// Admin acknowledges (or clears) a submission's rule violations. When
// acknowledged the submissions grid hides the orange violation marker.
export function acknowledgeSubmissionViolation(submissionId, acknowledged = true) {
  return request(`/submissions/${submissionId}/acknowledge-violation`, {
    method: 'PATCH',
    body: JSON.stringify({ acknowledged }),
  });
}

// Constraint-rule thresholds (min shifts/nights/evenings, max consecutive days).
// Public endpoint, admin-editable via /admin/settings. Used to surface soft,
// non-blocking warnings on submissions the guard sent.
export function fetchConstraintRules() {
  return request('/submissions/constraint-rules');
}

// A guard's existing submission for one week (admin-only), or null. Used to
// pre-fill the admin constraints form so the admin can edit what the guard
// (or a previous admin) already submitted — including Telegram submissions.
export function fetchGuardSubmission(userId, weekId) {
  const query = new URLSearchParams({ user_id: userId, week_id: weekId }).toString();
  return request(`/submissions/admin?${query}`);
}

// Admin fills a guard's weekly constraints on their behalf (e.g. guards
// without Telegram). Works regardless of the week's status.
export function createGuardSubmission(payload) {
  return request('/submissions/admin', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

// ──── Notifications ────
export function sendNotifications(weekId) {
  return request(`/admin/notifications/week/${weekId}`, { method: 'POST' });
}

// ──── Export ────
export async function exportWeekExcel(weekId) {
  const blob = await request(`/admin/export/constraints/${weekId}`);
  return blob;
}

// ──── Constraints import ────
// Multipart upload: build FormData and let the browser set the Content-Type
// boundary (the shared `request` helper forces application/json, which breaks
// file uploads), while still attaching the admin bearer token.
async function uploadConstraints(endpoint, file, query = {}) {
  const params = new URLSearchParams(
    Object.entries(query).filter(([, v]) => v != null && v !== ''),
  ).toString();
  const url = `${API_BASE}${endpoint}${params ? `?${params}` : ''}`;

  const form = new FormData();
  form.append('file', file);

  const token = getToken();
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(url, { method: 'POST', headers, body: form });

  if (res.status === 401) {
    clearToken();
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export function previewConstraintsImport(file) {
  return uploadConstraints('/admin/import/constraints/preview', file);
}

export function commitConstraintsImport(file, weekId) {
  return uploadConstraints('/admin/import/constraints/commit', file, { week_id: weekId });
}

// ──── Settings ────
export function fetchSettings() {
  return request('/admin/settings');
}

export function updateSettings(settingsMap) {
  return request('/admin/settings', {
    method: 'PUT',
    body: JSON.stringify({ settings: settingsMap }),
  });
}

// ──── Procedures (סד"פ) ────
// Mirrors backend/app/procedures/controllers/procedure_controller.py endpoints.
// All run under /admin/procedures (admin-only). The generate call can take
// 30–60s (one Claude request per procedure) — the shared request() helper has no
// timeout, so the spinner on ProceduresPage just shows until it resolves.
export function fetchProcedures() {
  return request('/admin/procedures');
}

export function fetchProcedure(id) {
  return request(`/admin/procedures/${id}`);
}

export function createProcedure({ title, body_text }) {
  return request('/admin/procedures', {
    method: 'POST',
    body: JSON.stringify({ title, body_text }),
  });
}

export function updateProcedure(id, { title, body_text }) {
  const body = {};
  if (title !== undefined) body.title = title;
  if (body_text !== undefined) body.body_text = body_text;
  return request(`/admin/procedures/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export function archiveProcedure(id) {
  return request(`/admin/procedures/${id}/archive`, { method: 'POST' });
}

// Hard-delete: removes the procedure AND all its quiz history (attempts,
// scores, results) via DB cascade. Archive is the keep-history alternative.
export function deleteProcedure(id) {
  return request(`/admin/procedures/${id}`, { method: 'DELETE' });
}

// Trigger AI question generation (drafts only). Resolves with
// { generated, skipped, total_questions }; rejects on 503 (no API key / Claude
// failure) or 409 (not a draft).
export function generateProcedureQuestions(id) {
  return request(`/admin/procedures/${id}/generate`, { method: 'POST' });
}

// ── Question editing ──
export function addProcedureQuestion(procId, { text, options, correct_index }) {
  return request(`/admin/procedures/${procId}/questions`, {
    method: 'POST',
    body: JSON.stringify({ text, options, correct_index }),
  });
}

export function updateProcedureQuestion(procId, qId, data) {
  return request(`/admin/procedures/${procId}/questions/${qId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export function deleteProcedureQuestion(procId, qId) {
  return request(`/admin/procedures/${procId}/questions/${qId}`, {
    method: 'DELETE',
  });
}

// Publish (or re-broadcast) a procedure. rebroadcast=true skips guards who
// already passed (POST /publish?rebroadcast=true). Resolves with
// { sent, skipped, total, republished }; rejects with 409 if already published
// when called without rebroadcast.
export function publishProcedure(id, { rebroadcast = false } = {}) {
  const query = rebroadcast ? '?rebroadcast=true' : '';
  return request(`/admin/procedures/${id}/publish${query}`, { method: 'POST' });
}

export function fetchProcedureResults(id) {
  return request(`/admin/procedures/${id}/results`);
}

// Upload a .docx for text extraction (does NOT save — returns the extracted
// text for the admin to review/edit before creating the procedure). Multipart,
// so it bypasses the JSON-forcing request() helper, same shape as
// uploadConstraints(): FormData + browser-set boundary + bearer token. The
// backend declares `title` as a Form field (not Query), so it goes in the body.
export function uploadProcedureDocx(file, title = '') {
  const url = `${API_BASE}/admin/procedures/upload`;

  const form = new FormData();
  form.append('file', file);
  form.append('title', title || '');

  const token = getToken();
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  return fetch(url, { method: 'POST', headers, body: form }).then(async (res) => {
    if (res.status === 401) {
      clearToken();
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || body.error || `HTTP ${res.status}`);
    }
    return res.json();
  });
}

// ──── Aliases used by pages ────
export const exportExcel = exportWeekExcel;
export const login = adminLogin;
export const sendReminder = sendWeekReminders;