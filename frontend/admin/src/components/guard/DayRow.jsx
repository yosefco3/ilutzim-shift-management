/**
 * Single day row — three shift toggles (morning / afternoon / night),
 * each with its own custom hours inputs.  Mobile-first.
 */
import {
  messages,
  DAY_NAMES,
  SHIFT_TYPES,
  SHIFT_LABELS,
  shiftTimeOptions,
} from "../../utils/guardMessages.js";

/**
 * Build the <option> list for a time dropdown from the security-day-constrained
 * options for this field/shift type. If the current value isn't one of them
 * (e.g. legacy data such as 06:30), it's prepended so it still displays instead
 * of being silently changed to the first slot.
 */
function timeOptions(value, opts) {
  const list = value && !opts.includes(value) ? [value, ...opts] : opts;
  return [
    // Keep an empty slot so a blank value shows as blank (not a wrong slot).
    !value && (
      <option key="" value="">
        --
      </option>
    ),
    ...list.map((t) => (
      <option key={t} value={t}>
        {t}
      </option>
    )),
  ];
}

/**
 * @param {object} props
 * @param {object} props.day - { day_index, blocked, shifts: { morning: {active, from_hour, to_hour}, afternoon: …, night: … } }
 * @param {boolean} props.disabled - Whether the form is locked
 * @param {Function} props.onToggleShift - (dayIndex, shiftType) => void
 * @param {Function} props.onSetShiftHours - (dayIndex, shiftType, from, to) => void
 */
export default function DayRow({
  day,
  disabled,
  onToggleShift,
  onSetShiftHours,
}) {
  const dayName = DAY_NAMES[day.day_index] || `יום ${day.day_index}`;
  const isBlocked = day.blocked;
  const isDisabled = disabled || isBlocked;

  return (
    <div className={`day-row ${isBlocked ? "blocked" : ""}`}>
      {/* Day header */}
      <div className="day-header">
        <span className="day-name">{dayName}</span>
        {isBlocked && (
          <span className="blocked-badge">{messages.LABEL_BLOCKED}</span>
        )}
      </div>

      {/* Shift toggles */}
      {!isBlocked && (
        <div className="day-shifts">
          {SHIFT_TYPES.map((st) => {
            const shift = day.shifts[st];
            const label = SHIFT_LABELS[st];

            return (
              <div
                key={st}
                className={`shift-row ${shift.active ? "active" : ""}`}
              >
                <button
                  type="button"
                  className={`shift-toggle-btn ${shift.active ? "on" : "off"}`}
                  disabled={disabled}
                  onClick={() => onToggleShift(day.day_index, st)}
                >
                  {label}
                </button>

                {shift.active && (
                  <div className="shift-hours">
                    <label className="hour-label">
                      {messages.LABEL_FROM}
                      <select
                        className="hour-input"
                        value={shift.from_hour}
                        disabled={isDisabled}
                        onChange={(e) =>
                          onSetShiftHours(
                            day.day_index,
                            st,
                            e.target.value,
                            shift.to_hour,
                          )
                        }
                      >
                        {timeOptions(shift.from_hour, shiftTimeOptions("from", st))}
                      </select>
                    </label>
                    <label className="hour-label">
                      {messages.LABEL_TO}
                      <select
                        className="hour-input"
                        value={shift.to_hour}
                        disabled={isDisabled}
                        onChange={(e) =>
                          onSetShiftHours(
                            day.day_index,
                            st,
                            shift.from_hour,
                            e.target.value,
                          )
                        }
                      >
                        {timeOptions(shift.to_hour, shiftTimeOptions("to", st))}
                      </select>
                    </label>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}