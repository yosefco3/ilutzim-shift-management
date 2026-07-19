import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  fetchProcedures,
  createProcedure,
  uploadProcedureDocx,
  generateProcedureQuestions,
  publishProcedure,
  deleteProcedure,
} from '../api/adminApiClient';
import { useToast } from '../components/Toast';
import ConfirmDialog from '../components/ConfirmDialog';
import messages from '../utils/messages';

const m = messages.procedures;

// Maps the backend status enum value → Hebrew label + badge class for the list.
const STATUS_META = {
  draft: { label: m.statusDraft, badge: 'badge-warning' },
  published: { label: m.statusPublished, badge: 'badge-published' },
  archived: { label: m.statusArchived, badge: 'badge-muted' },
};

const STATUS_LABEL = (status) => STATUS_META[status]?.label || status;

/**
 * Per-row publish action for a procedure. Every publish path makes the
 * procedure the single default (clearing the previous one); the button label +
 * confirm dialog + whether to rebroadcast depend on the current status:
 *   draft            → first publish (broadcast to ALL)
 *   archived         → re-publish (broadcast to ALL, becomes default)
 *   published        → rebroadcast=true (skips guards who already passed);
 *                      non-default becomes the default, default is re-shared.
 */
function publishActionMeta(proc) {
  if (proc.status === 'draft') {
    return {
      rebroadcast: false,
      label: m.rowPublish,
      title: m.publishConfirmTitle,
      message: m.publishConfirm,
      confirmLabel: m.publishLabel,
    };
  }
  if (proc.status === 'archived') {
    return {
      rebroadcast: false,
      label: m.republish,
      title: m.republishConfirmTitle,
      message: m.republishConfirm,
      confirmLabel: m.republish,
    };
  }
  if (proc.status === 'published' && !proc.is_default) {
    return {
      rebroadcast: true,
      label: m.markDefaultBroadcast,
      title: m.markDefaultConfirmTitle,
      message: m.markDefaultConfirm,
      confirmLabel: m.markDefaultBroadcast,
    };
  }
  // published + default → re-share (rebroadcast, stays the default).
  return {
    rebroadcast: true,
    label: m.reshare,
    title: m.reshareConfirmTitle,
    message: m.reshareConfirm,
    confirmLabel: m.reshare,
  };
}

/**
 * ProceduresPage (סד"פ) — list of procedures with a "new procedure" flow
 * (paste text OR upload a .docx → review/edit the extracted text → save draft)
 * and a per-draft "generate questions" button that calls the Claude-backed
 * generation endpoint (takes ~30–60s, so a spinner + clear error display).
 */
