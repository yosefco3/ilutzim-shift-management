import { Fragment, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import messages from '../utils/messages';
import { DAY_NAMES, SHIFT_LABELS } from '../utils/guardMessages';
import { computeAdminWarnings } from '../utils/submissionWarnings';
import { sortSubmissionsByName } from '../utils/sorting';
import ConfirmDialog from './ConfirmDialog';

export default function StatusGrid({
  submissions,
  detailsByUser = {},
  canFillConstraints = false,
  rules = null,
  onAcknowledgeViolation,
}) {
  const [expandedUser, setExpandedUser] = useState(null);
  // The submission whose violation-acknowledge dialog is open: { id, name, warnings }
  const [violationDialog, setViolationDialog] = useState(null);
  const navigate = useNavigate();

  // Detail row spans all columns. There's always a trailing violation-marker
  // column; the actions column only exists when the week is editable.
  const colCount = canFillConstraints ? 6 : 5;

  if (!submissions.length) {
    return <p className="empty-state">{messages.submissions.empty}</p>;
  }

  const sortedSubmissions = sortSubmissionsByName(submissions);

  function handleConfirmAcknowledge() {
    if (violationDialog && onAcknowledgeViolation) {
      onAcknowledgeViolation(violationDialog.id);
    }
    setViolationDialog(null);
  }

  return (
    <>
    <table className="data-table">
      <thead>
        <tr>
          <th>{messages.guards.fullName}</th>
          <th>{messages.submissions.status}</th>
          <th>{messages.submissions.submittedAt}</th>
          <th>{messages.submissions.viewDetails}</th>
          {canFillConstraints && <th>{messages.common.actions}</th>}
          <th className="violation-col" aria-label="חריגות"></th>
        </tr>
      </thead>
      <tbody>
        {sortedSubmissions.map((s) => {
          const detail = detailsByUser[s.user_id];
          const expanded = expandedUser === s.user_id;
          const warnings = detail ? computeAdminWarnings(detail, rules) : [];
          return (
            <Fragment key={s.user_id}>
              <tr>
                <td>
                  {s.full_name || s.user_id}
                  {s.has_telegram === false && (
                    <span
                      className="badge badge-danger no-telegram-badge"
                      title={messages.submissions.noTelegramTitle}
                    >
                      {messages.submissions.noTelegram}
                    </span>
                  )}
                </td>
                <td>
                  <span className={`badge ${s.submitted_at ? 'badge-success' : 'badge-warning'}`}>
                    {s.submitted_at ? messages.submissions.submitted : messages.submissions.missing}
                  </span>
                </td>
                <td>{s.submitted_at ? new Date(s.submitted_at).toLocaleString('he-IL') : '—'}</td>
                <td>
                  {detail ? (
                    <button
                      className="btn-sm"
                      onClick={() => setExpandedUser(expanded ? null : s.user_id)}
                    >
                      {expanded ? 'הסתר' : 'הצג'}
                    </button>
                  ) : (
                    <span className="text-muted">—</span>
                  )}
                </td>
                {canFillConstraints && (
                  <td className="actions-cell">
                    <button
                      className="btn btn-sm btn-secondary"
                      onClick={() => navigate(`/guards/${s.user_id}/constraints`)}
                    >
                      {messages.guards.fillConstraints}
                    </button>
                  </td>
                )}
                <td className="violation-col">
                  {warnings.length > 0 && !detail.violation_acknowledged && (
                    <button
                      type="button"
                      className="violation-dot"
                      title={messages.submissions.violationDotTitle}
                      onClick={() =>
                        setViolationDialog({
                          id: detail.id,
                          name: s.full_name || s.user_id,
                          warnings,
                        })
                      }
                    >
                      {warnings.length}
                    </button>
                  )}
                </td>
              </tr>
              {expanded && detail && (
                <tr className="detail-row">
                  <td colSpan={colCount}>
                    <div className="detail-content">
                      {warnings.length > 0 && (
                        <div className="detail-warnings">
                          <strong>{messages.submissions.warningsTitle}</strong>
                          <ul>
                            {warnings.map((w, wi) => (
                              <li key={wi}>{w}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {detail.days?.map((day, idx) => (
                        <div key={idx} className="detail-day">
                          <strong>{DAY_NAMES[idx] || `יום ${idx}`}</strong>
                          {day.shift_windows && day.shift_windows.length > 0 ? (
                            <ul>
                              {day.shift_windows.map((sw, si) => (
                                <li key={si}>
                                  {SHIFT_LABELS[sw.shift_type] || sw.shift_type}: {sw.start_time} - {sw.end_time}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <span className="text-muted"> לא זמין</span>
                          )}
                        </div>
                      ))}
                      {detail.general_notes && (
                        <div className="detail-notes">
                          <strong>הערות:</strong> {detail.general_notes}
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
    {violationDialog && (
      <ConfirmDialog
        title={messages.submissions.violationDialogTitle}
        message={
          <>
            {violationDialog.name} — {messages.submissions.warningsTitle}
            <br />
            {violationDialog.warnings.map((w, i) => (
              <span key={i}>• {w}<br /></span>
            ))}
          </>
        }
        confirmLabel={messages.submissions.violationAcknowledge}
        onConfirm={handleConfirmAcknowledge}
        onCancel={() => setViolationDialog(null)}
      />
    )}
    </>
  );
}
