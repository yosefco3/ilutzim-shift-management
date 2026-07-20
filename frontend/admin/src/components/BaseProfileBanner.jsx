import messages from '../utils/messages';

/**
 * BaseProfileBanner — a persistent, NON-blocking warning shown wherever the base
 * profile (שגרה, `is_base`) is the one being edited. It never blocks any action;
 * it only nudges the admin toward the safe workflow: duplicate שגרה, make the
 * copy the default, and edit the copy instead of the base template.
 *
 * By design there is NO action button and NO navigation here (per the product
 * decision) — the same informational banner drops into every editing surface
 * (Positions, board, Profiles) so the message reads identically everywhere.
 *
 * Callers decide WHEN to render it (they own the `is_base` check): the Positions
 * screen shows it when the selected profile is base, the board when the week's
 * effective profile is base, and the Profiles screen when the base profile is
 * also the current default.
 */
export default function BaseProfileBanner() {
  return (
    <div className="base-profile-banner" role="note">
      <span className="base-profile-banner-icon" aria-hidden="true">⚠️</span>
      <span className="base-profile-banner-text">
        {messages.profiles.baseProfileWarning}
      </span>
    </div>
  );
}
