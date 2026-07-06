// Submissions overview — who submitted for the open week, expandable per-guard
// availability detail.
const { Badge: KitBadge_s, Select: KitSelect_s, Button: KitBtn_s } = window.IlutsimDesignSystem_f4254f;

function SubmissionsScreen() {
  const { submissions, DAY_NAMES, SHIFT_LABELS } = window.KitData;
  const [expanded, setExpanded] = React.useState(1);

  return (
    <div>
      <div className="page-header">
        <h2>דיווחים שהתקבלו</h2>
      </div>
      <div style={{ maxWidth: 280, marginBottom: '1rem' }}>
        <KitSelect_s defaultValue="24">
          <option value="24">שבוע 25 (פתוח)</option>
          <option value="23">שבוע 24 (נעול)</option>
        </KitSelect_s>
      </div>
      <table className="data-table">
        <thead>
          <tr><th>שם מלא</th><th>סטטוס</th><th>תאריך הגשה</th><th>צפה בפירוט</th></tr>
        </thead>
        <tbody>
          {submissions.map((s) => {
            const isOpen = expanded === s.user_id;
            const hasDetail = s.submitted_at && s.days.length > 0;
            return (
              <React.Fragment key={s.user_id}>
                <tr>
                  <td>{s.full_name}</td>
                  <td><KitBadge_s tone={s.submitted_at ? 'submitted' : 'missing'}>{s.submitted_at ? 'שלח' : 'לא שלח'}</KitBadge_s></td>
                  <td>{s.submitted_at ? new Date(s.submitted_at).toLocaleString('he-IL') : '—'}</td>
                  <td>
                    {hasDetail
                      ? <KitBtn_s variant="ghost" size="sm" onClick={() => setExpanded(isOpen ? null : s.user_id)}>{isOpen ? 'הסתר' : 'הצג'}</KitBtn_s>
                      : <span className="text-muted">—</span>}
                  </td>
                </tr>
                {isOpen && hasDetail && (
                  <tr>
                    <td colSpan={4}>
                      <div className="detail-content">
                        {s.days.map((day, idx) => (
                          <div className="detail-day" key={idx}>
                            <strong>{DAY_NAMES[idx]}</strong>
                            {day.shift_windows.length > 0 ? (
                              <ul>
                                {day.shift_windows.map((sw, i) => (
                                  <li key={i}>{SHIFT_LABELS[sw.shift_type]}: {sw.start_time}–{sw.end_time}</li>
                                ))}
                              </ul>
                            ) : <span className="text-muted" style={{ fontSize: 'var(--fs-xs)' }}> לא זמין</span>}
                          </div>
                        ))}
                      </div>
                      {s.general_notes && (
                        <div style={{ marginTop: '0.6rem', fontSize: 'var(--fs-sm)', color: 'var(--text-muted)' }}>
                          <strong>הערות:</strong> {s.general_notes}
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
window.SubmissionsScreen = SubmissionsScreen;
