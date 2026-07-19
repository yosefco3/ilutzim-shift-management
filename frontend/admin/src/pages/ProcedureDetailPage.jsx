import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  fetchProcedure,
  addProcedureQuestion,
  updateProcedureQuestion,
  deleteProcedureQuestion,
  generateProcedureQuestions,
  publishProcedure,
  fetchProcedureResults,
} from '../api/adminApiClient';
import { useToast } from '../components/Toast';
import ConfirmDialog from '../components/ConfirmDialog';
import messages from '../utils/messages';

const m = messages.procedures;

// Telegram quiz-poll limits — mirror backend/app/procedures/constants.py
// (MAX_QUESTION_CHARS=300, MAX_OPTION_CHARS=100, 2–4 options) so the editor
// rejects overlong/over-structured questions client-side, exactly matching the
// API validation (question_schemas.py).
const MAX_QUESTION_CHARS = 300;
const MAX_OPTION_CHARS = 100;
const MIN_OPTIONS = 2;
const MAX_OPTIONS = 4;

// Returns a Hebrew error string for an invalid question, or null when valid.
// Mirrors _validate_question / _validate_options / _validate_correct server-side.
function validateQuestion({ text, options, correctIndex }) {
  const t = (text || '').trim();
  if (!t) return m.errQuestionEmpty;
  if (t.length > MAX_QUESTION_CHARS) return m.errQuestionLong(MAX_QUESTION_CHARS);
  const opts = (options || []).map((o) => (o || '').trim());
  if (opts.length < MIN_OPTIONS || opts.length > MAX_OPTIONS) return m.errOptionsCount;
  if (opts.some((o) => o.length > MAX_OPTION_CHARS)) return m.errOptionLong(MAX_OPTION_CHARS);
  if (opts.some((o) => !o)) return m.errOptionEmpty;
  if (correctIndex == null || correctIndex < 0 || correctIndex >= opts.length) {
    return m.errCorrect;
  }
  return null;
}

const HEADER_STATUS_META = {
  draft: { label: m.statusDraft, badge: 'badge-warning' },
  published: { label: m.statusPublished, badge: 'badge-published' },
  archived: { label: m.statusArchived, badge: 'badge-muted' },
};

const RESULT_STATUS_META = {
  passed: { label: m.statusPassed, badge: 'badge-success' },
  failed: { label: m.statusFailed, badge: 'badge-danger' },
  in_progress: { label: m.statusInProgress, badge: 'badge-warning' },
  not_started: { label: m.statusNotStarted, badge: 'badge-muted' },
};

/**
 * ProcedureDetailPage — body text, a question editor (add/edit/disable/delete
 * with client-side validation), a publish flow (confirm dialog → broadcast
 * counts; 409 → offer rebroadcast), and a per-guard results table.
 */
