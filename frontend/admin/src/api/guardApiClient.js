/**
 * Guard API client — for Telegram-authenticated guard submissions.
 * Uses Telegram initData for auth (not JWT).
 * Dev: requests go through the Vite proxy (/api → localhost:8000).
 * Prod (single origin): built with VITE_API_URL='' so requests hit the backend
 * at the same origin root. `??` keeps an explicit empty value (unlike `||`).
 */

import { messages } from '../utils/guardMessages.js';

const API_BASE = import.meta.env.VITE_API_URL ?? '/api';

/**
 * Perform an HTTP request with Telegram initData auth.
 * @param {string} path - API path (e.g. "/submissions/current-week")
 * @param {RequestInit} options - Fetch options
 * @param {string} initData - Telegram WebApp initData for auth
 * @returns {Promise<{data: any, error: string|null, status: number|null}>}
 *   ``status`` is exposed (additively) so callers like the procedure page can
 *   render status-specific screens (401 vs 404 vs 503) instead of a generic
 *   message; existing callers ignore it.
 */
async function request(path, options, initData) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-Telegram-Init-Data': initData,
        ...options.headers,
      },
    });

    if (!res.ok) {
      // Prefer the backend's own message so the approval/rejection text the guard
      // sees is authoritative (from the server, not invented in the frontend).
      let detail = null;
      try {
        const body = await res.json();
        if (typeof body?.detail === 'string') detail = body.detail;
      } catch {
        /* no / non-JSON body */
      }

      let fallback;
      if (res.status === 401) {
        fallback = messages.ERR_AUTH;
      } else if (res.status === 403 || res.status === 409) {
        fallback = messages.ERR_LOCKED;
      } else {
        fallback = messages.ERR_GENERIC;
      }
      // 401 is an auth/plumbing failure — keep the friendly hint rather than a
      // raw server detail; for everything else, trust the backend's message.
      const error = res.status === 401 ? fallback : detail || fallback;
      return { data: null, error, status: res.status };
    }

    // 204 No Content
    if (res.status === 204) {
      return { data: null, error: null, status: res.status };
    }

    const data = await res.json();
    return { data, error: null, status: res.status };
  } catch {
    return { data: null, error: messages.ERR_NETWORK, status: null };
  }
}

/**
 * GET request with Telegram initData.
 */
async function get(path, initData) {
  return request(path, { method: 'GET' }, initData);
}

/**
 * POST request with Telegram initData.
 */
async function post(path, body, initData) {
  return request(
    path,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
    initData,
  );
}

// ──── Procedures (סד"פ) — guard WebApp reading page ────
// Same request helper + X-Telegram-Init-Data header as the submission calls
// (dev bypass comes free). The GET records a read receipt; the POST starts the
// quiz in chat (first poll sent) so the page can close itself.

/**
 * Fetch one PUBLISHED procedure for the guard reading page (+ read receipt).
 * @param {string} procedureId
 * @param {string} initData - Telegram WebApp initData
 */
export function getProcedure(procedureId, initData) {
  return get(`/procedures/${procedureId}`, initData);
}

/**
 * Start the procedure's quiz from the reading page — sends the first poll to the
 * guard's chat. On success the page calls Telegram.WebApp.close().
 * @param {string} procedureId
 * @param {string} initData - Telegram WebApp initData
 */
export function startProcedureQuiz(procedureId, initData) {
  return post(`/procedures/${procedureId}/quiz/start`, {}, initData);
}

export { get, post };
