// Weeks management — lifecycle cards (closed → open → locked → published).
const { Button: KitBtn_w, Badge: KitBadge_w, Card: KitCard_w, Dialog: KitDialog_w } = window.IlutsimDesignSystem_f4254f;

const WEEK_CFG = {
  closed:    { tone: 'closed',    icon: '⏳', label: 'סגור' },
  open:      { tone: 'open',      icon: '🔓', label: 'פתוח להגשה' },
  locked:    { tone: 'locked',    icon: '🔒', label: 'סגור להגשה' },
  published: { tone: 'published', icon: '📢', label: 'פורסם' },
};

function WeekActions({ status, onAction }) {
  return (
    <div className="week-card-buttons">
      {(status === 'locked' || status === 'closed') && (
        <KitBtn_w variant="primary" size="sm" icon="🟢" onClick={() => onAction('open')}>פתח להגשה</KitBtn_w>
      )}
      {status === 'open' && (
        <KitBtn_w variant="secondary" size="sm" icon="🔒" onClick={() => onAction('lock')}>נעל</KitBtn_w>
      )}
      {status === 'locked' && (
        <KitBtn_w variant="success" size="sm" icon="📢" onClick={() => onAction('publish')}>פרסם</KitBtn_w>
      )}
      {status !== 'published' && (
        <KitBtn_w variant="danger" size="sm" icon="🗑️" onClick={() => onAction('delete')}>מחק</KitBtn_w>
      )}
    </div>
  );
}

function WeeksScreen({ toast }) {
  const [weeks, setWeeks] = React.useState(() => window.KitData.weeks.map((w) => ({ ...w })));
  const [confirm, setConfirm] = React.useState(null);

  const setStatus = (id, status, msg) => {
    setWeeks((ws) => ws.map((w) => (w.id === id ? { ...w, status } : w)));
    toast && toast('success', msg);
  };

  const handleAction = (week, action) => {
    if (action === 'open') setStatus(week.id, 'open', 'השבוע נפתח להגשה בהצלחה');
    if (action === 'lock') setStatus(week.id, 'locked', 'השבוע ננעל בהצלחה');
    if (action === 'publish') setStatus(week.id, 'published', 'השבוע פורסם בהצלחה — שבוע חדש נוצר אוטומטית');
    if (action === 'delete') setConfirm(week);
  };

  return (
    <div>
      <div className="page-header">
        <h2>ניהול שבועות</h2>
        <KitBtn_w variant="outline" size="sm">רענון</KitBtn_w>
      </div>
      <div className="week-cards">
        {weeks.map((w) => {
          const cfg = WEEK_CFG[w.status];
          return (
            <KitCard_w key={w.id} interactive>
              <div className="week-card-header">
                <span className="week-card-date">📅 {w.start_date} — {w.end_date}</span>
                <span className="week-card-label">{w.week_label}</span>
              </div>
              <span className="week-card-submissions">{w.submission_count} הגשות</span>
              <div className="week-card-actions">
                <KitBadge_w tone={cfg.tone} icon={cfg.icon}>{cfg.label}</KitBadge_w>
                <WeekActions status={w.status} onAction={(a) => handleAction(w, a)} />
              </div>
            </KitCard_w>
          );
        })}
      </div>
      {confirm && (
        <KitDialog_w
          title="מחק שבוע"
          message="האם למחוק את השבוע? פעולה זו אינה ניתנת לביטול."
          confirmLabel="מחק"
          onConfirm={() => {
            setWeeks((ws) => ws.filter((w) => w.id !== confirm.id));
            setConfirm(null);
            toast && toast('success', 'השבוע נמחק בהצלחה');
          }}
          onCancel={() => setConfirm(null)}
        />
      )}
    </div>
  );
}
window.WeeksScreen = WeeksScreen;
