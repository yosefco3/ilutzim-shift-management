/**
 * ManualEntryDialog — quick attendance entry for guards without Telegram
 * (stage 3 / 02 step 7). Three clicks in the common case: pick the guard →
 * "⚡ לפי הסידור" (prefills the planned window) → save.
 *
 * Guards WITHOUT a telegram_id sort first (tagged 📵) — they are who this is
 * for — and selecting one auto-fills the default reason.
 */

import { useMemo, useState } from 'react';
import { postAttendanceManualEntry } from '../../api/attendanceApiClient';
import { useGuards } from '../../hooks/useGuards';
import messages from '../../utils/messages';

const M = () => messages.attendance.manual;

const hhmm = (iso) =>
  new Date(iso).toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' });

export default function ManualEntryDialog({ date, plannedByUser = {}, onSaved, onClose }) {
  const { guards, loading } = useGuards();
  const [userId, setUserId] = useState('');
  const [checkIn, setCheckIn] = useState('');
  const [checkOut, setCheckOut] = useState('');
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const sorted = useMemo(() => {
    const active = guards.filter((g) => g.is_active);
    return [
      ...active.filter((g) => !g.telegram_id),
      ...active.filter((g) => g.telegram_id),
    ];
  }, [guards]);

  const planned = plannedByUser[userId] || [];

  const pickGuard = (id) => {
    setUserId(id);
    const guard = guards.find((g) => g.id === id);
    if (guard && !guard.telegram_id && !reason) {
      setReason(M().defaultReason);
    }
  };

  const fillFromSchedule = () => {
    if (!planned.length) return;
    setCheckIn(hhmm(planned[0].start));
    setCheckOut(hhmm(planned[planned.length - 1].end));
  };

  const submit = async () => {
    if (!userId) { setError(M().guardRequired); return; }
    if (!checkIn) { setError(M().timeRequired); return; }
    if (reason.trim().length < 2) { setError(M().reasonRequired); return; }
    try {
      setSaving(true);
      setError(null);
      await postAttendanceManualEntry({
        user_id: userId,
        date,
        check_in: checkIn,
        check_out: checkOut || null,
        reason: reason.trim(),
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message || messages.common.error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content att-edit-dialog" onClick={(e) => e.stopPropagation()}>
        <h3 className="modal-title">
          {M().title} — {new Date(`${date}T00:00:00`).toLocaleDateString('he-IL')}
        </h3>

        {loading ? (
          <div className="loading">{messages.common.loading}</div>
        ) : (
          <>
            <select
              className="settings-input"
              value={userId}
              onChange={(e) => pickGuard(e.target.value)}
              aria-label={M().guard}
            >
              <option value="">{M().pickGuard}</option>
              {sorted.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.telegram_id ? '' : '📵 '}{g.first_name} {g.last_name}
                </option>
              ))}
            </select>

            <div className="att-manual-times" dir="ltr">
              <input
                type="time"
                className="settings-input"
                value={checkIn}
                onChange={(e) => setCheckIn(e.target.value)}
                aria-label={M().checkIn}
              />
              <span>—</span>
              <input
                type="time"
                className="settings-input"
                value={checkOut}
                onChange={(e) => setCheckOut(e.target.value)}
                aria-label={M().checkOut}
              />
              <button
                type="button"
                className="btn btn-sm btn-secondary"
                disabled={!planned.length}
                title={planned.length ? '' : M().noSchedule}
                onClick={fillFromSchedule}
              >
                {M().fromSchedule}
              </button>
            </div>

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
              <button type="button" className="btn btn-secondary" onClick={onClose}>
                {messages.common.cancel}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
