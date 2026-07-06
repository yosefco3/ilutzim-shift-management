/**
 * WeekQuickLinks — the footer row of a week card: one-click links to every
 * per-week destination. Which links show depends on the week:
 *  - submissions detail + constraints export — always relevant
 *  - schedule download — a week that already STARTED downloads the ACTUAL
 *    schedule (סידור בפועל — what really happened, incl. mid-week edits);
 *    a future week keeps the planned snapshot (shown only when one exists)
 *  - attendance week-view — only once the week has started (there is no
 *    attendance before day one) and only when the attendance stage is built in
 *  - publish preview — only the current (publishable) week; the preview page
 *    already defaults to that same week (resolvePublishableWeek), so a plain
 *    link lands on the right one
 */
import { Link } from 'react-router-dom';
import messages from '../utils/messages';

// Same build-time flag convention as App.jsx / Navbar.jsx.
const ATTENDANCE_ENABLED = import.meta.env.VITE_ATTENDANCE_ENABLED !== 'false';
const ACTUAL_SCHEDULE_ENABLED =
  import.meta.env.VITE_ACTUAL_SCHEDULE_ENABLED !== 'false';

export default function WeekQuickLinks({
  week,
  todayIso,
  isCurrent = false,
  hasSavedSchedule = false,
  onExportConstraints,
  onDownloadSchedule,
  onDownloadActualSchedule,
}) {
  const L = messages.weeks.links;
  const started = (week.start_date || '') <= todayIso;
  const actualDownload = ACTUAL_SCHEDULE_ENABLED && started;

  return (
    <div className="week-links">
      {/* The editable submissions page (מילוי אילוצים), week preselected. */}
      <Link className="week-link" to={`/submissions?week=${week.id}`}>
        📋 {L.submissions}
      </Link>
      <button
        type="button"
        className="week-link"
        onClick={() => onExportConstraints(week)}
      >
        ⬇️ {L.exportConstraints}
      </button>
      {actualDownload ? (
        // Started week → "what really happened" (the editable actual layer;
        // always exists thanks to lazy seeding, no snapshot needed).
        <button
          type="button"
          className="week-link"
          onClick={() => onDownloadActualSchedule(week)}
        >
          📥 {L.downloadActualSchedule}
        </button>
      ) : (
        hasSavedSchedule && (
          <button
            type="button"
            className="week-link"
            onClick={() => onDownloadSchedule(week)}
          >
            📥 {L.downloadSchedule}
          </button>
        )
      )}
      {actualDownload && (
        <Link className="week-link" to={`/actual?week=${week.id}`}>
          🛠 {L.actualBoard}
        </Link>
      )}
      {ATTENDANCE_ENABLED && started && (
        <Link
          className="week-link"
          to={`/attendance?view=week&date=${week.start_date}`}
        >
          🕐 {L.attendance}
        </Link>
      )}
      {isCurrent && (
        <Link className="week-link" to="/publish-preview">
          👁️ {L.publishPreview}
        </Link>
      )}
    </div>
  );
}
