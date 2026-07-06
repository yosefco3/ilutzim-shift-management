import { useState, useMemo } from 'react';
import useHoverScroll from '../../hooks/useHoverScroll';
import messages, { ROLE_LABELS } from '../../utils/messages';
import { warningText } from '../../utils/warnings';

// Guard attributes are UserRole enum values (ARMED, AHMASH, …) — translate via
// ROLE_LABELS, NOT the lowercase RequirementAttribute vocabulary used by positions.
const roleLabel = (key) => ROLE_LABELS[key] || key;

// "AHMASH first" pool grouping — an admin toggle persisted across sessions.
const AHMASH_FIRST_KEY = 'board.ahmashFirst';

function loadAhmashFirst() {
  try {
    return localStorage.getItem(AHMASH_FIRST_KEY) !== 'false'; // default ON
  } catch {
    return true;
  }
}

// Format hours like 12 / 9.5 (drop trailing .0).
function hoursText(h) {
  const n = Number(h) || 0;
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

// Remaining-hours colour + meter colour, mirroring the mockup thresholds:
// used-up → danger, low (≤6h) → warning, otherwise primary.
function remStyle(remaining) {
  if (remaining <= 0) return { rem: 'var(--on-danger)', meter: 'var(--danger)' };
  if (remaining <= 6) return { rem: 'var(--on-warning)', meter: 'var(--warning)' };
  return { rem: 'var(--text-dim)', meter: 'var(--primary)' };
}

function GuardCard({ g, selected, onSelect, onDismiss, attrLabel, m, warnMsgs, warnings, openNote, setOpenNote, simple = false }) {
  const remaining = g.remaining_hours ?? 0;
  const available = g.available_hours ?? 0;
  const usedPct = available > 0 ? Math.max(0, Math.min(100, ((available - remaining) / available) * 100)) : 0;
  const { rem, meter } = remStyle(remaining);
  const warnTitle = (warnings || []).map((w) => warningText(w, warnMsgs)).join('\n');

  return (
    <div
      className={`guard-card${selected ? ' selected' : ''}`}
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      draggable
      onDragStart={(e) => {
        // Carry the guard id to the drop target, and select them so the board
        // paints their availability while dragging (mirrors the design-system concept).
        e.dataTransfer.setData('text/plain', g.id);
        e.dataTransfer.effectAllowed = 'copy';
        onSelect(g.id);
      }}
      onClick={() => onSelect(selected ? null : g.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(selected ? null : g.id);
        }
      }}
    >
      <div className="guard-card-head">
        <span className="guard-card-name">
          {(warnings || []).length > 0 && (
            <span className="guard-card-warn" title={warnTitle} aria-label={warnTitle}>
              🔴
            </span>
          )}
          {g.full_name}
        </span>
        {!simple && (
          <span className="guard-card-rem" style={{ color: rem }}>
            {remaining <= 0 ? m.usedUp : `${m.remainingPrefix} ${hoursText(remaining)}${m.hoursSuffix}`}
          </span>
        )}
      </div>

      <div className="guard-card-meta">
        {!simple && (
          <span className="guard-card-avail">
            {m.available} {hoursText(available)}{m.hoursSuffix}
          </span>
        )}
        <span className="guard-card-tags">
          {onDismiss && (
            <button
              type="button"
              className="guard-card-dismiss"
              aria-label={m.dismiss}
              title={m.dismiss}
              draggable={false}
              onClick={(e) => {
                e.stopPropagation();
                onDismiss(g.id);
              }}
            >
              ×
            </button>
          )}
          {g.notes && (
            <button
              type="button"
              className="guard-card-note-btn"
              aria-label={m.note}
              title={m.note}
              onClick={(e) => {
                e.stopPropagation();
                setOpenNote(openNote === g.id ? null : g.id);
              }}
            >
              📝
            </button>
          )}
          {(g.roles || []).map((key) => (
            <span key={key} className="board-attr-chip">
              {roleLabel(key)}
            </span>
          ))}
        </span>
      </div>

      {!simple && (
        <div className="guard-card-meter">
          <div className="guard-card-meter-fill" style={{ width: `${usedPct}%`, background: meter }} />
        </div>
      )}

      {openNote === g.id && g.notes && <p className="guard-card-note">{g.notes}</p>}
    </div>
  );
}

