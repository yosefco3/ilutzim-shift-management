import { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useWeeks } from '../hooks/useWeeks';
import { useSubmissions } from '../hooks/useSubmissions';
import StatusGrid from '../components/StatusGrid';
import GuardSearch from '../components/GuardSearch';
import { useToast } from '../components/Toast';
import { sendWeekReminders, fetchConstraintRules } from '../api/adminApiClient';
import { matchesGuardSearch } from '../utils/sorting';
import messages from '../utils/messages';

// The schedule board ("לוח הסידור") always targets the upcoming Sunday→Saturday
// week — the same week guards submit for — resolved on the backend as
// week_range(today) (see date_utils.upcoming_sunday). Mirror that Sunday here so
// the reports default matches the board even when the week is closed/locked.
function upcomingSundayIso(now = new Date()) {
  // JS getDay(): Sun=0 … Sat=6. Days to the *next* Sunday, strictly future
  // (Sunday itself skips a week), matching the backend's upcoming_sunday.
  const daysAhead = (7 - now.getDay()) % 7 || 7;
  const sun = new Date(now.getFullYear(), now.getMonth(), now.getDate() + daysAhead);
  const pad = (n) => String(n).padStart(2, '0');
  return `${sun.getFullYear()}-${pad(sun.getMonth() + 1)}-${pad(sun.getDate())}`;
}

