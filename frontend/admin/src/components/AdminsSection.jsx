import { useEffect, useState } from 'react';
import {
  listAdmins,
  createAdmin,
  setAdminActive,
  resetAdminPassword,
  changeAdminRole,
} from '../api/adminApiClient';
import ConfirmDialog from './ConfirmDialog';
import { useToast } from './Toast';
import messages from '../utils/messages';

const t = messages.settings.admins;

// Client-side policy mirror of the backend (auth_service.password_strength_errors):
// at least 10 chars, with a letter and a digit.
function isStrong(pw) {
  return pw.length >= 10 && /[a-zA-Zא-ת]/.test(pw) && /\d/.test(pw);
}

const ROLE_LABELS = {
  super_admin: t.roleSuperAdmin,
  admin: t.roleAdmin,
  viewer: t.roleViewer,
};

// Roles the super admin may hand out — mirrors the backend's ASSIGNABLE_ROLES
// (SUPER_ADMIN is never assignable). Per-route permissions per role are a
// future feature; for now VIEWER is groundwork.
const ASSIGNABLE_ROLES = ['admin', 'viewer'];

export default function AdminsSection() {
  const toast = useToast();
  const [admins, setAdmins] = useState([]);
  const [loaded, setLoaded] = useState(false);

  // Add-admin form
  const [showForm, setShowForm] = useState(false);
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('admin');
  const [submitting, setSubmitting] = useState(false);

  // Row actions
  const [resetTarget, setResetTarget] = useState(null); // admin id with the reset input open
  const [resetValue, setResetValue] = useState('');
  const [deactivateTarget, setDeactivateTarget] = useState(null); // admin pending confirm

  const refresh = async () => {
    try {
      const data = await listAdmins();
      setAdmins(data.admins || []);
    } catch (err) {
      toast.error(err.message || t.loadError);
    } finally {
      setLoaded(true);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!fullName.trim() || !email.trim() || !password) {
      toast.error(t.required);
      return;
    }
    if (!isStrong(password)) {
      toast.error(messages.settings.changePassword.weak);
      return;
    }
    setSubmitting(true);
    try {
      await createAdmin({
        email: email.trim(),
        fullName: fullName.trim(),
        password,
        role,
      });
      toast.success(t.createSuccess);
      setFullName('');
      setEmail('');
      setPassword('');
      setRole('admin');
      setShowForm(false);
      await refresh();
    } catch (err) {
      toast.error(err.message || t.createError);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSetActive = async (admin, active) => {
    setDeactivateTarget(null);
    try {
      await setAdminActive(admin.id, active);
      toast.success(active ? t.activated : t.deactivated);
      await refresh();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleChangeRole = async (admin, newRole) => {
    if (newRole === admin.role) return;
    try {
      await changeAdminRole(admin.id, newRole);
      toast.success(t.roleChanged);
      await refresh();
    } catch (err) {
      toast.error(err.message);
      await refresh(); // snap the select back to the server state
    }
  };

  const handleReset = async (admin) => {
    if (!isStrong(resetValue)) {
      toast.error(messages.settings.changePassword.weak);
      return;
    }
    try {
      await resetAdminPassword(admin.id, resetValue);
      toast.success(t.resetSuccess);
      setResetTarget(null);
      setResetValue('');
    } catch (err) {
      toast.error(err.message);
    }
  };

  return (
    <div className="card settings-group admins-section">
      {loaded && (
        <table className="data-table">
          <thead>
            <tr>
              <th>{t.colName}</th>
              <th>{t.colEmail}</th>
              <th>{t.colRole}</th>
              <th>{t.colStatus}</th>
              <th>{t.colActions}</th>
            </tr>
          </thead>
          <tbody>
            {admins.map((a) => (
              <tr key={a.id}>
                <td>{a.full_name}</td>
                <td dir="ltr">{a.email}</td>
                <td>
                  {a.role === 'super_admin' ? (
                    ROLE_LABELS[a.role]
                  ) : (
                    <select
                      className="settings-input admins-role-select"
                      aria-label={t.colRole}
                      value={a.role}
                      onChange={(e) => handleChangeRole(a, e.target.value)}
                    >
                      {ASSIGNABLE_ROLES.map((r) => (
                        <option key={r} value={r}>
                          {ROLE_LABELS[r]}
                        </option>
                      ))}
                    </select>
                  )}
                </td>
                <td>
                  <span className={`badge ${a.is_active ? 'badge-active' : 'badge-inactive'}`}>
                    {a.is_active ? t.active : t.inactive}
                  </span>
                </td>
                <td>
                  {/* Super-admin rows (incl. self) have no actions — the backend
                      blocks deactivation/self-reset anyway [EDGE E2/E3/E6]. */}
                  {a.role !== 'super_admin' && (
                    <div className="admins-row-actions">
                      {a.is_active ? (
                        <button
                          type="button"
                          className="btn btn-sm btn-danger"
                          onClick={() => setDeactivateTarget(a)}
                        >
                          {t.deactivate}
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-sm btn-secondary"
                          onClick={() => handleSetActive(a, true)}
                        >
                          {t.activate}
                        </button>
                      )}
                      {resetTarget === a.id ? (
                        <>
                          <input
                            type="password"
                            className="settings-input"
                            placeholder={t.newPassword}
                            aria-label={t.newPassword}
                            autoComplete="new-password"
                            value={resetValue}
                            onChange={(e) => setResetValue(e.target.value)}
                          />
                          <button
                            type="button"
                            className="btn btn-sm btn-primary"
                            onClick={() => handleReset(a)}
                          >
                            {t.resetConfirm}
                          </button>
                          <button
                            type="button"
                            className="btn btn-sm btn-secondary"
                            onClick={() => {
                              setResetTarget(null);
                              setResetValue('');
                            }}
                          >
                            {messages.common.cancel}
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-sm btn-secondary"
                          onClick={() => {
                            setResetTarget(a.id);
                            setResetValue('');
                          }}
                        >
                          {t.resetPassword}
                        </button>
                      )}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showForm ? (
        <form className="admins-create-form" onSubmit={handleCreate}>
          <input
            className="settings-input"
            placeholder={t.fullName}
            aria-label={t.fullName}
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />
          <input
            className="settings-input"
            type="email"
            dir="ltr"
            placeholder={t.email}
            aria-label={t.email}
            autoComplete="off"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            className="settings-input"
            type="password"
            placeholder={t.initialPassword}
            aria-label={t.initialPassword}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <select
            className="settings-input admins-role-select"
            aria-label={t.roleSelect}
            value={role}
            onChange={(e) => setRole(e.target.value)}
          >
            {ASSIGNABLE_ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r]}
              </option>
            ))}
          </select>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? messages.common.loading : t.createSubmit}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setShowForm(false)}
          >
            {messages.common.cancel}
          </button>
        </form>
      ) : (
        <div className="admins-add-action">
          <button type="button" className="btn btn-primary" onClick={() => setShowForm(true)}>
            {t.addAdmin}
          </button>
        </div>
      )}

      {deactivateTarget && (
        <ConfirmDialog
          title={t.deactivateTitle}
          message={t.deactivateMessage.replace('{name}', deactivateTarget.full_name)}
          confirmLabel={t.deactivate}
          onConfirm={() => handleSetActive(deactivateTarget, false)}
          onCancel={() => setDeactivateTarget(null)}
        />
      )}
    </div>
  );
}
