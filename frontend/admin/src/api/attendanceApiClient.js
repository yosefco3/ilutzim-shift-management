/**
 * Attendance API client — stage 3.
 *
 * All attendance requests go through this client so the boundary is explicit
 * on the frontend too (same convention as builderApiClient). Reuses the shared
 * `request` helper from adminApiClient (single auth / 401 handling path).
 */

import { request } from './adminApiClient';

const BASE = '/admin/attendance';

// day: 'YYYY-MM-DD' (omit for today) → { date, now, counters, bands }
export function getAttendanceDay(date) {
  return request(`${BASE}/day${date ? `?date=${date}` : ''}`);
}

// One employee's classified days over a range (max 62 days server-side).
export function getAttendanceUserPeriod(userId, from, to) {
  return request(`${BASE}/users/${userId}?from=${from}&to=${to}`);
}

// Source-health widget: { enabled, events_today, last_event_at }
export function getAttendanceStatus() {
  return request(`${BASE}/status`);
}

// Aggregated per-employee lines for the week/month list view.
export function getAttendancePeriodSummary(from, to) {
  return request(`${BASE}/period-summary?from=${from}&to=${to}`);
}

// One admin correction; returns { adjustment, day } — day is refreshed.
export function postAttendanceAdjustment(body) {
  return request(`${BASE}/adjustments`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// The audit trail for one user-day.
export function getAttendanceAdjustments(userId, workDate) {
  return request(`${BASE}/adjustments?user_id=${userId}&work_date=${workDate}`);
}

// Quick manual attendance (guards without Telegram): in (+optional out).
export function postAttendanceManualEntry(body) {
  return request(`${BASE}/manual-entry`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// YLM payroll sheets (xlsx blobs — hours columns only).
export function downloadYlmEmployeeReport(userId, year, month) {
  return request(`${BASE}/export/employee/${userId}?year=${year}&month=${month}`);
}

export function downloadYlmCenterReport(year, month) {
  return request(`${BASE}/export/center?year=${year}&month=${month}`);
}
