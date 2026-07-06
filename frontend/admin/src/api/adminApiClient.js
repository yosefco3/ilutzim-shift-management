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
    throw new Error(body.detail || body.error || `HTTP ${res.status}`);
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

// ──── Aliases used by pages ────
export const exportExcel = exportWeekExcel;
export const login = adminLogin;
export const sendReminder = sendWeekReminders;