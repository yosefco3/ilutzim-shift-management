import { useState } from 'react';
import { changeAdminPassword } from '../api/adminApiClient';
import { useToast } from './Toast';
import messages from '../utils/messages';

const t = messages.settings.changePassword;

// Client-side policy mirror of the backend (auth_service.password_strength_errors):
// at least 10 chars, with a letter and a digit.
function isStrong(pw) {
  return pw.length >= 10 && /[a-zA-Zא-ת]/.test(pw) && /\d/.test(pw);
}

export default function ChangePasswordForm() {
  const toast = useToast();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setCurrent('');
    setNext('');
    setConfirm('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!current || !next || !confirm) {
      toast.error(t.required);
      return;
    }
    if (next !== confirm) {
      toast.error(t.mismatch);
      return;
    }
    if (!isStrong(next)) {
      toast.error(t.weak);
      return;
    }

    setSubmitting(true);
    try {
      await changeAdminPassword(current, next);
      toast.success(t.success);
      reset();
    } catch (err) {
      toast.error(err.message || t.weak);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="card settings-item change-password-form" onSubmit={handleSubmit}>
      <div className="settings-info">
        <strong>{t.title}</strong>
      </div>
      <div className="change-password-fields">
        <input
          type="password"
          className="settings-input"
          placeholder={t.current}
          aria-label={t.current}
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
        />
        <input
          type="password"
          className="settings-input"
          placeholder={t.newPass}
          aria-label={t.newPass}
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
        />
        <input
          type="password"
          className="settings-input"
          placeholder={t.confirm}
          aria-label={t.confirm}
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? messages.common.loading : t.submit}
        </button>
      </div>
    </form>
  );
}
