import messages from '../../utils/messages';
import { DAY_NAMES_SHORT as DAY_NAMES } from '../../utils/guardMessages.js';

// The 7 day indices in canonical Sunday→Saturday order. The app is dir=rtl, so a
// plain <table> renders the first column (position name) on the right and ראשון
// naturally to its left — no direction fighting, no column reversing.
const DAY_INDICES = [0, 1, 2, 3, 4, 5, 6];

/**
 * Read-only positions × days matrix (step 03). Rows = the profile's positions in
 * display_order; columns = the 7 week days. An active cell shows its time window,
 * an inactive one shows ✕. Day headers carry the profile's per-day label chip
 * when present ([EDGE I2] — labels render ONLY here until step 07). Editing,
 * save, hours popover and multi-select land in steps 04–06.
 *
 * Props:
 *   positions — listPositions() result (already in display_order from the API).
 *   profile   — the selected ActivationProfile (carries day_labels). Optional.
 */
export default function ProfileMatrix({ positions, profile }) {
  const m = messages.positions;
  const labels = profile?.day_labels || {};

  return (
    <div className="profile-matrix-scroll">
      <table className="profile-matrix">
        <thead>
          <tr>
            <th scope="col" className="profile-matrix-col-name">
              {m.matrixPositionCol}
            </th>
            {DAY_INDICES.map((d) => (
              <th key={d} scope="col" className="profile-matrix-col-day">
                <span className="profile-matrix-day-name">{DAY_NAMES[d]}</span>
                {labels[String(d)] ? (
                  <span className="profile-matrix-day-label">{labels[String(d)]}</span>
                ) : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.id}>
              <th scope="row" className="profile-matrix-row-name">
                <span className="profile-matrix-name-text">{p.name}</span>
                {p.is_event && (
                  <span className="position-event-badge">
                    {p.event_required_count != null
                      ? `${m.eventBadge} · ${p.event_required_count}`
                      : m.eventBadge}
                  </span>
                )}
              </th>
              {DAY_INDICES.map((d) => {
                const win = p.day_schedules?.[String(d)];
                const active = !!win && !!win.start && !!win.end;
                return (
                  <td
                    key={d}
                    className={`profile-matrix-cell${active ? '' : ' is-off'}`}
                    title={active ? undefined : m.matrixOff}
                  >
                    {active ? m.matrixHours(win.start, win.end) : '✕'}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
