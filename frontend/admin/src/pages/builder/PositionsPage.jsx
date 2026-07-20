import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  listProfiles,
  listPositions,
  createPosition,
  updatePosition,
  deletePosition,
  copyPosition,
  bulkUpdateDaySchedules,
  listAttributes,
  createAttribute,
  deleteAttribute,
} from '../../api/builderApiClient';
import { useToast } from '../../components/Toast';
import ConfirmDialog from '../../components/ConfirmDialog';
import PositionEditorModal from '../../components/positions/PositionEditorModal';
import ProfileMatrix from '../../components/positions/ProfileMatrix';
import messages from '../../utils/messages';
import { DAY_NAMES_SHORT as DAY_NAMES } from '../../utils/guardMessages.js';

function daySummary(daySchedules) {
  const active = Object.keys(daySchedules || {})
    .map(Number)
    .sort((a, b) => a - b);
  if (!active.length) return '—';
  return active.map((i) => DAY_NAMES[i]).join(', ');
}

export default function PositionsPage() {
  const toast = useToast();
  const m = messages.positions;
  // Deep-link from the board's edit icon: ?profile=<id>&edit=<positionId>.
  const [searchParams, setSearchParams] = useSearchParams();

  const [profiles, setProfiles] = useState([]);
  const [profileId, setProfileId] = useState('');
  const [positions, setPositions] = useState([]);
  const [attributes, setAttributes] = useState([]);
  const [loading, setLoading] = useState(true);
  // "matrix" (positions × days, default) | "cards" (the original card UI). The
  // board's ?edit= deep-link opens the position editor modal, which lives in the
  // cards flow — so an ?edit param lands you on the cards tab to match.
  const [tab, setTab] = useState(() => (searchParams.get('edit') ? 'cards' : 'matrix'));

  // The selected profile object (carries day_labels for the matrix headers).
  const profile = profiles.find((p) => p.id === profileId);

  const [editor, setEditor] = useState(null); // editor form or null
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [showAttrs, setShowAttrs] = useState(false);
  const [attrForm, setAttrForm] = useState({ key: '', label: '' });
  const [confirmDeleteAttr, setConfirmDeleteAttr] = useState(null);

  // Drag-and-drop: copy a position into another profile.
  const [draggingId, setDraggingId] = useState(null); // position being dragged
  const [dragOverProfile, setDragOverProfile] = useState(null); // target highlight

  // Matrix editor (step 04) dirty tracking + unsaved-changes guard [EDGE N2].
  // matrixDirty = count of changed positions reported by ProfileMatrix. When >0,
  // switching tab/profile is intercepted by a ConfirmDialog and a beforeunload
  // listener guards a real page unload (the app uses <BrowserRouter>, so
  // react-router's useBlocker is unavailable — see report).
  const [matrixDirty, setMatrixDirty] = useState(0);
  // null, or { run } — the navigation to perform if the admin confirms leaving.
  const [pendingLeave, setPendingLeave] = useState(null);
  const matrixDirtyActive = matrixDirty > 0;

  const attrLabel = useCallback(
    (key) => attributes.find((a) => a.key === key)?.label || key,
    [attributes],
  );

  // Initial load: profiles + attributes, then default profile selection.
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [profs, attrs] = await Promise.all([listProfiles(), listAttributes()]);
        setProfiles(profs);
        setAttributes(attrs);
        // A deep-link (?profile=) wins over the default selection so the board's
        // edit shortcut lands on the same profile it was showing.
        const wanted = searchParams.get('profile');
        const def =
          profs.find((p) => p.id === wanted) ||
          profs.find((p) => p.is_default) ||
          profs[0];
        setProfileId(def ? def.id : '');
      } catch (err) {
        toast.error(err.message || messages.common.error);
      } finally {
        setLoading(false);
      }
    })();
  }, [toast]);

  const loadPositions = useCallback(async () => {
    if (!profileId) {
      setPositions([]);
      return;
    }
    try {
      setPositions(await listPositions(profileId));
    } catch (err) {
      toast.error(err.message || messages.common.error);
    }
  }, [profileId, toast]);

  useEffect(() => {
    loadPositions();
  }, [loadPositions]);

  // Once the (deep-linked) profile's positions have loaded, auto-open the editor
  // for ?edit=<positionId>, then clear the params so it opens exactly once.
  useEffect(() => {
    const editId = searchParams.get('edit');
    if (!editId || !positions.length) return;
    const target = positions.find((p) => p.id === editId);
    if (target) setEditor(target);
    setSearchParams({}, { replace: true });
  }, [positions, searchParams, setSearchParams]);

  const refreshAttrs = async () => {
    try {
      setAttributes(await listAttributes());
    } catch (err) {
      toast.error(err.message || messages.common.error);
    }
  };

  // The shared PositionEditorModal hands us a ready API body; `editor` is the
  // position being edited, or 'new' for creation.
  const handleSave = async (body) => {
    try {
      if (editor !== 'new' && editor?.id) {
        await updatePosition(editor.id, body);
        toast.success(m.updated);
      } else {
        await createPosition(profileId, body);
        toast.success(m.created);
      }
      setEditor(null);
      await loadPositions();
    } catch (err) {
      toast.error(err.message || messages.common.error);
    }
  };

  const handleDelete = async () => {
    const p = confirmDelete;
    setConfirmDelete(null);
    try {
      await deletePosition(p.id);
      toast.success(m.deleted);
      await loadPositions();
    } catch (err) {
      toast.error(err.message || messages.common.error);
    }
  };

  // Save the matrix's changed rows via the atomic bulk endpoint [EDGE C1]. The
  // status tells ProfileMatrix what to expect: 'ok'/'conflict' reload positions
  // (so its snapshot resets and dirty state clears); 'error' does NOT reload, so
  // the admin's dirty state survives for a retry [EDGE N1]. 409 = a position left
  // this profile between load and save → reload, discard dirty [EDGE C2].
  const handleMatrixSave = useCallback(
    async (items) => {
      try {
        await bulkUpdateDaySchedules(profileId, items);
        toast.success(m.matrixSaved);
        await loadPositions();
        return 'ok';
      } catch (err) {
        if (err.status === 409) {
          toast.error(m.matrixConflict);
          await loadPositions();
          return 'conflict';
        }
        toast.error(err.message || messages.common.error);
        return 'error';
      }
    },
    [profileId, toast, m, loadPositions],
  );

  // Run a navigation now, or — if the matrix has unsaved changes — defer it
  // behind the unsaved-changes ConfirmDialog. Used by the tab buttons and the
  // profile <select> [EDGE N2].
  const guarded = useCallback(
    (action) => {
      if (matrixDirtyActive) setPendingLeave({ run: action });
      else action();
    },
    [matrixDirtyActive],
  );

  // Guard a real page unload (close tab / refresh / external nav) while the
  // matrix is dirty. In-app SPA route changes aren't covered by beforeunload; the
  // `guarded` wrapper covers the tab/profile switches this page owns.
  useEffect(() => {
    if (!matrixDirtyActive) return undefined;
    const handler = (e) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [matrixDirtyActive]);

  // Drop a dragged position onto a target profile → deep-copy it there.
  const handleCopyToProfile = async (positionId, targetProfile) => {
    setDraggingId(null);
    setDragOverProfile(null);
    const pos = positions.find((p) => p.id === positionId);
    try {
      await copyPosition(positionId, targetProfile.id);
      toast.success(m.copied(pos ? pos.name : '', targetProfile.name));
    } catch (err) {
      toast.error(err.message || messages.common.error);
    }
  };

  const handleAddAttr = async (e) => {
    e.preventDefault();
    if (!attrForm.key.trim() || !attrForm.label.trim()) return;
    try {
      await createAttribute({ key: attrForm.key.trim(), label: attrForm.label.trim() });
      setAttrForm({ key: '', label: '' });
      toast.success(m.attrCreated);
      await refreshAttrs();
    } catch (err) {
      toast.error(err.message || messages.common.error);
    }
  };

  const handleDeleteAttr = async () => {
    const a = confirmDeleteAttr;
    setConfirmDeleteAttr(null);
    try {
      await deleteAttribute(a.id);
      toast.success(m.attrDeleted);
      await refreshAttrs();
    } catch (err) {
      toast.error(err.message || messages.common.error);
    }
  };

  if (loading) return <div className="loading">{messages.common.loading}</div>;

  return (
    <div className="page">
      <div className="page-header">
        <h2>{m.title}</h2>
        <p className="page-subtitle">{m.subtitle}</p>
      </div>

      <div className="positions-toolbar">
        <label htmlFor="profile-select">{m.profile}</label>
        <select
          id="profile-select"
          aria-label={m.profile}
          value={profileId}
          onChange={(e) => {
            const next = e.target.value;
            guarded(() => setProfileId(next));
          }}
        >
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <button
          className="btn btn-primary"
          disabled={!profileId}
          onClick={() => setEditor('new')}
        >
          {m.newPosition}
        </button>
        <button className="btn btn-secondary" onClick={() => setShowAttrs(true)}>
          {m.manageAttrs}
        </button>
      </div>

      {!positions.length ? (
        <p className="empty-state">{m.empty}</p>
      ) : (
        <>
          <div className="tab-row positions-tab-row">
            <button
              className={`btn btn-sm ${tab === 'matrix' ? 'btn-primary' : 'btn-outline'}`}
              aria-pressed={tab === 'matrix'}
              onClick={() => guarded(() => setTab('matrix'))}
            >
              {m.matrix}
            </button>
            <button
              className={`btn btn-sm ${tab === 'cards' ? 'btn-primary' : 'btn-outline'}`}
              aria-pressed={tab === 'cards'}
              onClick={() => guarded(() => setTab('cards'))}
            >
              {m.cards}
            </button>
          </div>

          {tab === 'matrix' ? (
            <ProfileMatrix
              positions={positions}
              profile={profile}
              onSave={handleMatrixSave}
              onDirtyChange={setMatrixDirty}
            />
          ) : (
            <>
              <div className="copy-targets">
                <span className="copy-targets-title">{m.copyTargetsTitle}</span>
                {profiles.filter((p) => p.id !== profileId).length === 0 ? (
                  <span className="copy-targets-hint">{m.copyOnlyProfile}</span>
                ) : (
                  <>
                    {profiles
                      .filter((p) => p.id !== profileId)
                      .map((p) => (
                        <div
                          key={p.id}
                          className={`copy-target${dragOverProfile === p.id ? ' over' : ''}`}
                          onDragOver={(e) => {
                            e.preventDefault();
                            e.dataTransfer.dropEffect = 'copy';
                            if (dragOverProfile !== p.id) setDragOverProfile(p.id);
                          }}
                          onDragLeave={() => setDragOverProfile((cur) => (cur === p.id ? null : cur))}
                          onDrop={(e) => {
                            e.preventDefault();
                            const id = e.dataTransfer.getData('text/plain');
                            if (id) handleCopyToProfile(id, p);
                          }}
                        >
                          {p.name}
                        </div>
                      ))}
                    <span className="copy-targets-hint">
                      {draggingId ? m.dropToCopy : m.copyHint}
                    </span>
                  </>
                )}
              </div>

              <div className="position-cards">
                {positions.map((p) => (
                  <div
                    key={p.id}
                    className={`position-card${draggingId === p.id ? ' dragging' : ''}`}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData('text/plain', p.id);
                      e.dataTransfer.effectAllowed = 'copy';
                      setDraggingId(p.id);
                    }}
                    onDragEnd={() => {
                      setDraggingId(null);
                      setDragOverProfile(null);
                    }}
                  >
                    <div className="position-card-header">
                      <span className="position-card-name">{p.name}</span>
                      {p.is_event && (
                        <span className="position-event-badge">
                          {p.event_required_count != null
                            ? `${m.eventBadge} · ${p.event_required_count}`
                            : m.eventBadge}
                        </span>
                      )}
                    </div>
                    <p className="position-card-days">{daySummary(p.day_schedules)}</p>
                    {p.required_attributes?.length > 0 && (
                      <div className="position-card-tags">
                        {p.required_attributes.map((key) => (
                          <span key={key} className="position-tag">
                            {attrLabel(key)}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="position-card-actions">
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => setEditor(p)}
                      >
                        {m.edit}
                      </button>
                      <button
                        className="btn btn-danger btn-sm"
                        onClick={() => setConfirmDelete(p)}
                      >
                        {m.delete}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}

      <PositionEditorModal
        open={editor !== null}
        position={editor === 'new' ? null : editor}
        attributes={attributes}
        onSave={handleSave}
        onCancel={() => setEditor(null)}
        onInvalidDays={() => toast.error(m.needOneDay)}
      />

      {showAttrs && (
        <div className="modal-overlay" onClick={() => setShowAttrs(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal-title">{m.attrsTitle}</h3>
            <form className="attr-create-form" onSubmit={handleAddAttr}>
              <input
                type="text"
                aria-label={m.attrKey}
                placeholder={m.attrKeyPlaceholder}
                value={attrForm.key}
                onChange={(e) => setAttrForm({ ...attrForm, key: e.target.value })}
              />
              <input
                type="text"
                aria-label={m.attrLabel}
                placeholder={m.attrLabelPlaceholder}
                value={attrForm.label}
                onChange={(e) => setAttrForm({ ...attrForm, label: e.target.value })}
              />
              <button
                type="submit"
                className="btn btn-primary btn-sm"
                disabled={!attrForm.key.trim() || !attrForm.label.trim()}
              >
                {m.addAttr}
              </button>
            </form>
            {!attributes.length ? (
              <p className="empty-state">{m.noAttrs}</p>
            ) : (
              <ul className="attr-list">
                {attributes.map((a) => (
                  <li key={a.id} className="attr-list-item">
                    <span>
                      {a.label} <code>{a.key}</code>
                    </span>
                    <button
                      className="btn btn-danger btn-sm"
                      onClick={() => setConfirmDeleteAttr(a)}
                    >
                      {m.delete}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShowAttrs(false)}>
                {messages.common.cancel}
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!confirmDelete}
        title={m.deleteTitle}
        message={m.deleteMsg}
        confirmLabel={m.delete}
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(null)}
      />
      <ConfirmDialog
        open={!!confirmDeleteAttr}
        title={m.deleteAttrTitle}
        message={m.deleteAttrMsg}
        confirmLabel={m.delete}
        onConfirm={handleDeleteAttr}
        onCancel={() => setConfirmDeleteAttr(null)}
      />
      {/* Unsaved-changes guard for tab/profile switches out of a dirty matrix. */}
      <ConfirmDialog
        open={pendingLeave !== null}
        title={m.matrixDirtyLeaveTitle}
        message={m.matrixDirtyLeave}
        confirmLabel={m.matrixDirtyLeaveConfirm}
        onConfirm={() => {
          const action = pendingLeave?.run;
          setPendingLeave(null);
          if (action) action();
        }}
        onCancel={() => setPendingLeave(null)}
      />
    </div>
  );
}
