/**
 * AttendanceEditDialog — the admin's ONE editing tool (stage 3 / 02).
 *
 * Opened per day from the employee page. Lists the day's punches with
 * fix/void actions, offers add-punch, and (for a no-show day) absence
 * approval. Every action requires a reason — it lands in the audit trail.
 * On success the server returns the refreshed day, handed back via onSaved.
 */

import { useState } from 'react';
import { postAttendanceAdjustment } from '../../api/attendanceApiClient';
import messages from '../../utils/messages';

const M = () => messages.attendance.edit;

const hhmm = (iso) =>
  new Date(iso).toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' });

// punches of a day as flat rows: {event_id, direction, at, source}
function punchRows(day) {
  const rows = [];
  day.actual.forEach((a) => {
    if (a.in_event_id) {
      rows.push({ event_id: a.in_event_id, direction: 'in', at: a.check_in_at, source: a.in_source });
    }
    if (a.out_event_id && a.check_out_raw) {
      rows.push({ event_id: a.out_event_id, direction: 'out', at: a.check_out_raw, source: a.out_source });
    }
  });
  // Orphan OUTs (out-without-in) pair into no shift, so they never appear in
  // day.actual — the summary carries them with their event ids so the admin
  // can fix/void them here like any other punch.
  (day.summary?.orphan_outs || []).forEach((o) => {
    rows.push({ event_id: o.event_id, direction: 'out', at: o.punched_at, source: o.source, orphan: true });
  });
  rows.sort((a, b) => new Date(a.at) - new Date(b.at));
  return rows;
}

export default function AttendanceEditDialog({ day, onSaved, onClose }) {
  // mode: {type:'edit_time',row} | {type:'add'} | {type:'void',row} | {type:'absence'}
  const [mode, setMode] = useState(null);
  const [time, setTime] = useState('');
  const [direction, setDirection] = useState('in');
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const punches = punchRows(day);
  const dirLabel = (d) => (d === 'in' ? M().dirIn : M().dirOut);

  const submit = async () => {
    if (reason.trim().length < 2) {
      setError(M().reasonRequired);
      return;
    }
    const body = { action: '', reason: reason.trim() };
    if (mode.type === 'edit_time') {
      body.action = 'edit_time';
      body.event_id = mode.row.event_id;
      body.punched_at = `${day.date}T${time}:00`;
    } else if (mode.type === 'add') {
      body.action = 'add_punch';
      body.user_id = day.user_id;
      body.direction = direction;
      body.punched_at = `${day.date}T${time}:00`;
    } else if (mode.type === 'void') {
      body.action = 'void_punch';
      body.event_id = mode.row.event_id;
    } else {
      body.action = 'mark_absence';
      body.user_id = day.user_id;
      body.work_date = day.date;
    }
    if ((mode.type === 'edit_time' || mode.type === 'add') && !time) {
      setError(M().timeRequired);
      return;
    }
    try {
      setSaving(true);
      setError(null);
      const result = await postAttendanceAdjustment(body);
      onSaved(result.day);
      onClose();
    } catch (err) {
      setError(err.message || messages.common.error);
    } finally {
      setSaving(false);
    }
  };

  const startMode = (m) => {
    setMode(m);
    setError(null);
    if (m.type === 'edit_time') setTime(hhmm(m.row.at));
    if (m.type === 'add') setTime('');
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content att-edit-dialog" onClick={(e) => e.stopPropagation()}>
        <h3 className="modal-title">
          {M().title} — {new Date(`${day.date}T00:00:00`).toLocaleDateString('he-IL')}
        </h3>

        {!mode && (
          <>
            {punches.length ? (
              <ul className="att-edit-punches">
                {punches.map((row) => (
                  <li key={row.event_id} className="att-edit-punch-row">
                    <span>
                      {dirLabel(row.direction)} <strong>{hhmm(row.at)}</strong>
                      {row.source === 'manual' && ' ✎'}
                      {row.orphan && <span className="att-edit-orphan-tag"> {M().orphanTag}</span>}
                    </span>
                    <span className="att-edit-punch-actions">
                      <button type="button" className="btn btn-sm btn-secondary"
                        onClick={() => startMode({ type: 'edit_time', row })}>
                        {M().fixTime}
                      </button>
                      <button type="button" className="btn btn-sm btn-danger"
                        onClick={() => startMode({ type: 'void', row })}>
                        {M().voidPunch}
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted">{M().noPunches}</p>
            )}
            <div className="modal-actions">
              <button type="button" className="btn btn-primary"
                onClick={() => startMode({ type: 'add' })}>
                {M().addPunch}
              </button>
              {!punches.length && (
                <button type="button" className="btn btn-secondary"
                  onClick={() => startMode({ type: 'absence' })}>
                  {M().markAbsence}
                </button>
              )}
              <button type="button" className="btn btn-secondary" onClick={onClose}>
                {messages.common.cancel}
              </button>
            </div>
          </>
        )}

        {mode && (
          <>
            <p className="att-edit-mode-title">
              {mode.type === 'edit_time' && `${M().fixTime}: ${dirLabel(mode.row.direction)} ${hhmm(mode.row.at)}`}
              {mode.type === 'add' && M().addPunch}
              {mode.type === 'void' && `${M().voidPunch}: ${dirLabel(mode.row.direction)} ${hhmm(mode.row.at)}`}
              {mode.type === 'absence' && M().markAbsence}
            </p>

            {mode.type === 'add' && (
              <select
                className="settings-input"
                value={direction}
                onChange={(e) => setDirection(e.target.value)}
                aria-label={M().direction}
              >
                <option value="in">{M().dirIn}</option>
                <option value="out">{M().dirOut}</option>
              </select>
            )}
            {(mode.type === 'edit_time' || mode.type === 'add') && (
              <input
                type="time"
                className="settings-input"
                value={time}
                onChange={(e) => setTime(e.target.value)}
                aria-label={M().newTime}
              />
            )}
            <input
              type="text"
              className="settings-input att-edit-reason"
              placeholder={M().reasonPlaceholder}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              aria-label={M().reason}
            />
            {error && <div className="error-banner">{error}</div>}
            <div className="modal-actions">
              <button type="button" className="btn btn-primary" disabled={saving} onClick={submit}>
                {saving ? messages.common.loading : messages.common.confirm}
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => setMode(null)}>
                {M().back}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