export default function ProcedureDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();

  const [proc, setProc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('questions'); // 'questions' | 'results'

  // Publish state: publishDialog = 'first' | 'rebroadcast' | null.
  const [publishDialog, setPublishDialog] = useState(null);
  const [publishing, setPublishing] = useState(false);

  // Inline question editor: editingId = the question being edited, or 'new',
  // or null. questionsBump forces the list to re-read after mutations.
  const [editingId, setEditingId] = useState(null);

  const reqId = useRef(0);
  const load = useCallback(async () => {
    const myReq = ++reqId.current;
    setLoading(true);
    setError('');
    try {
      const data = await fetchProcedure(id);
      if (myReq === reqId.current) setProc(data);
    } catch (err) {
      if (myReq === reqId.current) setError(err.message || messages.common.error);
    } finally {
      if (myReq === reqId.current) setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const doPublish = async (rebroadcast) => {
    setPublishing(true);
    try {
      const result = await publishProcedure(id, { rebroadcast });
      toast.success(
        rebroadcast
          ? m.rebroadcastDone(result.sent, result.skipped, result.total)
          : m.publishDone(result.sent, result.skipped, result.total),
      );
      await load();
    } catch (err) {
      // 409 on a first publish = already published (race). Offer rebroadcast,
      // which skips guards who already passed.
      if (!rebroadcast && err.status === 409) {
        setPublishDialog('rebroadcast');
      } else {
        toast.error(err.message || messages.common.error);
      }
    } finally {
      setPublishing(false);
    }
  };

  if (loading) return <div className="loading">{messages.common.loading}</div>;
  if (error && !proc) {
    return (
      <div className="page">
        <div className="alert alert-error" role="alert">{error}</div>
        <button className="btn btn-secondary btn-sm" onClick={() => navigate('/procedures')}>
          {m.back}
        </button>
      </div>
    );
  }
  if (!proc) return null;

  const isDraft = proc.status === 'draft';
  const meta = HEADER_STATUS_META[proc.status] || { badge: 'badge-muted' };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h2>{proc.title}</h2>
          <p className="page-subtitle">
            <span className={`badge ${meta.badge}`}>{meta.label || proc.status}</span>
            {proc.status === 'published' && proc.quiz_deadline_at && (
              <span
                data-testid="quiz-window-info"
                style={{ marginInlineStart: '0.5rem' }}
              >
                {proc.quiz_open === false
                  ? m.quizClosedHint
                  : m.quizOpenUntil(formatDateTime(proc.quiz_deadline_at))}
              </span>
            )}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            className="btn btn-secondary"
            onClick={() => navigate('/procedures')}
            data-testid="back-to-list"
          >
            {m.backToList}
          </button>
          {isDraft && (
            <button
              className="btn btn-primary"
              onClick={() => setPublishDialog('first')}
              disabled={publishing}
              data-testid="publish-btn"
            >
              {publishing ? m.publishing : m.publish}
            </button>
          )}
          {!isDraft && proc.status === 'published' && (
            <button
              className="btn btn-secondary"
              onClick={() => setPublishDialog('rebroadcast')}
              disabled={publishing}
              data-testid="rebroadcast-btn"
            >
              {m.rebroadcastLabel}
            </button>
          )}
        </div>
      </div>

      {error && <div className="alert alert-error" role="alert">{error}</div>}

      <div className="card">
        <h3>{m.body}</h3>
        <pre className="proc-body" data-testid="proc-body">
          {proc.body_text || m.bodyEmpty}
        </pre>
      </div>

      <div className="tab-row" style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        <button
          className={`btn btn-sm ${tab === 'questions' ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => setTab('questions')}
        >
          {m.tabsQuestions} ({proc.questions?.length || 0})
        </button>
        <button
          className={`btn btn-sm ${tab === 'results' ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => setTab('results')}
        >
          {m.tabsResults}
        </button>
      </div>

      {tab === 'questions' ? (
        <QuestionsTab
          proc={proc}
          isDraft={isDraft}
          editingId={editingId}
          setEditingId={setEditingId}
          reload={load}
        />
      ) : (
        <ResultsTab procedureId={id} />
      )}

      {publishDialog && (
        <ConfirmDialog
          title={publishDialog === 'rebroadcast' ? m.publishAlreadyTitle : m.publishConfirmTitle}
          message={publishDialog === 'rebroadcast' ? m.publishAlreadyMsg : m.publishConfirm}
          confirmLabel={publishDialog === 'rebroadcast' ? m.rebroadcastLabel : m.publishLabel}
          onConfirm={() => {
            setPublishDialog(null);
            doPublish(publishDialog === 'rebroadcast');
          }}
          onCancel={() => setPublishDialog(null)}
        />
      )}
    </div>
  );
}

// ── Questions tab ─────────────────────────────────────────────────────────────

function QuestionsTab({ proc, isDraft, editingId, setEditingId, reload }) {
  const toast = useToast();
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [generating, setGenerating] = useState(false);
  const questions = proc.questions || [];
  // Once an AI bank exists, stop offering generation (a re-run would replace
  // unedited AI questions) — same rule as the list page.
  const hasAiQuestions = questions.some((q) => q.source === 'ai');

  // AI generation, also available here (not only on the list page) — this is
  // where the admin lands right after creating a procedure.
  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const result = await generateProcedureQuestions(proc.id);
      toast.success(
        result.skipped
          ? m.generatePartial(result.generated, result.total_questions)
          : m.generateDone(result.generated),
      );
      await reload();
    } catch (err) {
      toast.error(err.status === 503 ? m.errGenerateUnavailable : (err.message || m.errGenerate));
    } finally {
      setGenerating(false);
    }
  };

  const handleSave = async (data, questionId) => {
    if (questionId) {
      await updateProcedureQuestion(proc.id, questionId, data);
      toast.success(m.questionSaved);
    } else {
      await addProcedureQuestion(proc.id, data);
      toast.success(m.questionAdded);
    }
    setEditingId(null);
    await reload();
  };

  const handleToggleActive = async (q) => {
    try {
      await updateProcedureQuestion(proc.id, q.id, { is_active: !q.is_active });
      toast.success(m.questionSaved);
      await reload();
    } catch (err) {
      toast.error(err.message || messages.common.error);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteProcedureQuestion(proc.id, deleteTarget.id);
      toast.success(m.questionDeleted);
      setDeleteTarget(null);
      await reload();
    } catch (err) {
      toast.error(err.message || messages.common.error);
    }
  };

  return (
    <div data-testid="questions-tab">
      {questions.length === 0 && editingId !== 'new' && (
        <div className="empty-state">{m.noQuestions}</div>
      )}

      {questions.map((q, index) => (
        <div key={q.id} className="card" data-testid={`question-card-${q.id}`}>
          {editingId === q.id ? (
            <QuestionForm
              initial={q}
              onCancel={() => setEditingId(null)}
              onSave={(data) => handleSave(data, q.id)}
            />
          ) : (
            <QuestionDisplay
              q={q}
              index={index}
              isDraft={isDraft}
              onEdit={() => setEditingId(q.id)}
              onToggleActive={() => handleToggleActive(q)}
              onDelete={() => setDeleteTarget(q)}
            />
          )}
        </div>
      ))}

      {editingId === 'new' ? (
        <div className="card" data-testid="new-question-form">
          <h3>{m.addQuestionTitle}</h3>
          <QuestionForm
            initial={null}
            onCancel={() => setEditingId(null)}
            onSave={(data) => handleSave(data, null)}
          />
        </div>
      ) : (
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {isDraft && !hasAiQuestions && (
            <button
              className="btn btn-primary"
              onClick={handleGenerate}
              disabled={generating}
              data-testid="generate-ai-btn"
            >
              {generating ? m.generating : m.generate}
            </button>
          )}
          <button
            className="btn btn-secondary"
            onClick={() => setEditingId('new')}
            data-testid="add-question-btn"
          >
            {m.addQuestion}
          </button>
        </div>
      )}

      {deleteTarget && (
        <ConfirmDialog
          title={m.deleteQuestionTitle}
          message={m.deleteQuestionMsg}
          confirmLabel={messages.common.delete}
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}

function QuestionDisplay({ q, index, isDraft, onEdit, onToggleActive, onDelete }) {
  const sourceBadge = q.source === 'manual' ? m.sourceManual : m.sourceAi;
  const sourceClass = q.source === 'manual' ? 'badge-muted' : 'badge-active';
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <span className={`badge ${sourceClass}`}>{sourceBadge}</span>
          {q.edited_at && <span className="badge badge-secondary">{m.editedBadge}</span>}
          <span className={`badge ${q.is_active ? 'badge-active' : 'badge-inactive'}`}>
            {q.is_active ? m.active : m.inactive}
          </span>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className="btn btn-outline btn-sm" onClick={onEdit}>
            {messages.common.edit}
          </button>
          {isDraft && (
            <button className="btn btn-danger btn-sm" onClick={onDelete} data-testid={`delete-${q.id}`}>
              {messages.common.delete}
            </button>
          )}
          {!q.is_active ? (
            <button className="btn btn-secondary btn-sm" onClick={onToggleActive} data-testid={`enable-${q.id}`}>
              {m.enable}
            </button>
          ) : (
            <button className="btn btn-secondary btn-sm" onClick={onToggleActive} data-testid={`disable-${q.id}`}>
              {m.disable}
            </button>
          )}
        </div>
      </div>

      <p style={{ marginTop: '0.5rem', fontWeight: 600 }}>
        {index + 1}. {q.text}
      </p>
      <ul className="option-list" style={{ margin: '0.25rem 0 0', paddingInlineStart: '1.2rem' }}>
        {q.options.map((opt, i) => (
          <li
            key={i}
            className={i === q.correct_index ? 'option-correct' : ''}
            style={{ fontWeight: i === q.correct_index ? 700 : 400, color: i === q.correct_index ? 'var(--success)' : 'inherit' }}
            data-testid={`option-${i}`}
          >
            {i === q.correct_index ? '✓ ' : ''}{opt}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Inline add/edit form for one question. Validates text ≤300, options ≤100,
 * 2–4 options, exactly one correct — matching the backend schema limits.
 */
function QuestionForm({ initial, onSave, onCancel }) {
  const [text, setText] = useState(initial?.text || '');
  const [options, setOptions] = useState(
    initial?.options?.length >= MIN_OPTIONS ? [...initial.options] : ['', ''],
  );
  const [correctIndex, setCorrectIndex] = useState(initial?.correct_index ?? 0);
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);

  const setOption = (i, value) =>
    setOptions((prev) => prev.map((o, idx) => (idx === i ? value : o)));
  const addOption = () => {
    if (options.length < MAX_OPTIONS) setOptions((prev) => [...prev, '']);
  };
  const removeOption = (i) => {
    if (options.length <= MIN_OPTIONS) return;
    setOptions((prev) => prev.filter((_, idx) => idx !== i));
    // Keep the radio on the SAME option after the indices shift left; removing
    // the correct option itself falls back to the first one.
    setCorrectIndex((prev) => (i === prev ? 0 : i < prev ? prev - 1 : prev));
  };

  const handleSave = async () => {
    const err = validateQuestion({ text, options, correctIndex });
    if (err) { setFormError(err); return; }
    setSaving(true);
    setFormError('');
    try {
      await onSave({
        text: text.trim(),
        options: options.map((o) => o.trim()),
        correct_index: correctIndex,
      });
    } catch (e) {
      setFormError(e.message || messages.common.error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div data-testid="question-form">
      <div className="form-group">
        <label htmlFor="q-text">{m.questionText}</label>
        <textarea
          id="q-text"
          className="settings-input"
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={MAX_QUESTION_CHARS}
          data-testid="q-text"
        />
        <p className="page-subtitle">{m.charsLeft(MAX_QUESTION_CHARS - text.length)}</p>
      </div>

      <div className="form-group">
        <label>{m.options}</label>
        {options.map((opt, i) => (
          <div key={i} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.4rem' }}>
            <input
              type="radio"
              name={`correct-${initial?.id || 'new'}`}
              checked={correctIndex === i}
              onChange={() => setCorrectIndex(i)}
              aria-label={m.correctLabel}
              data-testid={`correct-${i}`}
            />
            <input
              type="text"
              className="settings-input"
              value={opt}
              maxLength={MAX_OPTION_CHARS}
              placeholder={m.optionPlaceholder(i + 1)}
              onChange={(e) => setOption(i, e.target.value)}
              data-testid={`option-input-${i}`}
            />
            {options.length > MIN_OPTIONS && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => removeOption(i)}
                aria-label={m.removeOption}
              >
                ✕
              </button>
            )}
          </div>
        ))}
        {options.length < MAX_OPTIONS && (
          <button type="button" className="btn btn-outline btn-sm" onClick={addOption} data-testid="add-option">
            {m.addOption}
          </button>
        )}
      </div>

      {formError && <div className="alert alert-error" role="alert" data-testid="q-form-error">{formError}</div>}

      <div className="modal-actions">
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleSave}
          disabled={saving}
          data-testid="q-save"
        >
          {saving ? m.savingQuestion : m.saveQuestion}
        </button>
        <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={saving}>
          {messages.common.cancel}
        </button>
      </div>
    </div>
  );
}

// ── Results tab ───────────────────────────────────────────────────────────────

function ResultsTab({ procedureId }) {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    fetchProcedureResults(procedureId)
      .then((data) => { if (!cancelled) setResults(Array.isArray(data) ? data : []); })
      .catch((err) => { if (!cancelled) setError(err.message || messages.common.error); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [procedureId]);

  if (loading) return <div className="loading">{messages.common.loading}</div>;
  if (error) return <div className="alert alert-error" role="alert">{error}</div>;
  if (!results || results.length === 0) {
    return <div className="empty-state">{m.noResults}</div>;
  }

  return (
    <div data-testid="results-tab">
      <p className="page-subtitle">{m.resultsHint}</p>
      <div className="card table-scroll">
        <table className="preview-table" data-testid="results-table">
          <thead>
            <tr>
              <th>{m.resultGuard}</th>
              <th>{m.resultStatus}</th>
              <th>{m.resultRead}</th>
              <th>{m.resultAttempts}</th>
              <th>{m.resultBest}</th>
            </tr>
          </thead>
          <tbody>
            {results.map((row) => {
              const meta = RESULT_STATUS_META[row.status] || { badge: 'badge-muted', label: row.status };
              const notPassed = row.status === 'failed' || row.status === 'not_started';
              return (
                <tr
                  key={row.user_id}
                  style={notPassed ? { background: 'var(--danger-soft)' } : undefined}
                  data-testid={`result-row-${row.user_id}`}
                >
                  <td className="guard-cell">{row.user_name}</td>
                  <td>
                    <span className={`badge ${meta.badge}`}>{meta.label}</span>
                  </td>
                  <td data-testid={`read-cell-${row.user_id}`}>
                    {row.read
                      ? `${m.readYes} ${formatReadDate(row.first_read_at)}`
                      : m.readNo}
                  </td>
                  <td>{row.attempts ?? 0}</td>
                  <td>{row.best_score != null ? m.scorePercent(row.best_score) : m.noScore}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ISO datetime → localized date+time for the quiz-window deadline. Tolerant.
function formatDateTime(value) {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString('he-IL', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

// ISO datetime → localized date for the "קרא" column. Tolerant of bad input.
function formatReadDate(value) {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString('he-IL');
}
