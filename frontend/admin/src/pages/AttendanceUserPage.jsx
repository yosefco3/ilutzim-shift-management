/**
 * AttendanceUserPage — one employee's story, week or month (stage 3).
 *
 * Each relevant day (scheduled or punched) is a block with a per-day hour
 * ruler and TWO aligned lanes: planned (soft indigo) above, actual
 * (classified segments) below — every deviation is a visible shape. Punch
 * times print under the actual lane with their source icon; a rounded
 * check-out shows "15:15 ⤴ בפועל 15:01". No recommendations — the colors and
 * the dry numbers only.
 */

import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  downloadYlmEmployeeReport,
  getAttendanceUserPeriod,
} from '../api/attendanceApiClient';
import { triggerBlobDownload } from '../utils/download';
import AttendanceEditDialog from '../components/attendance/AttendanceEditDialog';
import TimelineBar from '../components/attendance/TimelineBar';
import messages from '../utils/messages';
import {
  hebDayName,
  minutesLabel,
  rangeFor,
  shiftRange,
} from '../utils/attendanceDates';

const M = () => messages.attendance;

const SEVERITY_CLASS = {
  big: 'att-tag-big',
  small: 'att-tag-small',
  ok: 'att-tag-ok',
  none: 'att-tag-none',
};

const SOURCE_ICON = { telegram: '📱', manual: '✎', device: '✋' };

const todayIso = () => new Date().toLocaleDateString('sv-SE');

const hhmm = (isoStr) =>
  new Date(isoStr).toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' });

function dayScale(day) {
  let min = null;
  let max = null;
  const feed = (isoStr) => {
    const t = new Date(isoStr).getTime();
    if (min === null || t < min) min = t;
    if (max === null || t > max) max = t;
  };
  day.planned.forEach((w) => { feed(w.start); feed(w.end); });
  day.segments.forEach((s) => { feed(s.start); feed(s.end); });
  day.actual.forEach((a) => {
    feed(a.check_in_at);
    if (a.check_out_raw) feed(a.check_out_raw);
  });
  if (min === null) {
    min = new Date(`${day.date}T06:00:00`).getTime();
    max = new Date(`${day.date}T22:00:00`).getTime();
  }
  const HOUR = 3600_000;
  return {
    start: new Date(Math.floor((min - HOUR) / HOUR) * HOUR).toISOString(),
    end: new Date(Math.ceil((max + HOUR) / HOUR) * HOUR).toISOString(),
  };
}

function PunchLabels({ day, scale }) {
  const s0 = new Date(scale.start).getTime();
  const span = Math.max(1, new Date(scale.end).getTime() - s0);
  const pct = (isoStr) =>
    Math.max(0, Math.min(100, ((new Date(isoStr).getTime() - s0) / span) * 100));

  return (
    <div className="att-punch-labels" dir="ltr">
      {day.actual.map((a) => (
        <span key={a.shift_id}>
          <span className="att-punch" style={{ left: `${pct(a.check_in_at)}%` }}>
            {hhmm(a.check_in_at)} {SOURCE_ICON[a.in_source] || ''}
          </span>
          {a.check_out_raw && (
            <span className="att-punch" style={{ left: `${pct(a.check_out_raw)}%` }}>
              {a.check_out_rounded && a.check_out_rounded !== a.check_out_raw ? (
                <>
                  <strong>{hhmm(a.check_out_rounded)}</strong>
                  {' ⤴ '}
                  {hhmm(a.check_out_raw)}
                </>
              ) : (
                hhmm(a.check_out_raw)
              )}{' '}
              {SOURCE_ICON[a.out_source] || ''}
            </span>
          )}
        </span>
      ))}
    </div>
  );
}

// "25 ד'" for short spans, "6:55 שע'" once it crosses an hour — no raw ±415.
const spanLabel = (min) =>
  min >= 60 ? `${minutesLabel(min)} ${messages.attendance.hoursShort}` : `${min} ${messages.attendance.minutes}`;

// Human phrasing instead of signed numbers: "הקדים 4 ד'" / "איחר 25 ד'".
function deltaPhrases(s) {
  const T = messages.attendance;
  const out = [];
  const dIn = s.delta_in_minutes;
  if (dIn !== null && dIn !== undefined && dIn !== 0) {
    out.push(dIn > 0 ? `${T.cameLate} ${spanLabel(dIn)}` : `${T.cameEarly} ${spanLabel(-dIn)}`);
  }
  const dOut = s.delta_out_minutes;
  if (dOut !== null && dOut !== undefined && dOut !== 0) {
    out.push(dOut > 0 ? `${T.stayedLate} ${spanLabel(dOut)}` : `${T.leftEarly} ${spanLabel(-dOut)}`);
  }
  return out;
}

