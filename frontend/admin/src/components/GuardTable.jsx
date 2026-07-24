import messages, { ROLE_LABELS } from '../utils/messages';
import { sortGuardsByName } from '../utils/sorting';

// Stage 3 (attendance): read-only GPS-consent indicator, hidden when the
// attendance feature is compiled out (same flag convention as the builder).
const ATTENDANCE_ENABLED = import.meta.env.VITE_ATTENDANCE_ENABLED !== 'false';

function gpsConsentBadge(guard) {
  if (!ATTENDANCE_ENABLED || !guard.gps_consent_at) return null;
  const day = new Date(guard.gps_consent_at).toLocaleDateString('he-IL');
  return (
    <span
      className="gps-consent-badge"
      title={`${messages.guards.gpsConsent}: ${day}`}
      aria-label={messages.guards.gpsConsent}
    >
      {' '}📍
    </span>
  );
}

export default function GuardTable({ guards, onEdit, onToggle, onDelete }) {
  if (!guards.length) {
    return <p className="empty-state">{messages.guards.empty}</p>;
  }

  const sortedGuards = sortGuardsByName(guards);

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th className="row-number-col">{messages.guards.rowNumber}</th>
          <th>{messages.guards.name}</th>
          <th>{messages.guards.phone}</th>
          <th>{messages.guards.role}</th>
          <th>{messages.guards.active}</th>
          <th>{messages.common.actions}</th>
        </tr>
      </thead>
      <tbody>
        {sortedGuards.map((g, i) => (
          <tr key={g.id} className={g.is_active ? undefined : 'row-inactive'}>
            <td className="row-number-col">{i + 1}</td>
            <td>{g.first_name} {g.last_name}{gpsConsentBadge(g)}</td>
            <td>{g.phone_number || '—'}</td>
            <td>{(g.roles || []).map((r) => ROLE_LABELS[r] || r).join(', ') || '—'}</td>
            <td>
              <span className={`badge ${g.is_active ? 'badge-success' : 'badge-secondary'}`}>
                {g.is_active ? messages.common.yes : messages.common.no}
              </span>
            </td>
            <td className="actions-cell">
              <button className="btn btn-sm btn-primary" onClick={() => onEdit(g)}>
                {messages.common.edit}
              </button>
              <button className="btn btn-sm btn-secondary" onClick={() => onToggle(g)}>
                {g.is_active ? messages.guards.deactivate : messages.guards.activate}
              </button>
              <button className="btn btn-sm btn-danger" onClick={() => onDelete(g)}>
                {messages.common.delete}
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}