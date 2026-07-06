import { useState } from 'react';
import { DAY_NAMES, SHIFT_LABELS } from '../utils/guardMessages';

export default function SubmissionsTable({ submissions, userNames = {} }) {
  const [expandedUser, setExpandedUser] = useState(null);

  if (!submissions.length) {
    return <p className="empty-state">אין מאבטחים ששלחו אילוצים</p>;
  }

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>שם מלא</th>
          <th>תאריך הגשה</th>
          <th>פירוט</th>
        </tr>
      </thead>
      <tbody>
        {submissions.map((sub) => (
          <>
            <tr key={sub.user_id}>
              <td>{sub.full_name || userNames[sub.user_id] || sub.user_id}</td>
              <td>{new Date(sub.submitted_at).toLocaleString('he-IL')}</td>
              <td>
                <button
                  className="btn-sm"
                  onClick={() => setExpandedUser(expandedUser === sub.user_id ? null : sub.user_id)}
                >
                  {expandedUser === sub.user_id ? 'הסתר' : 'הצג'}
                </button>
              </td>
            </tr>
            {expandedUser === sub.user_id && (
              <tr key={`${sub.user_id}-detail`} className="detail-row">
                <td colSpan={3}>
                  <div className="detail-content">
                    {sub.days?.map((day, idx) => (
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
                    {sub.general_notes && (
                      <div className="detail-notes">
                        <strong>הערות:</strong> {sub.general_notes}
                      </div>
                    )}
                  </div>
                </td>
              </tr>
            )}
          </>
        ))}
      </tbody>
    </table>
  );
}