/**
 * Admin constraints page — lets an admin fill a guard's weekly availability on
 * their behalf (for guards without Telegram). Reuses the guard-side DayRow +
 * guard.css for the per-day shift toggles.
 */
import { useParams, useNavigate } from 'react-router-dom';
import { useAdminConstraints } from '../hooks/useAdminConstraints';
import DayRow from '../components/guard/DayRow';
import { useToast } from '../components/Toast';
import { messages as guardMessages } from '../utils/guardMessages';
import messages from '../utils/messages';
import '../styles/guard.css';

const WEEK_STATUS_LABELS = {
  open: 'פתוח',
  closed: 'סגור',
  locked: 'נעול (סופי)',
};

export default function AdminConstraintsPage() {
  const { guardId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const {
    loading,
    error,
    saving,
    guard,
    weeks,
    selectedWeekId,
    setSelectedWeekId,
    isPublished,
    days,
    notes,
    setNotes,
    toggleShift,
    setShiftHours,
    submit,
  } = useAdminConstraints(guardId);

  if (loading) return <div className="loading">{messages.common.loading}</div>;

  const guardName = guard ? `${guard.first_name} ${guard.last_name}` : '';

  // On a successful save, confirm and return to the submissions list (closes the form).
  const handleSubmit = async () => {
    const ok = await submit();
    if (ok) {
      toast.success(`${messages.common.success} — ${guardName}`);
      navigate('/submissions');
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <h2>
          {messages.guards.fillConstraints} — {guardName}
        </h2>
        <button className="btn btn-secondary" onClick={() => navigate('/submissions')}>
          {messages.common.back || 'חזרה'}
        </button>
      </div>

      {/* Week selector */}
      <div className="form-group">
        <label>שבוע</label>
        <select
          value={selectedWeekId}
          onChange={(e) => setSelectedWeekId(e.target.value)}
        >
          {weeks.map((w) => (
            <option key={w.id} value={w.id}>
              {w.week_label} ({WEEK_STATUS_LABELS[w.status] || w.status})
            </option>
          ))}
        </select>
        <p className="hint">ניתן למלא ולערוך אילוצים כששבוע סגור / פתוח / נעול — אך לא לאחר שפורסם.</p>
      </div>

      {/* Day rows (guard-scoped CSS) */}
      <div className="guard-layout">
        {error && <div className="error-banner">{error}</div>}
        {isPublished && (
          <div className="error-banner">{messages.guards.cannotEditPublished}</div>
        )}

        <div className="days-list">
          {days.map((day) => (
            <DayRow
              key={day.day_index}
              day={day}
              disabled={isPublished}
              onToggleShift={toggleShift}
              onSetShiftHours={setShiftHours}
            />
          ))}
        </div>

        <div className="notes-section">
          <label className="notes-label">{guardMessages.LABEL_NOTES}</label>
          <textarea
            className="notes-input"
            value={notes}
            placeholder={guardMessages.LABEL_NOTES_PLACEHOLDER}
            onChange={(e) => setNotes(e.target.value)}
            disabled={isPublished}
          />
        </div>

        <button
          type="button"
          className="submit-btn"
          disabled={saving || !selectedWeekId || isPublished}
          onClick={handleSubmit}
        >
          {saving ? messages.common.loading : guardMessages.LABEL_SUBMIT}
        </button>
      </div>
    </div>
  );
}
