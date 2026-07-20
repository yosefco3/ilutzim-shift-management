import { useState, useEffect, useCallback } from 'react';
import {
  listProfiles,
  createProfile,
  updateProfile,
  duplicateProfile,
  deleteProfile,
  getProfileDeleteImpact,
  setDefaultProfile,
} from '../../api/builderApiClient';
import { useToast } from '../../components/Toast';
import ConfirmDialog from '../../components/ConfirmDialog';
import messages from '../../utils/messages';

const EMPTY_FORM = { name: '' };

export default function ProfilesPage() {
  const toast = useToast();
  const m = messages.profiles;

  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editing, setEditing] = useState(null); // profile being edited (modal)
  const [confirmDelete, setConfirmDelete] = useState(null); // profile pending delete
  // Impact of the pending delete { weeks, assignments } — drives the warning text.
  const [deleteImpact, setDeleteImpact] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setProfiles(await listProfiles());
    } catch (err) {
      toast.error(err.message || messages.common.error);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    try {
      await createProfile({ name: form.name.trim() });
      setForm(EMPTY_FORM);
      toast.success(m.created);
      await load();
    } catch (err) {
      toast.error(err.message || messages.common.error);
    }
  };

  const handleSetDefault = async (p) => {
    try {
      await setDefaultProfile(p.id);
      toast.success(m.defaultSet);
      await load();
    } catch (err) {
      toast.error(err.message || messages.common.error);
    }
  };

  const handleDuplicate = async (p) => {
    try {
      await duplicateProfile(p.id);
      toast.success(m.duplicated);
      await load();
    } catch (err) {
      toast.error(err.message || messages.common.error);
    }
  };

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    if (!editing.name.trim()) return;
    try {
      await updateProfile(editing.id, { name: editing.name.trim() });
      setEditing(null);
      toast.success(m.updated);
      await load();
    } catch (err) {
      toast.error(err.message || messages.common.error);
    }
  };

  // Open the confirm dialog, first fetching how much the delete would wipe so we
  // can warn with specifics. A failed impact check still lets the delete proceed
  // (the backend re-guards) — it just falls back to the generic message.
  const askDelete = async (p) => {
    setDeleteImpact(null);
    setConfirmDelete(p);
    try {
      setDeleteImpact(await getProfileDeleteImpact(p.id));
    } catch {
      // keep the generic message; the delete itself is still guarded server-side
    }
  };

  const handleDelete = async () => {
    const p = confirmDelete;
    setConfirmDelete(null);
    setDeleteImpact(null);
    try {
      await deleteProfile(p.id);
      toast.success(m.deleted);
      await load();
    } catch (err) {
      toast.error(err.message || messages.common.error);
    }
  };

  // Warn with the cascade impact when the profile carries real schedules.
  const deleteMessage =
    deleteImpact && deleteImpact.weeks > 0
      ? m.deleteMsgImpact(deleteImpact.weeks, deleteImpact.assignments)
      : m.deleteMsg;

  if (loading) return <div className="loading">{messages.common.loading}</div>;

  return (
    <div className="page">
      <div className="page-header">
        <h2>{m.title}</h2>
        <p className="page-subtitle">{m.subtitle}</p>
      </div>

      <form className="profile-create-form" onSubmit={handleCreate}>
        <input
          type="text"
          aria-label={m.name}
          placeholder={m.namePlaceholder}
          value={form.name}
          onChange={(e) => setForm({ name: e.target.value })}
        />
        <button type="submit" className="btn btn-primary" disabled={!form.name.trim()}>
          {m.newProfile}
        </button>
      </form>

      {!profiles.length ? (
        <p className="empty-state">{m.empty}</p>
      ) : (
        <div className="profile-cards">
          {profiles.map((p) => (
            <div key={p.id} className="profile-card">
              <div className="profile-card-header">
                <span className="profile-card-name">{p.name}</span>
                {p.is_default && (
                  <span className="profile-card-default">{m.default}</span>
                )}
                {p.is_base && (
                  <span className="profile-card-base" title={m.baseHint}>{m.base}</span>
                )}
              </div>
              <p className="profile-card-positions">
                {p.position_count > 0 ? m.positionsCount(p.position_count) : m.noPositionsYet}
              </p>
              <div className="profile-card-actions">
                {!p.is_default && (
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleSetDefault(p)}
                  >
                    {m.makeDefault}
                  </button>
                )}
                <button className="btn btn-secondary btn-sm" onClick={() => handleDuplicate(p)}>
                  {m.duplicate}
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => setEditing({ id: p.id, name: p.name })}
                >
                  {m.edit}
                </button>
                {/* The base template is permanent — no delete button for it. */}
                {!p.is_base && (
                  <button className="btn btn-danger btn-sm" onClick={() => askDelete(p)}>
                    {m.delete}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && (
        <div className="modal-overlay" onClick={() => setEditing(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal-title">{m.edit}</h3>
            <form onSubmit={handleSaveEdit}>
              <div className="form-group">
                <label htmlFor="edit-profile-name">{m.name}</label>
                <input
                  id="edit-profile-name"
                  type="text"
                  aria-label={`${m.edit}-${m.name}`}
                  autoFocus
                  value={editing.name}
                  onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                />
              </div>
              <div className="modal-actions">
                <button type="submit" className="btn btn-primary" disabled={!editing.name.trim()}>
                  {messages.common.save}
                </button>
                <button type="button" className="btn btn-secondary" onClick={() => setEditing(null)}>
                  {messages.common.cancel}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!confirmDelete}
        title={m.deleteTitle}
        message={deleteMessage}
        confirmLabel={m.delete}
        onConfirm={handleDelete}
        onCancel={() => { setConfirmDelete(null); setDeleteImpact(null); }}
      />
    </div>
  );
}
