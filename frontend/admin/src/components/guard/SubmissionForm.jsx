/**
 * Main submission form — renders day rows, notes, submit button.
 * Self-contained: calls useTelegram + useSubmission hooks internally.
 * Wrapped in .guard-layout for CSS scoping.
 */
import { useTelegram } from "../../hooks/useTelegram.js";
import { useSubmission } from "../../hooks/useSubmission.js";
import { messages } from "../../utils/guardMessages.js";
import LockBanner from "./LockBanner.jsx";
import DayRow from "./DayRow.jsx";
import "../../styles/guard.css";

export default function SubmissionForm() {
  const { initData } = useTelegram();
  const {
    loading,
    submitting,
    error,
    week,
    days,
    notes,
    setNotes,
    weekStatus,
    isLocked,
    warnings = [],
    toggleShift,
    setShiftHours,
    submit,
  } = useSubmission(initData);

  // Navigate to the success page ONLY when the backend confirmed the save.
  async function handleSubmit() {
    const { ok } = await submit();
    if (ok) window.location.href = "/submit/success";
  }

  if (loading) {
    return (
      <div className="guard-layout">
        <div className="loading">{messages.LABEL_LOADING}</div>
      </div>
    );
  }

  if (error && !week) {
    return (
      <div className="guard-layout">
        <div className="error-banner">{error}</div>
      </div>
    );
  }

  return (
    <div className="guard-layout">
      {isLocked && <LockBanner status={weekStatus} />}

      {error && <div className="error-banner">{error}</div>}

      {/* Week info */}
      {week && (
        <div className="week-info">
          <span className="week-label">
            {week.week_label || `שבוע ${week.id}`}
          </span>
        </div>
      )}

      {/* Day rows */}
      <div className="days-list">
        {days.map((day) => (
          <DayRow
            key={day.day_index}
            day={day}
            disabled={isLocked}
            onToggleShift={toggleShift}
            onSetShiftHours={setShiftHours}
          />
        ))}
      </div>

      {/* Notes */}
      <div className="notes-section">
        <label className="notes-label">{messages.LABEL_NOTES}</label>
        <textarea
          className="notes-input"
          value={notes}
          placeholder={messages.LABEL_NOTES_PLACEHOLDER}
          disabled={isLocked}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>

      {/* Soft constraint-rule warnings — informational, submit still allowed */}
      {!isLocked && warnings.length > 0 && (
        <div className="warning-banner">
          <strong>{messages.WARN_TITLE}</strong>
          <ul>
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Submit button */}
      {!isLocked && (
        <button
          type="button"
          className="submit-btn"
          onClick={handleSubmit}
          disabled={submitting}
        >
          {submitting ? messages.LABEL_SUBMITTING : messages.LABEL_SUBMIT}
        </button>
      )}
    </div>
  );
}