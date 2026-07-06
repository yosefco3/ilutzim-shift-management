import { useState, useEffect, useRef, useCallback } from 'react';
import { useWeeks } from '../hooks/useWeeks';
import { previewPublish } from '../api/adminApiClient';
import GuardSearch from '../components/GuardSearch';
import { matchesGuardSearch } from '../utils/sorting';
import { resolvePublishableWeek } from '../utils/weeks';
import messages from '../utils/messages';

const M = messages.publishPreview;

/**
 * PublishPreviewPage — dry run of "publish": shows the exact Telegram message
 * each guard WOULD receive, without sending anything. Built for verifying content
 * and recipients while the data (phone numbers / telegram ids) is still placeholder.
 */
export default function PublishPreviewPage() {
  const { weeks, loading: weeksLoading } = useWeeks();
  const [selectedWeek, setSelectedWeek] = useState('');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');

  // Default to the exact week the publish button targets — the upcoming
  // un-started week (else the latest). The weeks list arrives unordered, so
  // picking "the first closed week" could lock onto a stale older week (e.g. one
  // whose profile was deleted, wiping its schedule) and show an empty preview.
  // resolvePublishableWeek keeps this in lockstep with WeeksPage / the backend.
  const didInit = useRef(false);
  useEffect(() => {
    if (didInit.current || !weeks.length) return;
    didInit.current = true;
    const target = resolvePublishableWeek(weeks);
    if (target) setSelectedWeek(String(target.id));
  }, [weeks]);

  // Fetch the preview for the current week. Returns a cleanup that cancels the
  // in-flight response, so both the effect and the manual "refresh" button can
  // reuse it without racing stale data onto the screen.
  const loadPreview = useCallback(() => {
    if (!selectedWeek) {
      setItems([]);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError('');
    previewPublish(selectedWeek)
      .then((data) => { if (!cancelled) setItems(data || []); })
      .catch((e) => { if (!cancelled) { setError(e.message); setItems([]); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [selectedWeek]);

  // Refetch whenever the selected week changes.
  useEffect(() => loadPreview(), [loadPreview]);

  // Auto-refresh when the admin returns to the tab/window — e.g. after editing
  // the schedule elsewhere and coming back. Keeps the preview from going stale
  // without a manual refresh.
  useEffect(() => {
    if (!selectedWeek) return undefined;
    const refetchIfVisible = () => {
      if (document.visibilityState === 'visible') loadPreview();
    };
    window.addEventListener('focus', refetchIfVisible);
    document.addEventListener('visibilitychange', refetchIfVisible);
    return () => {
      window.removeEventListener('focus', refetchIfVisible);
      document.removeEventListener('visibilitychange', refetchIfVisible);
    };
  }, [selectedWeek, loadPreview]);

  const willSend = items.filter((i) => i.would_send).length;
  const shownItems = items.filter((i) => matchesGuardSearch(i.user_name, search));
  const noSearchResults = !!search.trim() && items.length > 0 && shownItems.length === 0;

  if (weeksLoading) return <div className="loading">{messages.common.loading}</div>;

  return (
    <div className="page">
      <h2>{M.title}</h2>
      <p className="page-subtitle">{M.subtitle}</p>

      <div className="card">
        <div className="form-group">
          <label>{M.selectWeek}</label>
          <div className="preview-week-row">
            <select value={selectedWeek} onChange={(e) => setSelectedWeek(e.target.value)}>
              <option value="">{M.chooseWeek}</option>
              {weeks.map((w) => (
                <option key={w.id} value={w.id}>{w.week_label}</option>
              ))}
            </select>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={loadPreview}
              disabled={!selectedWeek || loading}
            >
              {M.refresh}
            </button>
          </div>
        </div>
        {selectedWeek && !loading && !error && (
          <div className="preview-summary">{M.summary(willSend, items.length)}</div>
        )}
        {selectedWeek && !loading && !error && items.length > 0 && (
          <GuardSearch value={search} onChange={setSearch} />
        )}
      </div>

      {!selectedWeek && <div className="empty-state">{M.noWeek}</div>}
      {error && <div className="alert alert-error">{error}</div>}
      {loading && <div className="loading">{M.loading}</div>}
      {selectedWeek && !loading && !error && items.length === 0 && (
        <div className="empty-state">{M.empty}</div>
      )}
      {noSearchResults && (
        <div className="empty-state">{messages.common.noSearchResults}</div>
      )}

      <div className="preview-list">
        {shownItems.map((item, i) => (
          <div className="card preview-card" key={`${item.telegram_id || 'no-tg'}-${i}`}>
            <div className="preview-card-head">
              <span className="preview-name">{item.user_name}</span>
              <span className={`badge ${item.would_send ? 'badge-success' : 'badge-danger'}`}>
                {item.would_send ? M.willSend : M.wontSend}
              </span>
            </div>
            <div className="preview-meta">
              <span>{M.phone}: {item.phone_number || M.noPhone}</span>
              <span>{M.telegramId}: {item.telegram_id || M.noPhone}</span>
            </div>
            <pre className="preview-message">{item.message}</pre>
          </div>
        ))}
      </div>
    </div>
  );
}
