import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  fetchProcedures,
  createProcedure,
  uploadProcedureDocx,
  generateProcedureQuestions,
} from '../api/adminApiClient';
import { useToast } from '../components/Toast';
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
                  error={genErrors[proc.id]}
                  onGenerate={() => handleGenerate(proc)}
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

function ProcedureRow({ proc, generating, error, onGenerate, onOpen }) {
  const isDraft = proc.status === 'draft';
  const meta = STATUS_META[proc.status] || { badge: 'badge-muted' };
  return (
    <tr data-testid={`procedure-row-${proc.id}`}>
      <td className="guard-cell">
        <button className="btn btn-ghost btn-sm" onClick={onOpen} data-testid={`open-${proc.id}`}>
          {proc.title}
        </button>
      </td>
      <td>
        <span className={`badge ${meta.badge}`}>{STATUS_LABEL(proc.status)}</span>
      </td>
      <td>
        {isDraft
          ? m.questionsCount(proc.active_questions, proc.total_questions)
          : m.activeOnly(proc.active_questions)}
      </td>
      <td>{proc.published_at ? formatDate(proc.published_at) : '—'}</td>
      <td>
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center', flexWrap: 'wrap' }}>
          {isDraft && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={onGenerate}
              disabled={generating}
              data-testid={`generate-${proc.id}`}
            >
              {generating ? m.generating : m.generate}
            </button>
          )}
          <button className="btn btn-outline btn-sm" onClick={onOpen}>
            {m.edit}
          </button>
        </div>
        {error && (
          <div className="alert alert-error" role="alert" style={{ marginTop: 8 }}>
            {error}
          </div>
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
      setBody(result.text || '');
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
      const proc = await createProcedure({ title: t, body_text: b });
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
