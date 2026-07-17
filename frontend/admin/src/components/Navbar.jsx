import { NavLink, useNavigate } from 'react-router-dom';
import { adminLogout, isLoggedIn } from '../api/adminApiClient';
import messages from '../utils/messages';

// Part B (constraints import + schedule builder) is hidden in production via a
// build-time flag, matching the gated routes in App.jsx.
const BUILDER_ENABLED = import.meta.env.VITE_SCHEDULE_BUILDER_ENABLED !== 'false';
// Stage 3 (attendance) — same build-time flag convention.
const ATTENDANCE_ENABLED = import.meta.env.VITE_ATTENDANCE_ENABLED !== 'false';
// "סידור בפועל" (actual schedule) — same build-time flag convention.
const ACTUAL_SCHEDULE_ENABLED = import.meta.env.VITE_ACTUAL_SCHEDULE_ENABLED !== 'false';
// סד"פ (procedure quiz) — DELIBERATE divergence: unlike the flags above (which
// use `!== 'false'`, i.e. default ON), this feature ships DARK and defaults OFF.
// It is flipped ON only in the final deploy step (deploy-safe sequencing — the
// backend lands in prod first with this unset, so no nav entry appears until the
// full feature is ready). Matches the inverted check in App.jsx.
const PROCEDURES_ENABLED = import.meta.env.VITE_PROCEDURES_ENABLED === 'true';

export default function Navbar() {
  const navigate = useNavigate();
  const authenticated = isLoggedIn();

  const handleLogout = () => {
    adminLogout();
    navigate('/login');
  };

  if (!authenticated) {
    return (
      <nav className="navbar">
        <div className="navbar-brand">{messages.app.title}</div>
        <div className="navbar-links">
          <NavLink to="/login">{messages.nav.login}</NavLink>
        </div>
      </nav>
    );
  }

  return (
    <nav className="navbar">
      <div className="navbar-brand">{messages.app.title}</div>
      <div className="navbar-links">
        <NavLink to="/guards">{messages.nav.guards}</NavLink>
        <NavLink to="/weeks">{messages.nav.weeks}</NavLink>
        {/* דיווחים / יצוא אילוצים / תצוגה מקדימה — הוסרו מהתפריט; מגיעים אליהם
            דרך הקישורים פר-שבוע בדף השבועות (WeekQuickLinks). הראוטים קיימים.
            ייבוא אילוצים — מוסתר זמנית (לא נדרש כרגע). הראוט /import עדיין קיים. */}
        {BUILDER_ENABLED && (
          <>
            <span className="navbar-group-sep" aria-hidden="true">|</span>
            <span className="navbar-group-label">{messages.nav.builderGroup}</span>
            <NavLink to="/builder/profiles">{messages.nav.profiles}</NavLink>
            <NavLink to="/builder/positions">{messages.nav.positions}</NavLink>
            <NavLink to="/builder/board">{messages.nav.board}</NavLink>
          </>
        )}
        {/* The actual board sits between the builder and attendance — the
            logical flow: plan → record reality → compare punches against it. */}
        {ACTUAL_SCHEDULE_ENABLED && (
          <>
            <span className="navbar-group-sep" aria-hidden="true">|</span>
            <NavLink to="/actual">{messages.nav.actual}</NavLink>
          </>
        )}
        {/* Attendance sits AFTER the builder group — the logical flow is:
            build the schedule, then track attendance against it (Yosef 4/7). */}
        {ATTENDANCE_ENABLED && (
          <>
            <span className="navbar-group-sep" aria-hidden="true">|</span>
            <NavLink to="/attendance">{messages.nav.attendance}</NavLink>
          </>
        )}
        {/* סד"פ — נהלים (feature-flagged, default OFF — see PROCEDURES_ENABLED). */}
        {PROCEDURES_ENABLED && (
          <>
            <span className="navbar-group-sep" aria-hidden="true">|</span>
            <NavLink to="/procedures">{messages.procedures.nav}</NavLink>
          </>
        )}
        {/* הגדרות — אחרון לפני "התנתק" (יוסף 4/7): עמוד תחזוקה, לא עבודה יומית. */}
        <NavLink to="/settings">{messages.nav.settings}</NavLink>
        <button className="btn btn-secondary btn-sm" onClick={handleLogout}>
          {messages.nav.logout}
        </button>
      </div>
    </nav>
  );
}