function DayBlock({ day, onEdit }) {
  const scale = dayScale(day);
  const positions = [...new Set(day.planned.map((w) => w.position_name))].join(' / ');
  const s = day.summary;
  const deltas = deltaPhrases(s);

  return (
    <div className="card att-day-block" data-testid="att-day-block">
      <div className="att-day-head">
        <span className="att-day-title">
          {hebDayName(day.date)}{' '}
          {new Date(`${day.date}T00:00:00`).toLocaleDateString('he-IL', {
            day: '2-digit', month: '2-digit',
          })}
        </span>
        {positions && <span className="att-day-pos">{positions}</span>}
        <span className={`att-tag ${SEVERITY_CLASS[s.severity] || ''}`}>
          {s.tag}
          {s.orphan_out_times.length > 0 && ` (${s.orphan_out_times.join(', ')})`}
        </span>
        <span className="att-day-nums">
          {M().actualShort} {minutesLabel(s.actual_minutes)}
          {' · '}
          {M().plannedShort} {minutesLabel(s.planned_minutes)}
          {deltas.length > 0 && ` · ${deltas.join(' · ')}`}
        </span>
        <button
          type="button"
          className="btn btn-sm btn-secondary"
          onClick={() => onEdit(day)}
          aria-label={`${M().edit.title} ${day.date}`}
        >
          ✎ {M().edit.button}
        </button>
      </div>

      <div className="att-lanes">
        <div className="att-lane-name">{M().lanePlanned}</div>
        <TimelineBar planned={day.planned} segments={[]} scaleStart={scale.start} scaleEnd={scale.end} />
        <div className="att-lane-name">{M().laneActual}</div>
        <div className="att-lane-actual">
          <TimelineBar planned={[]} segments={day.segments} scaleStart={scale.start} scaleEnd={scale.end} />
          <PunchLabels day={day} scale={scale} />
        </div>
      </div>
    </div>
  );
}

export default function AttendanceUserPage() {
  const { userId } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();

  const view = params.get('view') === 'month' ? 'month' : 'week';
  const date = params.get('date') || todayIso();
  const range = rangeFor(date, view);
  // Where the back button returns to: the exact main-page list we came from.
  const backView = ['day', 'week', 'month'].includes(params.get('back'))
    ? params.get('back')
    : 'day';

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editDay, setEditDay] = useState(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      setLoading(true);
      setData(await getAttendanceUserPeriod(userId, range.from, range.to));
    } catch (err) {
      setError(err.message || messages.common.error);
    } finally {
      setLoading(false);
    }
  }, [userId, range.from, range.to]);

  useEffect(() => { load(); }, [load]);

  const setView = (v) => setParams({ date, view: v, back: backView });
  const move = (dir) =>
    setParams({ date: shiftRange(date, view, dir), view, back: backView });

  const downloadReport = async () => {
    const [year, month] = date.split('-').map(Number);
    const blob = await downloadYlmEmployeeReport(userId, year, month);
    triggerBlobDownload(blob, `ylm_${year}-${String(month).padStart(2, '0')}.xlsx`);
  };

  if (loading) return <div className="loading">{messages.common.loading}</div>;

  const summary = data?.summary || {};

  return (
    <div className="page att-page">
      <div className="att-header">
        <h2>
          <button
            type="button"
            className="btn btn-sm btn-secondary"
            onClick={() => navigate(`/attendance?date=${date}&view=${backView}`)}
          >
            → {M().backToList}
          </button>{' '}
          {data?.user_name}
        </h2>
        <div className="att-controls">
          <div className="att-view-switch">
            <button
              type="button"
              className={`btn btn-sm ${view === 'week' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setView('week')}
            >
              {M().viewWeek}
            </button>
            <button
              type="button"
              className={`btn btn-sm ${view === 'month' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setView('month')}
            >
              {M().viewMonth}
            </button>
          </div>
          <div className="att-view-switch">
            <button type="button" className="btn btn-sm btn-secondary" onClick={() => move(-1)}>
              {M().prev}
            </button>
            <span className="att-range-label">{range.from} — {range.to}</span>
            <button type="button" className="btn btn-sm btn-secondary" onClick={() => move(1)}>
              {M().next}
            </button>
          </div>
          {view === 'month' && (
            <button
              type="button"
              className="btn btn-sm btn-primary"
              onClick={downloadReport}
              title={M().ylmReportHint}
            >
              ⬇️ {M().ylmReport}
            </button>
          )}
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="att-statusline">
        <span>{M().plannedHours}: <strong>{minutesLabel(summary.planned_minutes || 0)}</strong></span>
        <span>{M().actualHours}: <strong>{minutesLabel(summary.actual_minutes || 0)}</strong></span>
        <span>{M().extraHours}: <strong>{minutesLabel(summary.extra_minutes || 0)}</strong></span>
        <span className="att-tag-big">{M().bigGaps}: <strong>{summary.big ?? 0}</strong></span>
        <span className="att-tag-small">{M().smallGaps}: <strong>{summary.small ?? 0}</strong></span>
      </div>

      {!data?.days?.length ? (
        <p className="empty-state">{M().emptyPeriod}</p>
      ) : (
        data.days.map((day) => (
          <DayBlock key={day.date} day={day} onEdit={setEditDay} />
        ))
      )}

      {editDay && (
        <AttendanceEditDialog
          day={editDay}
          onClose={() => setEditDay(null)}
          onSaved={(freshDay) => {
            // Swap the refreshed day into place (server-side truth).
            setData((prev) => ({
              ...prev,
              days: prev.days.map((d) => (d.date === freshDay.date ? freshDay : d)),
            }));
          }}
        />
      )}
    </div>
  );
}
