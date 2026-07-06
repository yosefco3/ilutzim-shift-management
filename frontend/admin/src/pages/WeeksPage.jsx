import { useEffect, useState } from 'react';
import { useWeeks } from '../hooks/useWeeks';
import { useSettings } from '../hooks/useSettings';
import WeekStatusControl, { WeekStatusBadge } from '../components/WeekStatusControl';
import WeekQuickLinks from '../components/WeekQuickLinks';
import messages from '../utils/messages';
import { deriveAutomation, formatSchedule } from '../utils/automation';
import { exportExcel } from '../api/adminApiClient';
import { listSavedSchedules, downloadSavedSchedule, saveSchedule, exportActualScheduleGrid } from '../api/builderApiClient';
import { triggerBlobDownload, weeklyExportFilename } from '../utils/download';
import { resolvePublishableWeek } from '../utils/weeks';
import { useToast } from '../components/Toast';

const A = messages.weeks.automation;

export default function WeeksPage() {
  const { weeks, loading, setStatus, openForSubmission, publish } = useWeeks();
  const { settings, loading: settingsLoading } = useSettings();
  const { autoOpen, autoLock } = deriveAutomation(settings);
  const automationOn = autoOpen.enabled || autoLock.enabled;
  const toast = useToast();

  // In-flight guard for publish: a publish broadcasts to every guard (seconds),
  // so a double-click on the same ConfirmDialog must not fire two publishes. This
  // is per-week and local — the global useWeeks `loading` only covers the initial
  // fetch, not the publish round-trip (F-1).
  const [publishingWeekId, setPublishingWeekId] = useState(null);

  // Weeks that have a saved schedule snapshot → show a download button on them.
  // The builder router may be feature-flagged off; failure just means no buttons.
  const [savedWeekIds, setSavedWeekIds] = useState(() => new Set());
  useEffect(() => {
    let cancelled = false;
    listSavedSchedules()
      .then((rows) => {
        if (!cancelled) setSavedWeekIds(new Set(rows.map((r) => r.week_id)));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const handleDownloadSchedule = async (week) => {
    const blob = await downloadSavedSchedule(week.id);
    triggerBlobDownload(blob, weeklyExportFilename('schedule', week.start_date));
  };

  // Started week → the ACTUAL schedule ("what really happened", incl. mid-week
  // edits) instead of the frozen planned snapshot.
  const handleDownloadActualSchedule = async (week) => {
    try {
      const blob = await exportActualScheduleGrid(week.id);
      triggerBlobDownload(blob, weeklyExportFilename('actual_schedule', week.start_date));
    } catch (err) {
      toast.error(err?.message || messages.common.error);
    }
  };

  // Direct per-week constraints export — replaced the standalone /export page
  // (which was just a week picker in front of this same call).
  const handleExportConstraints = async (week) => {
    try {
      const blob = await exportExcel(week.id);
      triggerBlobDownload(blob, weeklyExportFilename('constraints', week.start_date));
    } catch (err) {
      toast.error(err?.message || messages.common.error);
    }
  };

  const handleOpen = async (weekId) => {
    // The backend now enforces no-reopen / single-open; surface its rejection
    // (e.g. "already ran", "another week open") as a toast instead of failing
    // silently.
    try {
      await openForSubmission(weekId);
    } catch (err) {
      toast.error(err?.message || messages.common.error);
    }
  };

  const handleLock = async (weekId) => {
    // Close the submission window → CLOSED (reopenable, admin can still edit).
    try {
      await setStatus(weekId, 'closed');
    } catch (err) {
      toast.error(err?.message || messages.common.error);
    }
  };

  const handlePublish = async (weekId) => {
    if (publishingWeekId) return; // a publish is already in flight — ignore (F-1)
    setPublishingWeekId(weekId);
    try {
      const summary = await publish(weekId);
      const { sent = 0, failed = 0, total = 0, republished = false } = summary || {};
      // Publishing (and re-publishing) also snapshots the built schedule so it
      // stays downloadable (and survives later profile deletion). A save failure
      // must not undo the successful publish, so it only surfaces a warning.
      try {
        await saveSchedule(weekId);
        setSavedWeekIds((prev) => new Set(prev).add(weekId));
      } catch {
        toast.error(messages.weeks.scheduleSaveFailed);
        return;
      }
      if (failed > 0) {
        toast.warning(messages.weeks.publishPartial(sent, failed, total));
      } else {
        toast.success(
          republished
            ? messages.weeks.republishedToast(sent, total)
            : messages.weeks.publishedToast(sent, total),
        );
      }
    } catch (err) {
      toast.error(err?.message || messages.common.error);
    } finally {
      setPublishingWeekId(null);
    }
  };

  // Wait for settings too, so the manual/auto buttons don't flicker on load.
  if (loading || settingsLoading) return <div className="loading">{messages.common.loading}</div>;

  const slot = (block) =>
    block.enabled ? formatSchedule(block.weekday, block.time) : A.manual;

  // The week the publish button belongs to = the nearest week that has NOT
  // STARTED yet (start_date > today) — the upcoming week guards submitted for,
  // finalized before it goes live. Once a week starts there is nothing left to
  // publish, so the button moves to the next upcoming week. Falls back to the
  // latest week only when no upcoming week exists — the same rule the backend
  // uses to decide which week still shows publish / re-publish (see week_service
  // _is_publishable_week). Shared with the publish-preview default (utils/weeks).
  const now = new Date();
  const todayIso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  const byStartDesc = (a, b) => (b.start_date || '').localeCompare(a.start_date || '');
  const upcoming = weeks
    .filter((w) => (w.start_date || '') > todayIso)
    .sort((a, b) => (a.start_date || '').localeCompare(b.start_date || ''));
  const currentWeekId = resolvePublishableWeek(weeks, now)?.id;

  // "Open" is offered ONLY for the single upcoming, never-opened week, and only
  // when no other week is already OPEN (single-open + no-reopen product rule).
  // An old CLOSED week (already ran its window → opened_at set) or a LOCKED week
  // never shows an open/reopen affordance. Mirrors the backend guard in
  // change_week_status.
  const anyOpenWeek = weeks.some((w) => (w.status || 'closed') === 'open');
  const openTarget = anyOpenWeek
    ? null
    : upcoming.find((w) => (w.status || 'closed') === 'closed' && !w.opened_at);
  const openTargetId = openTarget?.id;

  // A week stays in the "active" group (top) until it reaches LOCKED (the Sunday
  // rollover). LOCKED is terminal — no more publish/edit — so it drops to the
  // inactive group. Publishing keeps a week CLOSED, so it stays active (and keeps
  // its re-publish button) right up until the rollover locks it.
  const isActive = (w) => (w.status || 'closed') !== 'locked';
  const activeWeeks = weeks.filter(isActive).sort(byStartDesc);
  const inactiveWeeks = weeks.filter((w) => !isActive(w)).sort(byStartDesc);

  // "פורסם לאחרונה 03/07, 21:15" — day/month + time is enough; the year is on
  // the card's date range anyway.
  const publishedAtLabel = (iso) =>
    new Date(iso).toLocaleString('he-IL', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    });

  const renderCard = (w) => {
    const isCurrent = w.id === currentWeekId;
    const isLockedWeek = (w.status || 'closed') === 'locked';
    return (
      <div
        key={w.id}
        className={`week-card${isCurrent ? ' week-card-current' : ''}${isLockedWeek ? ' week-card-inactive' : ''}`}
      >
        <div className="week-card-header">
          <div className="week-card-title">
            <span className="week-card-date">📅 {w.start_date} — {w.end_date}</span>
            <span className="week-card-label">{w.week_label}</span>
          </div>
          <div className="week-card-badges">
            {isCurrent && (
              <span className="week-chip-current">{messages.weeks.currentChip}</span>
            )}
            <WeekStatusBadge status={w.status} />
          </div>
        </div>
        {/* LOCKED weeks are archive: header + quick links only — no meta, no
            actions (LOCKED is terminal anyway). */}
        {!isLockedWeek && (
          <>
            <div className="week-card-meta">
              <span>📋 {w.submission_count ?? 0} {messages.weeks.submissionCount}</span>
              {w.published_at && (
                <span>📢 {messages.weeks.lastPublished} {publishedAtLabel(w.published_at)}</span>
              )}
            </div>
            <WeekStatusControl
              week={w}
              onOpen={handleOpen}
              onLock={handleLock}
              onPublish={handlePublish}
              loading={loading}
              autoOpen={autoOpen}
              autoLock={autoLock}
              isCurrent={isCurrent}
              isOpenTarget={w.id === openTargetId}
              isPublishing={publishingWeekId === w.id}
            />
          </>
        )}
        <WeekQuickLinks
          week={w}
          todayIso={todayIso}
          isCurrent={isCurrent}
          hasSavedSchedule={savedWeekIds.has(w.id)}
          onExportConstraints={handleExportConstraints}
          onDownloadSchedule={handleDownloadSchedule}
          onDownloadActualSchedule={handleDownloadActualSchedule}
        />
      </div>
    );
  };

  return (
    <div className="page">
      <div className="page-header">
        <h2>{messages.weeks.title}</h2>
      </div>

      {automationOn && (
        <div className="automation-banner">
          🤖 {A.bannerOpen}: {slot(autoOpen)} · {A.bannerLock}: {slot(autoLock)} · {A.bannerPublish}: {A.manual}
        </div>
      )}

      {!weeks.length ? (
        <p className="empty-state">{messages.weeks.empty}</p>
      ) : (
        <>
          {activeWeeks.length > 0 && (
            <div className="week-cards">
              {activeWeeks.map(renderCard)}
            </div>
          )}

          {inactiveWeeks.length > 0 && (
            <>
              <h3 className="week-section-title">{messages.weeks.inactiveSection}</h3>
              <div className="week-cards">
                {inactiveWeeks.map(renderCard)}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}