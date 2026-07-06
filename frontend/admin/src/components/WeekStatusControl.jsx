/**
 * WeekStatusControl — action buttons for a single week card. (The status pill
 * is the exported WeekStatusBadge, rendered by WeeksPage in the card header.)
 *
 * Props: week, onOpen, onLock, onPublish, loading, autoOpen, autoLock, isCurrent,
 *        isOpenTarget
 *
 * When auto-open/auto-lock is enabled the corresponding manual button is hidden
 * (the scheduler manages it) and a "will happen automatically" indicator is
 * shown instead. "Publish" is always manual and shown only on the *current*,
 * CLOSED week — publishing never locks, it just broadcasts and stamps
 * ``published_at``. Before it was ever published → "פרסם"; once ``published_at``
 * is set → "עדכן ופרסם מחדש" (re-publish). Both stay CLOSED and remain available
 * until the weekly rollover locks the week (LOCKED → terminal, no actions).
 *
 * "Open" is shown ONLY when ``isOpenTarget`` — the single upcoming, never-opened
 * week when no other week is OPEN (no reopening; the parent computes this). An old
 * CLOSED week or a LOCKED week never shows an open/reopen affordance.
 */
import { useState } from 'react';
import messages from '../utils/messages';
import { formatSchedule } from '../utils/automation';
import ConfirmDialog from './ConfirmDialog';

const A = messages.weeks.automation;

// 3-state model: CLOSED (reopenable) / OPEN / LOCKED (final).
// Colors come from the dark-indigo theme vars (the old hardcoded hex predated it).
const STATUS_CFG = {
  closed:    { label: messages.weeks.statusClosed,    bg: 'var(--surface-2)',      color: 'var(--text-muted)', icon: '⏳' },
  open:      { label: messages.weeks.statusOpen,      bg: 'var(--success-soft)',   color: 'var(--on-success)', icon: '🔓' },
  locked:    { label: messages.weeks.statusLocked,    bg: 'var(--warning-soft)',   color: 'var(--on-warning)', icon: '🔒' },
};

// The status pill, rendered by WeeksPage in the card header (separated from the
// action buttons so the card reads top-down: identity → state → actions).
export function WeekStatusBadge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.closed;
  return (
    <span
      className="week-status-badge"
      style={{ background: cfg.bg, color: cfg.color }}
    >
      {cfg.icon} {cfg.label}
    </span>
  );
}

export default function WeekStatusControl({
  week,
  onOpen,
  onLock,
  onPublish,
  loading,
  autoOpen = { enabled: false },
  autoLock = { enabled: false },
  isCurrent = false,
  isOpenTarget = false,
  isPublishing = false,
}) {
  const status = week.status || 'closed';
  const [showPublishConfirm, setShowPublishConfirm] = useState(false);
  const [showRepublishConfirm, setShowRepublishConfirm] = useState(false);

  return (
    <>
      <div className="week-card-actions">
        {/* Action buttons by status (3-state model). The status badge itself is
            rendered by the parent (WeekStatusBadge in the card header). */}
        <div className="week-card-buttons">
          {/* Only the single upcoming, never-opened week may be opened (no
              reopening). Manual button unless auto-open manages it. */}
          {isOpenTarget && !autoOpen.enabled && (
            <button
              className="btn btn-primary btn-sm"
              disabled={loading}
              onClick={() => onOpen(week.id)}
            >
              🟢 {messages.weeks.openForSubmission}
            </button>
          )}

          {isOpenTarget && autoOpen.enabled && (
            <span className="week-auto-indicator">
              ⏰ {A.willOpenAuto} · {formatSchedule(autoOpen.weekday, autoOpen.time)}
            </span>
          )}

          {/* CLOSED (current week) → publish. Publishing keeps the week CLOSED
              (never locks): it broadcasts each guard their personal schedule and
              stamps published_at (see WeeksPage.handlePublish). Before it was ever
              published → "פרסם"; once published_at is set → re-publish. */}
          {status === 'closed' && isCurrent && !week.published_at && (
            <button
              className="btn btn-success btn-sm"
              disabled={loading || isPublishing}
              onClick={() => setShowPublishConfirm(true)}
            >
              {messages.weeks.published}
            </button>
          )}

          {status === 'closed' && isCurrent && week.published_at && (
            <button
              className="btn btn-warning btn-sm"
              disabled={loading || isPublishing}
              onClick={() => setShowRepublishConfirm(true)}
            >
              {messages.weeks.republish}
            </button>
          )}

          {/* OPEN → can be closed (submission window ends → CLOSED, reopenable). */}
          {status === 'open' && !autoLock.enabled && (
            <button
              className="btn btn-warning btn-sm"
              disabled={loading}
              onClick={() => onLock(week.id)}
            >
              🔒 {messages.weeks.closeForSubmission}
            </button>
          )}

          {status === 'open' && autoLock.enabled && (
            <span className="week-auto-indicator">
              ⏰ {A.willLockAuto} · {formatSchedule(autoLock.weekday, autoLock.time)}
            </span>
          )}

          {/* LOCKED is terminal — no actions. */}
        </div>
      </div>

      {showPublishConfirm && (
        <ConfirmDialog
          title={messages.weeks.publishConfirmTitle}
          message={messages.weeks.publishConfirm}
          confirmLabel={messages.weeks.publishConfirmLabel}
          onConfirm={() => { setShowPublishConfirm(false); onPublish(week.id); }}
          onCancel={() => setShowPublishConfirm(false)}
        />
      )}

      {showRepublishConfirm && (
        <ConfirmDialog
          title={messages.weeks.republishConfirmTitle}
          message={messages.weeks.republishConfirm}
          confirmLabel={messages.weeks.republishConfirmLabel}
          onConfirm={() => { setShowRepublishConfirm(false); onPublish(week.id); }}
          onCancel={() => setShowRepublishConfirm(false)}
        />
      )}
    </>
  );
}