export default function SubmissionsPage() {
  const { weeks, loading: weeksLoading } = useWeeks();
  // ?week=<id> — deep link from a week card's דיווחים quick-link. Lands on
  // THIS page (the editable one, with מילוי אילוצים) with the week preselected.
  const [searchParams] = useSearchParams();
  const [selectedWeek, setSelectedWeek] = useState('');
  const { submissions, detailedData, loading: subsLoading, acknowledgeViolation } = useSubmissions(selectedWeek, { detailed: true });
  const toast = useToast();
  const [reminding, setReminding] = useState(false);

  const [showInactive, setShowInactive] = useState(false);
  const [search, setSearch] = useState('');

  // Constraint-rule thresholds — drive the soft warnings shown per submission.
  // Fetched once; failure is silent (warnings simply won't appear).
  const [rules, setRules] = useState(null);
  useEffect(() => {
    fetchConstraintRules().then(setRules).catch(() => {});
  }, []);

  // Default the week selector to the board's week — the upcoming Sun→Saturday
  // week the schedule board targets — once weeks load. That's the week the admin
  // almost always wants, regardless of whether it's still open or already
  // closed/locked, so the default now tracks the board rather than only firing
  // for an 'open' week. Falls back to the open week (then nothing) if the board
  // week isn't in the list yet. Runs once; the admin can still pick another week.
  const didInitWeek = useRef(false);
  useEffect(() => {
    if (didInitWeek.current || !weeks.length) return;
    didInitWeek.current = true;
    // An explicit ?week= deep link wins over the board-week default; an unknown
    // id just falls through to the default.
    const requested = searchParams.get('week');
    if (requested && weeks.some((w) => String(w.id) === requested)) {
      setSelectedWeek(requested);
      return;
    }
    const boardSunday = upcomingSundayIso();
    const boardWeek = weeks.find((w) => w.start_date === boardSunday);
    const target = boardWeek || weeks.find((w) => w.status === 'open');
    if (target) setSelectedWeek(String(target.id));
  }, [weeks, searchParams]);

  const loading = weeksLoading || subsLoading;

  // Admins may fill and edit constraints while a week is 'closed' / 'open' —
  // only a 'locked' week is final and blocks editing for everyone, including the
  // admin (matches the backend: create_submission(override_lock=True) rejects a
  // LOCKED week). Regular guards are blocked on anything but 'open'; that gate
  // lives on the guard side, not here.
  const selectedWeekObj = weeks.find((w) => String(w.id) === String(selectedWeek));
  const canFillConstraints = !!selectedWeekObj && selectedWeekObj.status !== 'locked';

  // Map each guard's user_id to their detailed submission (days + notes)
  const detailsByUser = {};
  for (const s of detailedData?.submitted || []) {
    detailsByUser[s.user_id] = s;
  }

  // Active guards are the default view; inactive guards live in a separate,
  // collapsible list. (Older API responses without is_active count as active.)
  const activeSubmissions = submissions.filter((s) => s.is_active !== false);
  const inactiveSubmissions = submissions.filter((s) => s.is_active === false);

  // Only active guards receive reminders, so count missing among them only.
  // Counted before the name search filter so the reminder total reflects the
  // whole week, not just the rows currently shown.
  const missingCount = activeSubmissions.filter((s) => !s.submitted_at).length;

  // Name search narrows only the displayed rows.
  const matchesSearch = (s) => matchesGuardSearch(s.full_name || s.user_id, search);
  const activeShown = activeSubmissions.filter(matchesSearch);
  const inactiveShown = inactiveSubmissions.filter(matchesSearch);
  const noSearchResults = !!search.trim() && activeShown.length === 0 && inactiveShown.length === 0;

  async function handleAcknowledgeViolation(submissionId) {
    try {
      await acknowledgeViolation(submissionId, true);
      toast.success(messages.submissions.violationAcknowledged);
    } catch (err) {
      toast.error(messages.common.error + ': ' + err.message);
    }
  }

  async function handleRemind() {
    if (!selectedWeek || reminding) return;
    setReminding(true);
    try {
      const result = await sendWeekReminders(selectedWeek);
      if (result?.reminded > 0) {
        toast.success(`${messages.submissions.reminderSent} (${result.reminded})`);
      } else if (result?.skipped_no_telegram > 0) {
        // Someone still hasn't submitted but has no Telegram linked, so no
        // reminder could be delivered — say so instead of "everyone submitted".
        toast.info(`${messages.submissions.reminderNoTelegram} (${result.skipped_no_telegram})`);
      } else {
        toast.info(messages.submissions.reminderNone);
      }
    } catch (err) {
      toast.error(messages.common.error + ': ' + err.message);
    } finally {
      setReminding(false);
    }
  }

  return (
    <div className="page">
      <h2>{messages.submissions.title}</h2>
      <div className="form-group">
        <label>{messages.submissions.selectWeek}</label>
        <select value={selectedWeek} onChange={(e) => setSelectedWeek(e.target.value)}>
          <option value="">{messages.submissions.chooseWeek}</option>
          {weeks.map((w) => (
            <option key={w.id} value={w.id}>{w.week_label}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <div className="loading">{messages.common.loading}</div>
      ) : selectedWeek ? (
        <>
          {missingCount > 0 && (
            <div className="submissions-actions">
              <span className="submissions-missing-count">
                <strong>{missingCount}</strong> {messages.submissions.missingCount}
              </span>
              <button className="btn btn-primary" onClick={handleRemind} disabled={reminding}>
                <span aria-hidden="true">🔔</span>
                {reminding ? messages.submissions.reminding : messages.submissions.remind}
              </button>
            </div>
          )}

          {submissions.length > 0 && <GuardSearch value={search} onChange={setSearch} />}

          {noSearchResults ? (
            <p className="empty-state">{messages.common.noSearchResults}</p>
          ) : (
            <>
              <StatusGrid
                submissions={activeShown}
                detailsByUser={detailsByUser}
                canFillConstraints={canFillConstraints}
                rules={rules}
                onAcknowledgeViolation={handleAcknowledgeViolation}
              />

              {inactiveShown.length > 0 && (
                <div className="inactive-section">
                  <button
                    type="button"
                    className="btn btn-outline inactive-toggle"
                    onClick={() => setShowInactive((v) => !v)}
                    aria-expanded={showInactive}
                  >
                    <span aria-hidden="true">{showInactive ? '▾' : '▸'}</span>
                    {messages.submissions.inactiveToggle} ({inactiveShown.length})
                  </button>
                  {showInactive && (
                    <StatusGrid
                      submissions={inactiveShown}
                      detailsByUser={detailsByUser}
                      canFillConstraints={canFillConstraints}
                      rules={rules}
                    />
                  )}
                </div>
              )}
            </>
          )}
        </>
      ) : (
        <p className="empty-state">{messages.submissions.selectWeekPrompt}</p>
      )}
    </div>
  );
}