// The guard pool panel — styled after the schedule-builder mockup. Cards show
// the guard's name, remaining hours (colour-coded), available hours, attribute
// chips, a notes button and a usage meter. A search box filters by name; guards
// who are fully used drop into a quiet "נוצלו במלואם" section. Selecting a guard
// colours the board by their availability.
// `simple` mode (the actual board): the pool is just "every active guard" —
// no submitted availability, no remaining-hours math — so the hour meta and
// the used-up section are hidden and every guard stays in the active list.
export default function GuardPool({
  guards,
  selectedId,
  onSelect,
  attrLabel = (k) => k,
  guardWarnings = {},
  dismissedIds = new Set(),
  onDismiss,
  onRestore,
  simple = false,
  subtitle,
}) {
  const m = messages.board.pool;
  const warnMsgs = messages.board.warn;
  const [openNote, setOpenNote] = useState(null);
  const [search, setSearch] = useState('');
  const [ahmashFirst, setAhmashFirst] = useState(loadAhmashFirst);
  // Arrow keys scroll the pool while the pointer is over it (04·nav).
  const { ref: scrollRef, handlers: scrollHandlers } = useHoverScroll();

  const toggleAhmashFirst = () => {
    setAhmashFirst((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(AHMASH_FIRST_KEY, String(next));
      } catch {
        // Private mode etc. — the toggle still works for this session.
      }
      return next;
    });
  };

  const { active, done, dismissed } = useMemo(() => {
    const term = search.trim();
    const filtered = term ? guards.filter((g) => g.full_name.includes(term)) : guards;
    // Guards the admin manually hid from the pool for this session — pulled out
    // of the working list into a quiet, restorable section at the bottom.
    const dismissed = filtered.filter((g) => dismissedIds.has(g.id));
    let visible = filtered.filter((g) => !dismissedIds.has(g.id));
    // "AHMASH first" toggle: a stable partition — AHMASH guards lead, everyone
    // else follows, and the incoming sort order is kept within each group.
    if (ahmashFirst) {
      const isAhmash = (g) => (g.roles || []).includes('AHMASH');
      visible = [...visible.filter(isAhmash), ...visible.filter((g) => !isAhmash(g))];
    }
    // While you're actively assigning a guard, keep him pinned to the top of the
    // list — even after a shift drops his remaining hours and the backend re-sorts
    // him down (or fully uses him up). He only falls back into his sorted slot,
    // or down into the "used up" section, once he's deselected.
    const pinned = selectedId != null ? visible.find((g) => g.id === selectedId) : null;
    const rest = pinned ? visible.filter((g) => g.id !== selectedId) : visible;
    const active = simple ? rest : rest.filter((g) => (g.remaining_hours ?? 0) > 0);
    const done = simple ? [] : rest.filter((g) => (g.remaining_hours ?? 0) <= 0);
    if (pinned) active.unshift(pinned);
    return { active, done, dismissed };
  }, [guards, search, selectedId, dismissedIds, simple, ahmashFirst]);

  if (!guards.length) {
    return <aside className="guard-pool empty">{m.empty}</aside>;
  }

  const cardProps = { onSelect, onDismiss, attrLabel, m, warnMsgs, openNote, setOpenNote, simple };

  return (
    <aside className="guard-pool" aria-label={m.title} ref={scrollRef} {...scrollHandlers}>
      <div className="guard-pool-head">
        <h2 className="guard-pool-title">{m.title}</h2>
        <span className="guard-pool-sub">{subtitle || m.sortedBy}</span>
      </div>
      <div className="guard-pool-ahmash-toggle">
        <button
          type="button"
          role="switch"
          aria-checked={ahmashFirst}
          className={`switch ${ahmashFirst ? 'on' : 'off'}`}
          onClick={toggleAhmashFirst}
        >
          <span className="switch-track"><span className="switch-thumb" /></span>
          <span className="switch-label">{m.ahmashFirst}</span>
        </button>
      </div>
      <input
        className="guard-pool-search"
        type="search"
        value={search}
        placeholder={m.search}
        aria-label={m.search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <p className="guard-pool-hint">{selectedId ? m.hintSelected : m.hint}</p>

      <div className="guard-pool-list">
        {active.map((g) => (
          <GuardCard key={g.id} g={g} selected={g.id === selectedId} warnings={guardWarnings[g.id]} {...cardProps} />
        ))}
      </div>

      {done.length > 0 && (
        <div className="guard-pool-done">
          <div className="guard-pool-done-title">{m.usedSection} · {done.length}</div>
          <div className="guard-pool-list">
            {done.map((g) => (
              <GuardCard key={g.id} g={g} selected={g.id === selectedId} warnings={guardWarnings[g.id]} {...cardProps} />
            ))}
          </div>
        </div>
      )}

      {dismissed.length > 0 && (
        <div className="guard-pool-dismissed">
          <div className="guard-pool-done-title">{m.dismissedSection} · {dismissed.length}</div>
          <div className="guard-pool-dismissed-list">
            {dismissed.map((g) => (
              <button
                key={g.id}
                type="button"
                className="guard-pool-dismissed-chip"
                title={m.restore}
                onClick={() => onRestore?.(g.id)}
              >
                {g.full_name} ↺
              </button>
            ))}
          </div>
        </div>
      )}
    </aside>
  );
}
