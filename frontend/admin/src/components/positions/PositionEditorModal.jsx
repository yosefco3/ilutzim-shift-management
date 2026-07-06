/**
 * PositionEditorModal — THE position form, shared by both boards.
 *
 * Extracted from PositionsPage (user feedback 5/7: the actual board must use
 * the same form as the profile's position editor, not an ad-hoc one). One
 * form, one behaviour: name, event flag + fixed count, the 7-day half-hour
 * grid with duration hints, and the required-attribute checkboxes.
 *
 * Self-contained: owns its form state (re-seeded whenever it opens on a new
 * target) and submits a ready API payload — the callers decide what create/
 * update means on their side (profile position vs actual-board position).
 */
import { useEffect, useState } from 'react';
import messages from '../../utils/messages';
import {
  DAY_NAMES_SHORT as DAY_NAMES,
  DAY_HALF_HOUR_OPTIONS,
} from '../../utils/guardMessages.js';

// Build a blank editor form, optionally seeded from an existing position
// ({name, day_schedules, required_attributes, is_event, event_required_count}).
function makeForm(position) {
  const days = {};
  for (let i = 0; i < 7; i += 1) {
    const key = String(i);
    const existing = position?.day_schedules?.[key];
    days[i] = {
      active: !!existing,
      start: existing?.start || '07:00',
      end: existing?.end || '15:00',
    };
  }
  return {
    name: position?.name || '',
    days,
    required: new Set(position?.required_attributes || []),
    is_event: !!position?.is_event,
    // Event-only fixed participant count. '' = unlimited. Stored as a string for
    // the number input; coerced to int|null on save.
    event_required_count:
      position?.event_required_count != null
        ? String(position.event_required_count)
        : '',
  };
}

// Valid end-times for a given start: every half-hour slot *after* the start,
// continuing along the 07:00→07:00 security day and ending at 07:00 the next
// morning (inclusive). DAY_HALF_HOUR_OPTIONS[0] is "07:00" (day start), so the
// terminal "07:00" we append represents the *next-day* boundary.
export function endOptionsFor(start) {
  const i = DAY_HALF_HOUR_OPTIONS.indexOf(start);
  return [...DAY_HALF_HOUR_OPTIONS.slice(i + 1), '07:00'];
}

// Duration of a shift in hours, treating the end as always *after* the start:
// the security day runs 07:00 → 07:00, so an end at/<= start wraps to the next
// day (07:00→17:00 = 10h; 23:00→07:00 = 8h; 07:00→07:00 = a full 24h).
export function shiftHours(start, end) {
  const toMin = (t) => {
    const [h, m] = t.split(':').map(Number);
    return h * 60 + m;
  };
  let diff = (toMin(end) - toMin(start) + 1440) % 1440;
  if (diff === 0) diff = 1440;
  const h = diff / 60;
  return Number.isInteger(h) ? h : h.toFixed(1);
}

// Collapse the editor's day grid into the API's day_schedules map.
function toDaySchedules(days) {
  const out = {};
  Object.entries(days).forEach(([i, d]) => {
    if (d.active) out[String(i)] = { start: d.start, end: d.end };
  });
  return out;
}

