/**
 * ReinforcementDialog — manage this week's reinforcement guards (מתגברים).
 *
 * One dialog: the current week's cards (with removal — which also deletes
 * the one-off guard and his assignments) + an add form (name required;
 * phone/supervisor/note optional). Reinforcements are external one-off
 * helpers: no punching, no payroll, invisible on the guards page. The
 * reinforcements REPORT lives on its own page (/actual/report).
 */
import { useState } from 'react';
import ConfirmDialog from '../ConfirmDialog';
import messages from '../../utils/messages';

export default function ReinforcementDialog({
  open,
  reinforcements = [],
  onAdd,
  onRemove,
  onClose,
}) {
  const m = messages.actualBoard.reinforcements;
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [phone, setPhone] = useState('');
  const [supervisor, setSupervisor] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(null);

  if (!open) return null;

  const canAdd = firstName.trim() && lastName.trim() && !saving;

  const handleAdd = async () => {
    setSaving(true);
    try {
      const ok = await onAdd({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone_number: phone.trim() || null,
        note: note.trim() || null,
        supervisor_name: supervisor.trim() || null,
      });
      if (ok) {
        setFirstName('');
        setLastName('');
        setPhone('');
        setSupervisor('');
        setNote('');
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content actual-pos-dialog"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="modal-title">{m.dialogTitle}</h3>
        <p className="reinforcement-hint">{m.dialogHint}</p>

        <div className="reinforcement-list">
          <div className="reinforcement-list-title">{m.listTitle}</div>
          {reinforcements.length === 0 ? (
            <p className="reinforcement-empty">{m.emptyList}</p>
          ) : (
            reinforcements.map((r) => (
              <div key={r.id} className="reinforcement-row">
                <span className="reinforcement-name">
                  {r.full_name}
                  {r.phone_number && (
                    <span className="reinforcement-phone"> · {r.phone_number}</span>
                  )}
                  {r.supervisor_name && (
                    <span className="reinforcement-note"> · מפקח: {r.supervisor_name}</span>
                  )}
                  {r.note && <span className="reinforcement-note"> · {r.note}</span>}
                </span>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setConfirmRemove(r)}
                >
                  {messages.common.delete}
                </button>
              </div>
            ))
          )}
        </div>

        <div className="reinforcement-form">
          <label className="actual-pos-field">
            {m.firstName}
            <input
              type="text"
              value={firstName}
              autoFocus
              onChange={(e) => setFirstName(e.target.value)}
            />
          </label>
          <label className="actual-pos-field">
            {m.lastName}
            <input
              type="text"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
            />
          </label>
          <label className="actual-pos-field">
            {m.phone}
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </label>
          <label className="actual-pos-field">
            {m.supervisor}
            <input
              type="text"
              value={supervisor}
              onChange={(e) => setSupervisor(e.target.value)}
            />
          </label>
          <label className="actual-pos-field">
            {m.note}
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
        </div>

        <div className="modal-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={!canAdd}
            onClick={handleAdd}
          >
            ➕ {m.add}
          </button>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            {messages.common.cancel}
          </button>
        </div>

        {confirmRemove && (
          <ConfirmDialog
            title={m.confirmDeleteTitle}
            message={m.confirmDelete(confirmRemove.full_name)}
            confirmLabel={messages.common.delete}
            onConfirm={() => {
              onRemove(confirmRemove);
              setConfirmRemove(null);
            }}
            onCancel={() => setConfirmRemove(null)}
          />
        )}
      </div>
    </div>
  );
}