export default function ProceduresPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const [procedures, setProcedures] = useState([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState('');

  const [showNew, setShowNew] = useState(false);

  // Per-row generate state: which id is currently generating, and an error per
  // id (so one failing row doesn't smear its error onto another).
  const [generatingId, setGeneratingId] = useState(null);
  const [genErrors, setGenErrors] = useState({});

  // Per-row publish state: which id is mid-publish (disables its button).
  const [publishingId, setPublishingId] = useState(null);

  // Ignore stale fetches after unmount / re-entry.
  const reqId = useRef(0);

  const load = useCallback(async () => {
    const myReq = ++reqId.current;
    setLoading(true);
    setListError('');
    try {
      const data = await fetchProcedures();
      if (myReq === reqId.current) setProcedures(Array.isArray(data) ? data : []);
    } catch (err) {
      if (myReq === reqId.current) setListError(err.message || messages.common.error);
    } finally {
      if (myReq === reqId.current) setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreated = async (proc) => {
    setShowNew(false);
    toast.success(m.createdToast);
    // Go straight to the detail page so the admin can edit the body / questions.
    navigate(`/procedures/${proc.id}`);
  };

  const handleGenerate = async (proc) => {
    setGeneratingId(proc.id);
    setGenErrors((prev) => ({ ...prev, [proc.id]: null }));
    try {
      const result = await generateProcedureQuestions(proc.id);
      const msg = result.skipped
        ? m.generatePartial(result.generated, result.total_questions)
        : m.generateDone(result.generated);
      toast.success(msg);
      await load();
    } catch (err) {
      // 503 = no ANTHROPIC_API_KEY / Claude API failure → actionable message;
      // 409 = not a draft → backend's Hebrew detail is already clear.
      const text = err.status === 503 ? m.errGenerateUnavailable : (err.message || m.errGenerate);
      setGenErrors((prev) => ({ ...prev, [proc.id]: text }));
    } finally {
      setGeneratingId(null);
    }
  };

  const handleDelete = useCallback(async (proc) => {
    try {
      await deleteProcedure(proc.id);
      toast.success(m.procDeleted);
      await load();
    } catch (err) {
      toast.error(err.message || messages.common.error);
    }
  }, [load, toast]);

  const handlePublish = useCallback(async (proc, rebroadcast) => {
    setPublishingId(proc.id);
    try {
      const result = await publishProcedure(proc.id, { rebroadcast });
      toast.success(
        rebroadcast
          ? m.rebroadcastDone(result.sent, result.skipped, result.total)
          : m.publishDone(result.sent, result.skipped, result.total),
      );
      await load(); // refresh the default badge
    } catch (err) {
      toast.error(err.message || messages.common.error);
    } finally {
      setPublishingId(null);
    }
  }, [load, toast]);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h2>{m.title}</h2>
          <p className="page-subtitle">{m.subtitle}</p>
        </div>
        {!showNew && (
          <button className="btn btn-primary" onClick={() => setShowNew(true)}>
            {m.add}
          </button>
        )}
      </div>

      {showNew && (
        <NewProcedureForm
          onSaved={handleCreated}
          onCancel={() => setShowNew(false)}
        />
      )}

      {listError && <div className="alert alert-error" role="alert">{listError}</div>}

      {loading ? (
        <div className="loading">{messages.common.loading}</div>
      ) : procedures.length === 0 ? (
        <div className="empty-state">{m.noProcedures}</div>
      ) : (
        <div className="card table-scroll">
          <table className="preview-table" data-testid="procedures-table">
            <thead>
              <tr>
                <th>{messages.procedures.titleField}</th>
                <th>{m.status}</th>
                <th>{m.questions}</th>
                <th>{m.publishedAt}</th>
                <th>{messages.common.actions}</th>
              </tr>
            </thead>
            <tbody>
              {procedures.map((proc) => (
                <ProcedureRow
                  key={proc.id}
                  proc={proc}
                  generating={generatingId === proc.id}
                  publishing={publishingId === proc.id}
                  error={genErrors[proc.id]}
                  onGenerate={() => handleGenerate(proc)}
                  onPublish={handlePublish}
                  onDelete={handleDelete}
                  onOpen={() => navigate(`/procedures/${proc.id}`)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ProcedureRow({ proc, generating, publishing, error, onGenerate, onPublish, onDelete, onOpen }) {
  const isDraft = proc.status === 'draft';
  const meta = STATUS_META[proc.status] || { badge: 'badge-muted' };
  const [publishOpen, setPublishOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const action = publishActionMeta(proc);
  return (
    <tr data-testid={`procedure-row-${proc.id}`}>
      <td className="guard-cell">
        <button className="btn btn-ghost btn-sm" onClick={onOpen} data-testid={`open-${proc.id}`}>
          {proc.title}
        </button>
        {proc.is_default && (
          <span className="badge badge-published" data-testid={`default-badge-${proc.id}`} style={{ marginInlineStart: '0.5rem' }}>
            {m.defaultBadge}
          </span>
        )}
      </td>
      <td>
        <span className={`badge ${meta.badge}`}>{STATUS_LABEL(proc.status)}</span>
        {proc.status === 'published' && proc.quiz_open === false && (
          <span
            className="badge badge-danger"
            data-testid={`quiz-closed-badge-${proc.id}`}
            style={{ marginInlineStart: '0.5rem' }}
          >
            {m.quizClosedBadge}
          </span>
        )}
      </td>
      <td>
        {isDraft
          ? m.questionsCount(proc.active_questions, proc.total_questions)
          : m.activeOnly(proc.active_questions)}
      </td>
      <td>{proc.published_at ? formatDate(proc.published_at) : '—'}</td>
      <td>
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center', flexWrap: 'wrap' }}>
          {/* Hidden once an AI bank exists — regeneration would silently
              replace unedited AI questions, so the UI stops offering it. */}
          {isDraft && !proc.has_ai_questions && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={onGenerate}
              disabled={generating}
              data-testid={`generate-${proc.id}`}
            >
              {generating ? m.generating : m.generate}
            </button>
          )}
          <button
            className="btn btn-primary btn-sm"
            onClick={() => setPublishOpen(true)}
            disabled={publishing}
            data-testid={`publish-${proc.id}`}
          >
            {publishing ? m.publishing : action.label}
          </button>
          <button className="btn btn-outline btn-sm" onClick={onOpen}>
            {m.edit}
          </button>
          <button
            className="btn btn-danger btn-sm"
            onClick={() => setDeleteOpen(true)}
            data-testid={`delete-proc-${proc.id}`}
          >
            {m.delete}
          </button>
        </div>
        {error && (
          <div className="alert alert-error" role="alert" style={{ marginTop: 8 }}>
            {error}
          </div>
        )}
        {publishOpen && (
          <ConfirmDialog
            title={action.title}
            message={action.message}
            confirmLabel={action.confirmLabel}
            onConfirm={() => {
              setPublishOpen(false);
              onPublish(proc, action.rebroadcast);
            }}
            onCancel={() => setPublishOpen(false)}
          />
        )}
        {deleteOpen && (
          <ConfirmDialog
            title={m.deleteProcTitle}
            message={isDraft ? m.deleteProcConfirmDraft : m.deleteProcConfirmHistory}
            confirmLabel={m.delete}
            onConfirm={() => {
              setDeleteOpen(false);
              onDelete(proc);
            }}
            onCancel={() => setDeleteOpen(false)}
          />
        )}
      </td>
    </tr>
  );
}

/**
 * New-procedure form: paste a title + body, or upload a .docx (the extracted
 * text fills the editable body for review), then save → POST /admin/procedures.
 */
function NewProcedureForm({ onSaved, onCancel }) {
  const toast = useToast();
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  // Sanitized docx→HTML snapshot from the upload response — sent on save so the
  // WebApp reading page renders the rich version. Editing the plain body above
  // does NOT touch it (the hint below tells the admin). A re-upload replaces it.
  const [bodyHtml, setBodyHtml] = useState(null);
  const [sourceFilename, setSourceFilename] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const handleDocx = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setExtracting(true);
    setFormError('');
    try {
      const result = await uploadProcedureDocx(file, title);
      const text = result.text || '';
      // The document's first non-empty line becomes the title (unless the admin
      // already typed one) and is stripped from the body to avoid duplication.
      if (!title.trim()) {
        const lines = text.split('\n');
        const idx = lines.findIndex((l) => l.trim());
        if (idx >= 0) {
          // Strip the *bold* markers the docx extractor emits — the title is
          // sent bold anyway, and literal asterisks would show in Telegram.
          setTitle(lines[idx].trim().replace(/\*/g, '').trim().slice(0, 200));
          setBody(lines.slice(idx + 1).join('\n').replace(/^\n+/, ''));
        } else {
          setBody(text);
        }
      } else {
        setBody(text);
      }
      // A re-upload replaces BOTH the text (above) and the HTML snapshot.
      setBodyHtml(result.body_html ?? null);
      setSourceFilename(result.source_filename || file.name);
    } catch (err) {
      setFormError(err.message || messages.common.error);
    } finally {
      setExtracting(false);
      // Allow re-selecting the same file (change event won't fire otherwise).
      e.target.value = '';
    }
  };

  const handleSave = async () => {
    const t = title.trim();
    const b = body.trim();
    if (!t) { setFormError(m.errTitleRequired); return; }
    if (!b) { setFormError(m.errBodyRequired); return; }
    setSaving(true);
    setFormError('');
    try {
      // Only send body_html when an uploaded-docx snapshot exists — pasted-text
      // procedures have none, so their payload stays { title, body_text }.
      const payload = { title: t, body_text: b };
      if (bodyHtml) payload.body_html = bodyHtml;
      const proc = await createProcedure(payload);
      onSaved(proc);
    } catch (err) {
      setFormError(err.message || messages.common.error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card" data-testid="new-procedure-form">
      <h3>{m.newTitle}</h3>
      <p className="page-subtitle">{m.newSubtitle}</p>

      <div className="form-group">
        <label htmlFor="proc-title">{m.titleField}</label>
        <input
          id="proc-title"
          type="text"
          className="settings-input"
          value={title}
          placeholder={m.titlePlaceholder}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>

      <div className="form-group">
        <label htmlFor="proc-body">{m.bodyField}</label>
        <textarea
          id="proc-body"
          className="settings-input"
          rows={10}
          value={body}
          placeholder={m.bodyPlaceholder}
          onChange={(e) => setBody(e.target.value)}
          data-testid="proc-body"
        />
        <p className="page-subtitle" data-testid="proc-body-hint">{m.bodyBoldHint}</p>
        {bodyHtml && (
          <p className="page-subtitle" data-testid="body-html-hint">{m.bodyHtmlHint}</p>
        )}
        {sourceFilename && !extracting && (
          <p className="page-subtitle" data-testid="docx-extracted">
            {m.extractedChars(body.length)} · {sourceFilename}
          </p>
        )}
      </div>

      <div className="form-group">
        <label>{m.docxUpload}</label>
        <p className="page-subtitle">{m.docxHint}</p>
        <input
          type="file"
          accept=".docx"
          onChange={handleDocx}
          disabled={extracting || saving}
          data-testid="docx-input"
        />
        {extracting && <span className="page-subtitle"> {m.extracting}</span>}
      </div>

      {formError && <div className="alert alert-error" role="alert">{formError}</div>}

      <div className="modal-actions">
        <button
          className="btn btn-primary"
          onClick={handleSave}
          disabled={saving || extracting}
          data-testid="save-draft"
        >
          {saving ? m.saving : m.saveDraft}
        </button>
        <button className="btn btn-secondary" onClick={onCancel} disabled={saving}>
          {messages.common.cancel}
        </button>
      </div>
    </div>
  );
}

// ISO → localized date string (backend returns ISO datetimes). Kept tolerant of
// already-formatted strings.
function formatDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString('he-IL');
}