export default function PositionEditorModal({
  open,
  position = null, // existing position to edit, or null to create
  attributes = [],
  onSave, // async (payload) — payload is the ready create/update body
  onCancel,
  onInvalidDays, // called when saving with no active day (caller toasts)
}) {
  const m = messages.positions;
  const editing = position != null;
  const [editor, setEditor] = useState(() => makeForm(position));

  // Re-seed the form whenever the dialog opens on a (different) target.
  useEffect(() => {
    if (open) setEditor(makeForm(position));
  }, [open, position]);

  if (!open) return null;

  const toggleRequirement = (key) => {
    setEditor((prev) => {
      const required = new Set(prev.required);
      if (required.has(key)) required.delete(key);
      else required.add(key);
      return { ...prev, required };
    });
  };

  const setDay = (i, patch) => {
    setEditor((prev) => {
      const day = { ...prev.days[i], ...patch };
      // When the start moves, keep the end valid: it must stay *after* start
      // (within the 07:00→07:00 day). Snap to the earliest valid slot if not.
      if (patch.start !== undefined) {
        const opts = endOptionsFor(day.start);
        if (!opts.includes(day.end)) day.end = opts[0];
      }
      return { ...prev, days: { ...prev.days, [i]: day } };
    });
  };

  const handleSave = async (e) => {
    e.preventDefault();
    const body = {
      name: editor.name.trim(),
      day_schedules: toDaySchedules(editor.days),
      required_attributes: Array.from(editor.required),
      is_event: editor.is_event,
      // Event-only: a fixed participant count, or null for unlimited. Cleared
      // whenever the position isn't an event.
      event_required_count:
        editor.is_event && editor.event_required_count !== ''
          ? Number(editor.event_required_count)
          : null,
    };
    if (!body.name) return;
    if (!Object.keys(body.day_schedules).length) {
      onInvalidDays?.();
      return;
    }
    await onSave(body);
  };

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content modal-wide" onClick={(e) => e.stopPropagation()}>
        <h3 className="modal-title">{editing ? m.editTitle : m.addTitle}</h3>
        <form onSubmit={handleSave}>
          <div className="form-group">
            <label htmlFor="pos-name">{m.name}</label>
            <input
              id="pos-name"
              type="text"
              aria-label={m.name}
              autoFocus
              placeholder={m.namePlaceholder}
              value={editor.name}
              onChange={(e) => setEditor({ ...editor, name: e.target.value })}
            />
          </div>

          <div className="form-group">
            <label className="event-toggle">
              <input
                type="checkbox"
                aria-label={m.eventLabel}
                checked={editor.is_event}
                onChange={(e) =>
                  setEditor({
                    ...editor,
                    is_event: e.target.checked,
                    // Leaving event mode clears any fixed count.
                    event_required_count: e.target.checked
                      ? editor.event_required_count
                      : '',
                  })
                }
              />
              {m.eventLabel}
            </label>
            {editor.is_event && (
              <div className="event-count">
                <label htmlFor="event-required-count">{m.eventCountLabel}</label>
                <input
                  id="event-required-count"
                  type="number"
                  min="1"
                  step="1"
                  inputMode="numeric"
                  placeholder={m.eventCountUnlimited}
                  value={editor.event_required_count}
                  onChange={(e) =>
                    setEditor({ ...editor, event_required_count: e.target.value })
                  }
                />
                <p className="form-hint">{m.eventCountHint}</p>
              </div>
            )}
          </div>

          <div className="form-group">
            <label>{m.days}</label>
            <p className="form-hint">{m.hoursHint}</p>
            <div className="day-grid">
              {DAY_NAMES.map((dayName, i) => (
                <div key={i} className="day-row">
                  <label className="day-toggle">
                    <input
                      type="checkbox"
                      aria-label={dayName}
                      checked={editor.days[i].active}
                      onChange={(e) => setDay(i, { active: e.target.checked })}
                    />
                    {dayName}
                  </label>
                  <select
                    aria-label={`${dayName}-${m.start}`}
                    disabled={!editor.days[i].active}
                    value={editor.days[i].start}
                    onChange={(e) => setDay(i, { start: e.target.value })}
                  >
                    {DAY_HALF_HOUR_OPTIONS.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                  <select
                    aria-label={`${dayName}-${m.end}`}
                    disabled={!editor.days[i].active}
                    value={editor.days[i].end}
                    onChange={(e) => setDay(i, { end: e.target.value })}
                  >
                    {endOptionsFor(editor.days[i].start).map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                  <span className="day-duration">
                    {editor.days[i].active
                      ? `${shiftHours(editor.days[i].start, editor.days[i].end)} ${m.hours}`
                      : ''}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label>{m.requirements}</label>
            {!attributes.length ? (
              <p className="empty-state">{m.noRequirements}</p>
            ) : (
              <div className="requirement-checks">
                {attributes.map((a) => (
                  <label key={a.id} className="requirement-check">
                    <input
                      type="checkbox"
                      aria-label={a.label}
                      checked={editor.required.has(a.key)}
                      onChange={() => toggleRequirement(a.key)}
                    />
                    {a.label}
                  </label>
                ))}
              </div>
            )}
          </div>

          <div className="modal-actions">
            <button type="submit" className="btn btn-primary" disabled={!editor.name.trim()}>
              {messages.common.save}
            </button>
            <button type="button" className="btn btn-secondary" onClick={onCancel}>
              {messages.common.cancel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
