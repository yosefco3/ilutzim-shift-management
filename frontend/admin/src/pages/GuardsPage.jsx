import { useState } from 'react';
import { useGuards } from '../hooks/useGuards';
import GuardTable from '../components/GuardTable';
import GuardForm from '../components/GuardForm';
import GuardSearch from '../components/GuardSearch';
import ConfirmDialog from '../components/ConfirmDialog';
import { useToast } from '../components/Toast';
import { guardFullName, matchesGuardSearch } from '../utils/sorting';
import messages from '../utils/messages';

export default function GuardsPage() {
  const { guards, loading, createGuard, updateGuard, toggleGuard, deleteGuard } = useGuards();
  const toast = useToast();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [search, setSearch] = useState('');

  const [saving, setSaving] = useState(false);

  const handleSave = async (data) => {
    try {
      setSaving(true);
      if (editing) {
        await updateGuard(editing.id, data);
      } else {
        await createGuard(data);
      }
      setShowForm(false);
      setEditing(null);
      toast.success(messages.common.success);
    } catch (err) {
      toast.error(messages.common.error + ': ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (guard) => {
    setEditing(guard);
    setShowForm(true);
  };

  const handleToggle = async (guard) => {
    try {
      await toggleGuard(guard.id, !guard.is_active);
      toast.success(messages.common.success);
    } catch (err) {
      toast.error(messages.common.error + ': ' + err.message);
    }
  };

  const handleDelete = async () => {
    if (confirmDelete) {
      try {
        await deleteGuard(confirmDelete.id);
        setConfirmDelete(null);
        toast.success(messages.common.success);
      } catch (err) {
        toast.error(messages.common.error + ': ' + err.message);
      }
    }
  };

  if (loading) return <div className="loading">{messages.common.loading}</div>;

  const filteredGuards = guards.filter((g) => matchesGuardSearch(guardFullName(g), search));

  return (
    <div className="page">
      <div className="page-header">
        <h2>{messages.guards.title}</h2>
        {!showForm && (
          <button className="btn btn-primary" onClick={() => { setEditing(null); setShowForm(true); }}>
            {messages.guards.addTitle}
          </button>
        )}
      </div>

      {showForm && (
        <GuardForm
          guard={editing}
          onSave={handleSave}
          onCancel={() => { setShowForm(false); setEditing(null); }}
        />
      )}

      {guards.length > 0 && <GuardSearch value={search} onChange={setSearch} />}

      {search.trim() && filteredGuards.length === 0 ? (
        <p className="empty-state">{messages.common.noSearchResults}</p>
      ) : (
        <GuardTable
          guards={filteredGuards}
          onEdit={handleEdit}
          onToggle={handleToggle}
          onDelete={(g) => setConfirmDelete(g)}
        />
      )}

      {confirmDelete && (
        <ConfirmDialog
          message={messages.guards.confirmDelete}
          onConfirm={handleDelete}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}