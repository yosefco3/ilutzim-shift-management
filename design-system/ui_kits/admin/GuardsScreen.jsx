// Guards management — table + add/edit form + delete confirm.
const {
  Button: KitBtn_g, Badge: KitBadge_g, Card: KitCard_g, Dialog: KitDialog_g,
  Field: KitField_g, TextInput: KitInput_g, Select: KitSelect_g,
} = window.IlutsimDesignSystem_f4254f;

const ROLE_OPTS = [
  { value: 'AHMASH', label: 'אחמ"ש' },
  { value: 'BASIC_GUARD', label: 'מאבטח בסיסי' },
  { value: 'LEVEL_B', label: "מאבטח רמה ב'" },
  { value: 'NINE_HOURS', label: 'מאבטח 9 שעות' },
  { value: 'UNARMED', label: 'לא חמוש' },
  { value: 'CHECKER', label: 'בודק' },
];

function GuardForm({ guard, onSave, onCancel }) {
  const [form, setForm] = React.useState({
    first_name: guard?.first_name || '', last_name: guard?.last_name || '',
    phone_number: guard?.phone_number || '', role: guard?.role || 'AHMASH',
  });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  return (
    <KitCard_g style={{ marginBottom: '1rem' }}>
      <h3 style={{ margin: '0 0 1rem', fontSize: 'var(--fs-lg)', fontWeight: 'var(--fw-heading)' }}>
        {guard ? 'עריכת מאבטח' : 'הוספת מאבטח'}
      </h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 1rem' }}>
        <KitField_g label="שם פרטי"><KitInput_g value={form.first_name} onChange={set('first_name')} /></KitField_g>
        <KitField_g label="שם משפחה"><KitInput_g value={form.last_name} onChange={set('last_name')} /></KitField_g>
        <KitField_g label="טלפון"><KitInput_g value={form.phone_number} onChange={set('phone_number')} /></KitField_g>
        <KitField_g label="תפקיד">
          <KitSelect_g value={form.role} onChange={set('role')}>
            {ROLE_OPTS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </KitSelect_g>
        </KitField_g>
      </div>
      <div style={{ display: 'flex', gap: '0.6rem', marginTop: '0.5rem' }}>
        <KitBtn_g variant="primary" onClick={() => onSave(form)}>שמור</KitBtn_g>
        <KitBtn_g variant="secondary" onClick={onCancel}>ביטול</KitBtn_g>
      </div>
    </KitCard_g>
  );
}

function GuardsScreen({ toast }) {
  const { ROLE_LABELS } = window.KitData;
  const [guards, setGuards] = React.useState(() => window.KitData.guards.map((g) => ({ ...g })));
  const [showForm, setShowForm] = React.useState(false);
  const [editing, setEditing] = React.useState(null);
  const [confirm, setConfirm] = React.useState(null);

  const save = (data) => {
    if (editing) {
      setGuards((gs) => gs.map((g) => (g.id === editing.id ? { ...g, ...data } : g)));
    } else {
      setGuards((gs) => [...gs, { id: Date.now(), is_active: true, ...data }]);
    }
    setShowForm(false); setEditing(null);
    toast && toast('success', 'הפעולה בוצעה בהצלחה');
  };

  return (
    <div>
      <div className="page-header">
        <h2>ניהול מאבטחים</h2>
        {!showForm && (
          <KitBtn_g variant="primary" onClick={() => { setEditing(null); setShowForm(true); }}>הוספת מאבטח</KitBtn_g>
        )}
      </div>
      {showForm && <GuardForm guard={editing} onSave={save} onCancel={() => { setShowForm(false); setEditing(null); }} />}
      <table className="data-table">
        <thead>
          <tr><th>שם מלא</th><th>טלפון</th><th>תפקיד</th><th>פעיל</th><th>פעולות</th></tr>
        </thead>
        <tbody>
          {guards.map((g) => (
            <tr key={g.id}>
              <td>{g.first_name} {g.last_name}</td>
              <td>{g.phone_number || '—'}</td>
              <td>{ROLE_LABELS[g.role] || g.role}</td>
              <td><KitBadge_g tone={g.is_active ? 'active' : 'inactive'}>{g.is_active ? 'פעיל' : 'לא פעיל'}</KitBadge_g></td>
              <td>
                <div className="actions-cell">
                  <KitBtn_g variant="primary" size="sm" onClick={() => { setEditing(g); setShowForm(true); }}>ערוך</KitBtn_g>
                  <KitBtn_g variant="secondary" size="sm">מילוי אילוצים</KitBtn_g>
                  <KitBtn_g variant="secondary" size="sm" onClick={() => {
                    setGuards((gs) => gs.map((x) => (x.id === g.id ? { ...x, is_active: !x.is_active } : x)));
                  }}>{g.is_active ? 'השבת' : 'הפעל'}</KitBtn_g>
                  <KitBtn_g variant="danger" size="sm" onClick={() => setConfirm(g)}>מחק</KitBtn_g>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {confirm && (
        <KitDialog_g
          message="האם למחוק את המאבטח לצמיתות? פעולה זו אינה ניתנת לביטול."
          confirmLabel="מחק"
          onConfirm={() => { setGuards((gs) => gs.filter((x) => x.id !== confirm.id)); setConfirm(null); toast && toast('success', 'המאבטח נמחק'); }}
          onCancel={() => setConfirm(null)}
        />
      )}
    </div>
  );
}
window.GuardsScreen = GuardsScreen;
