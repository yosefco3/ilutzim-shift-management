/**
 * AttendancePage — stage 3, the admin's morning screen.
 *
 * Day view (default): every employee who is scheduled OR punched today, one
 * thin timeline row each, grouped by the board's bands (morning/evening/
 * night), problems sorted first, a red now-line across all rows. "The admin
 * sees, not reads" — no recommendations, only shape and color.
 *
 * Week/month per-employee views arrive in the next step; their switcher
 * buttons are present but disabled so the layout is final.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  downloadYlmCenterReport,
  getAttendanceDay,
  getAttendancePeriodSummary,
  getAttendanceStatus,
} from '../api/attendanceApiClient';
import { triggerBlobDownload } from '../utils/download';
import ManualEntryDialog from '../components/attendance/ManualEntryDialog';
import TimelineBar from '../components/attendance/TimelineBar';
import messages from '../utils/messages';
import { minutesLabel, periodLabel, rangeFor, shiftRange } from '../utils/attendanceDates';

const M = () => messages.attendance;

const BAND_META = {
  morning: { icon: '☀️', label: 'בוקר' },
  evening: { icon: '🌆', label: 'ערב' },
  night: { icon: '🌙', label: 'לילה' },
};

const SEVERITY_CLASS = {
  big: 'att-tag-big',
  small: 'att-tag-small',
  ok: 'att-tag-ok',
  none: 'att-tag-none',
};

const todayIso = () => new Date().toLocaleDateString('sv-SE'); // YYYY-MM-DD, local

const hhmm = (iso) =>
  new Date(iso).toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' });

// The shared scale: an hour before the earliest planned/actual moment to an
// hour after the latest; a sane 06:00–22:00 default when the day is empty.
function computeScale(day, rows) {
  let min = null;
  let max = null;
  const feed = (iso) => {
    const t = new Date(iso).getTime();
    if (min === null || t < min) min = t;
    if (max === null || t > max) max = t;
  };
  rows.forEach((r) => {
    r.planned.forEach((w) => { feed(w.start); feed(w.end); });
    r.segments.forEach((s) => { feed(s.start); feed(s.end); });
  });
  if (min === null) {
    min = new Date(`${day}T06:00:00`).getTime();
    max = new Date(`${day}T22:00:00`).getTime();
  }
  const HOUR = 3600_000;
  return {
    start: new Date(Math.floor((min - HOUR) / HOUR) * HOUR).toISOString(),
    end: new Date(Math.ceil((max + HOUR) / HOUR) * HOUR).toISOString(),
  };
}

function ruler(scale) {
  const ticks = [];
  const s0 = new Date(scale.start).getTime();
  const s1 = new Date(scale.end).getTime();
  const span = s1 - s0;
  const stepHours = span > 14 * 3600_000 ? 4 : 2;
  const first = new Date(s0);
  first.setMinutes(0, 0, 0);
  for (let t = first.getTime(); t <= s1; t += stepHours * 3600_000) {
    if (t < s0) continue;
    ticks.push({
      left: `${((t - s0) / span) * 100}%`,
      label: String(new Date(t).getHours()).padStart(2, '0'),
    });
  }
  return ticks;
}

export default function AttendancePage() {
  const navigate = useNavigate();
  // view + date live in the URL so the employee page's back button (and any
  // deep link) returns to the exact list the admin left.
  const [params, setParams] = useSearchParams();
  const view = ['day', 'week', 'month'].includes(params.get('view'))
    ? params.get('view')
    : 'day';
  const date = params.get('date') || todayIso();
  const setView = (v) => setParams({ date, view: v }, { replace: true });
  const setDate = (d) => setParams({ date: d || todayIso(), view }, { replace: true });
  const [data, setData] = useState(null);
  const [summaryRows, setSummaryRows] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [manualOpen, setManualOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(null);
      if (view === 'day') {
        const [day, st] = await Promise.all([
          getAttendanceDay(date),
          getAttendanceStatus().catch(() => null),
        ]);
        setData(day);
        setStatus(st);
      } else {
        const range = rangeFor(date, view);
        setSummaryRows(await getAttendancePeriodSummary(range.from, range.to));
      }
    } catch (err) {
      setError(err.message || messages.common.error);
    } finally {
      setLoading(false);
    }
  }, [date, view]);

  useEffect(() => {
    setLoading(true);
    load();
    // Keep the now-line and classification fresh while the page sits open.
    const timer = setInterval(load, 60_000);
    return () => clearInterval(timer);
  }, [load]);

  const rows = useMemo(
    () => (data ? data.bands.flatMap((b) => b.rows) : []),
    [data],
  );
  const scale = useMemo(
    () => (data ? computeScale(data.date, rows) : null),
    [data, rows],
  );

  if (loading) return <div className="loading">{messages.common.loading}</div>;

  const isToday = date === todayIso();
  const counters = data?.counters || {};

  return (
    <div className="page att-page">
      <div className="att-header">
        <h2>{M().title}</h2>
        <div className="att-controls">
          <div className="att-view-switch" role="tablist">
            {['day', 'week', 'month'].map((v) => (
              <button
                key={v}
                type="button"
                className={`btn btn-sm ${view === v ? 'btn-primary' : 'btn-secondary'}`}
                aria-pressed={view === v}
                onClick={() => { setLoading(true); setView(v); }}
              >
                {v === 'day' ? M().viewDay : v === 'week' ? M().viewWeek : M().viewMonth}
              </button>
            ))}
          </div>
          {view === 'day' ? (
            <input
              type="date"
              className="settings-input att-date-input"
              value={date}
              onChange={(e) => setDate(e.target.value || todayIso())}
              aria-label={M().pickDate}
            />
          ) : (
            // A period picker that matches the view: prev/next by week or by
            // month, with a readable label of exactly what is on screen.
            <div className="att-view-switch">
              <button
                type="button"
                className="btn btn-sm btn-secondary"
                onClick={() => setDate(shiftRange(date, view, -1))}
              >
                {M().prev}
              </button>
              <span className="att-range-label">{periodLabel(date, view)}</span>
              <button
                type="button"
                className="btn btn-sm btn-secondary"
                onClick={() => setDate(shiftRange(date, view, 1))}
              >
                {M().next}
              </button>
            </div>
          )}
          {view === 'day' && (
            <button
              type="button"
              className="btn btn-sm btn-primary"
              onClick={() => setManualOpen(true)}
            >
              ➕ {M().manual.title}
            </button>
          )}
          {view === 'month' && (
            <button
              type="button"
              className="btn btn-sm btn-primary"
              onClick={async () => {
                const [year, month] = date.split('-').map(Number);
                const blob = await downloadYlmCenterReport(year, month);
                triggerBlobDownload(
                  blob,
                  `ylm_center_${year}-${String(month).padStart(2, '0')}.xlsx`,
                );
              }}
            >
              ⬇️ {M().ylmCenter}
            </button>
          )}
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {view !== 'day' ? (
        <PeriodSummaryList
          rows={summaryRows || []}
          onOpen={(uid) =>
            navigate(`/attendance/users/${uid}?date=${date}&view=${view}&back=${view}`)
          }
        />
      ) : (
      <>
      <div className="att-statusline">
        <span>{M().scheduled}: <strong>{counters.scheduled ?? 0}</strong></span>
        <span>{M().present}: <strong>{counters.present ?? 0}</strong></span>
        <span className="att-tag-big">{M().bigGaps}: <strong>{counters.big ?? 0}</strong></span>
        <span className="att-tag-small">{M().smallGaps}: <strong>{counters.small ?? 0}</strong></span>
        {status && (
          <span className="att-source">
            📱 {M().eventsToday}: <strong>{status.events_today}</strong>
            {status.last_event_at && <> · {M().lastEvent} {hhmm(status.last_event_at)}</>}
          </span>
        )}
      </div>

      {!rows.length ? (
        <p className="empty-state">{M().emptyDay}</p>
      ) : (
        <div className="card att-board">
          {/* shared hour ruler */}
          <div className="att-row att-ruler-row" dir="rtl">
            <div className="att-name" />
            <div className="att-rail att-ruler" dir="ltr">
              {ruler(scale).map((t) => (
                <span key={t.left} className="att-tick" style={{ left: t.left }}>
                  {t.label}
                </span>
              ))}
            </div>
            <div className="att-tag" />
          </div>

          {data.bands.map((band) => (
            <div key={band.band} className="att-band">
              <div className="att-band-head">
                {BAND_META[band.band]?.icon} {BAND_META[band.band]?.label || band.band}
              </div>
              {band.rows.map((row) => (
                <button
                  key={row.user_id}
                  type="button"
                  className="att-row att-row-btn"
                  onClick={() =>
                    navigate(`/attendance/users/${row.user_id}?date=${data.date}&back=day`)
                  }
                  title={M().openEmployee}
                >
                  <div className="att-name">{row.user_name}</div>
                  <TimelineBar
                    planned={row.planned}
                    segments={row.segments}
                    scaleStart={scale.start}
                    scaleEnd={scale.end}
                    now={isToday ? data.now : null}
                  />
                  <div className={`att-tag ${SEVERITY_CLASS[row.summary.severity] || ''}`}>
                    {row.summary.tag}
                  </div>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
      </>
      )}

      {manualOpen && (
        <ManualEntryDialog
          date={date}
          plannedByUser={Object.fromEntries(rows.map((r) => [r.user_id, r.planned]))}
          onClose={() => setManualOpen(false)}
          onSaved={load}
        />
      )}
    </div>
  );
}

// ── week/month: per-employee aggregate list (with column headers) ───────────

function PeriodSummaryList({ rows, onOpen }) {
  if (!rows.length) {
    return <p className="empty-state">{M().emptyPeriod}</p>;
  }
  const H = M().headers;
  return (
    <div className="card att-board">
      <div className="att-summary-row att-summary-head" aria-hidden="true">
        <div>{H.employee}</div>
        <div>{H.days}</div>
        <div>{H.actual}</div>
        <div>{H.planned}</div>
        <div>{H.extra}</div>
        <div>{H.issues}</div>
      </div>
      {rows.map((r) => (
        <button
          key={r.user_id}
          type="button"
          className="att-row-btn att-summary-row"
          onClick={() => onOpen(r.user_id)}
          title={M().openEmployee}
        >
          <div className="att-name">{r.user_name}</div>
          <div className="att-cell">
            {r.days_present}/{r.days_scheduled}
          </div>
          <div className="att-cell att-cell-strong">{minutesLabel(r.actual_minutes)}</div>
          <div className="att-cell">{minutesLabel(r.planned_minutes)}</div>
          <div className="att-cell att-extra-note">
            {r.extra_minutes > 0 ? `+${minutesLabel(r.extra_minutes)}` : '—'}
          </div>
          <div className="att-cell">
            {r.big > 0 && <span className="att-dot att-dot-big" title={M().bigGaps}>{r.big}</span>}
            {r.small > 0 && <span className="att-dot att-dot-small" title={M().smallGaps}>{r.small}</span>}
            {r.big === 0 && r.small === 0 && <span className="att-tag-ok">✅</span>}
          </div>
        </button>
      ))}
    </div>
  );
}
