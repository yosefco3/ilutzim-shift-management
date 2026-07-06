import { useState, useRef } from 'react';
import { previewConstraintsImport, commitConstraintsImport } from '../api/adminApiClient';
import { useWeeks } from '../hooks/useWeeks';
import { useToast } from '../components/Toast';
import messages from '../utils/messages';
import { DAY_NAMES_SHORT as DAY_NAMES } from '../utils/guardMessages.js';

const m = messages.importConstraints;

/**
 * Constraints import — upload an xlsx, see a clean merged preview (dry-run),
 * then confirm to persist into the existing availability model. After commit a
 * summary report (imported / created-new / errors / target week) is shown.
 */
export default function ImportConstraintsPage() {
  const { weeks } = useWeeks();
  const toast = useToast();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [summary, setSummary] = useState(null);
  const [weekId, setWeekId] = useState('');
  const [loading, setLoading] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);

  const handleFile = (e) => {
    setFile(e.target.files?.[0] || null);
    setPreview(null);
    setSummary(null);
    setError('');
  };

  const handlePreview = async () => {
    if (!file) {
      setError(m.pickFileFirst);
      return;
    }
    setLoading(true);
    setError('');
    setSummary(null);
    try {
      setPreview(await previewConstraintsImport(file));
    } catch (err) {
      setError(err.message || 'שגיאה בעיבוד הקובץ');
      setPreview(null);
    } finally {
      setLoading(false);
    }
  };

  const handleCommit = async () => {
    if (!file) return;
    setCommitting(true);
    setError('');
    try {
      const resp = await commitConstraintsImport(file, weekId || undefined);
      setSummary(resp.summary);
      toast.success(m.commitSuccess);
    } catch (err) {
      setError(err.message || 'שגיאה בשמירת הייבוא');
    } finally {
      setCommitting(false);
    }
  };

  return (
    <div className="page" dir="rtl">
      <h2>{m.title}</h2>
      <p className="page-subtitle">{m.subtitle}</p>

      <div className="card">
        <div className="form-group">
          <label>{m.chooseFile}</label>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx"
            onChange={handleFile}
            data-testid="file-input"
          />
        </div>
        <div className="form-group">
          <label>{m.week}</label>
          <select value={weekId} onChange={(e) => setWeekId(e.target.value)}>
            <option value="">{m.weekAuto}</option>
            {weeks.map((w) => (
              <option key={w.id} value={w.id}>{w.week_label}</option>
            ))}
          </select>
        </div>
        <button
          className="btn btn-primary"
          onClick={handlePreview}
          disabled={!file || loading}
        >
          {loading ? m.previewing : m.preview}
        </button>
      </div>

      {error && <div className="alert alert-error" role="alert">{error}</div>}

      {summary && <SummaryReport summary={summary} />}

      {preview && (
        <PreviewResult
          preview={preview}
          committing={committing}
          onCommit={handleCommit}
        />
      )}
    </div>
  );
}

function SummaryReport({ summary }) {
  const { week_start, week_end, imported, created_new, errors } = summary;
  return (
    <div className="card summary-report" data-testid="summary-report">
      <h3>{m.summaryTitle}</h3>
      <p className="summary-line">{imported} {m.importedSuffix}</p>
      <p className="summary-line">{m.createdPrefix} {created_new} {m.createdSuffix}</p>
      {week_start && week_end && (
        <p className="summary-line">{m.weekPrefix} {week_start} {m.weekJoin} {week_end}</p>
      )}
      {errors && errors.length > 0 && (
        <>
          <p className="summary-line">{m.errorsTitle}:</p>
          <ul className="import-errors" data-testid="summary-errors">
            {errors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </>
      )}
    </div>
  );
}

function PreviewResult({ preview, committing, onCommit }) {
  const { week_start, week_end, guards, errors } = preview;
  return (
    <>
      <div className="card preview-meta">
        {week_start && week_end && (
          <span className="preview-week">
            {m.weekPrefix} {week_start} {m.weekJoin} {week_end}
          </span>
        )}
        <span className="preview-count">{guards.length} {m.guardsSuffix}</span>
      </div>

      <div className={`card ${errors.length ? 'alert-error' : ''}`}>
        <h3>{m.errorsTitle}</h3>
        {errors.length === 0 ? (
          <p>{m.noErrors}</p>
        ) : (
          <ul className="import-errors" data-testid="parse-errors">
            {errors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        )}
      </div>

      <div className="card table-scroll">
        <table className="preview-table" dir="rtl">
          <thead>
            <tr>
              <th>{m.guard}</th>
              {DAY_NAMES.map((d) => <th key={d}>{d}</th>)}
              <th>{m.weeklyHours}</th>
              <th>{m.notes}</th>
            </tr>
          </thead>
          <tbody>
            {guards.map((g) => (
              <tr key={g.name}>
                <td className="guard-cell">
                  {g.name}{' '}
                  <span className={`badge ${g.exists ? 'badge-muted' : 'badge-new'}`}>
                    {g.exists ? m.exists : m.new}
                  </span>
                </td>
                {g.days.map((day) => (
                  <td key={day.day_index} className="day-cell">
                    {day.segments.length === 0 ? (
                      <span className="cell-empty">—</span>
                    ) : (
                      day.segments.map((s, i) => (
                        <div key={i} className="cell-window">{s}</div>
                      ))
                    )}
                  </td>
                ))}
                <td className="hours-cell">{g.weekly_hours}</td>
                <td className="notes-cell">{g.notes || ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <button className="btn btn-primary" onClick={onCommit} disabled={committing}>
          {committing ? m.committing : m.confirm}
        </button>
      </div>
    </>
  );
}
