/**
 * Centralized Hebrew UI texts for the guard-facing area.
 * Zero hard-coded Hebrew text elsewhere — everything comes from here.
 */
export const messages = {
  DAY_SUNDAY: "יום ראשון",
  DAY_MONDAY: "יום שני",
  DAY_TUESDAY: "יום שלישי",
  DAY_WEDNESDAY: "יום רביעי",
  DAY_THURSDAY: "יום חמישי",
  DAY_FRIDAY: "יום שישי",
  DAY_SATURDAY: "שבת",

  LABEL_AVAILABLE: "זמין",
  LABEL_UNAVAILABLE: "לא זמין",
  LABEL_MORNING: "בוקר",
  LABEL_AFTERNOON: "ערב",
  LABEL_NIGHT: "לילה",
  LABEL_FROM: "משעה",
  LABEL_TO: "עד שעה",
  LABEL_NOTES: "הערות כלליות",
  LABEL_NOTES_PLACEHOLDER: "הערות נוספות (אופציונלי)...",
  LABEL_BLOCKED: "חסום",
  LABEL_SUBMIT: "שלח אילוצים",
  LABEL_SUBMITTING: "שולח...",
  LABEL_LOADING: "טוען...",

  LOCK_BANNER: "השבוע נעול — לא ניתן לעדכן אילוצים",
  LOCK_STATUS_CLOSED: "ההגשה סגורה כרגע",
  LOCK_STATUS_LOCKED: "השבוע נעול — ההגשה נסגרה ולא ניתן עוד לעדכן אילוצים",
  LOCK_NO_WEEK: "אין שבוע פעיל",

  ERR_AUTH: "שגיאת אימות — נסה שוב דרך הבוט",
  ERR_LOCKED: "השבוע נעול להגשות",
  ERR_GENERIC: "אירעה שגיאה — נסה שוב",
  ERR_NETWORK: "בעיית תקשורת — בדוק את החיבור לאינטרנט",
  // Shown when the POST returned 2xx but no persisted submission came back —
  // i.e. the server did not actually confirm the save. Never treat as success.
  ERR_NO_CONFIRM: "השרת לא אישר את ההגשה — נסה שוב",
  SUCCESS_SUBMITTED: "האילוצים נשלחו בהצלחה!",

  // Hard time-range errors — block submit (the security day runs 07:00 → 07:00).
  ERR_SHIFT_BEFORE_ANCHOR: "לא ניתן להתחיל משמרת לפני 07:00",
  ERR_NIGHT_PAST_ANCHOR: "משמרת לילה חייבת להסתיים עד 07:00 בבוקר למחרת",
  ERR_END_BEFORE_START: "שעת הסיום חייבת להיות אחרי שעת ההתחלה",

  // Soft, non-blocking constraint-rule warnings (submission is still allowed).
  WARN_TITLE: "שים לב — ייתכן שחרגת מהכללים (ניתן לשלוח בכל זאת):",
  WARN_MIN_SHIFTS: (got, min) => `סימנת ${got} משמרות בלבד; המומלץ לפחות ${min}.`,
  WARN_MIN_NIGHTS: (got, min) => `סימנת ${got} לילות; המומלץ לפחות ${min}.`,
  WARN_MIN_EVENINGS: (got, min) => `סימנת ${got} ערבים; המומלץ לפחות ${min}.`,
  WARN_MAX_CONSEC: (got, max) => `סימנת ${got} ימים רצופים; המקסימום הוא ${max}.`,

  // ── Procedure reading page (סד"פ WebApp) ───────────────────────────────
  PROC_PASSED_BADGE: "✅ עברת את המבחן",
  PROC_QUIZ_BTN: "▶️ התחל מבחן",
  PROC_QUIZ_SENDING: "שולח...",
  PROC_QUIZ_SENT: "המבחן נשלח לצ'אט",
  // Status-specific screens (friendly Hebrew, never a raw error).
  PROC_ERR_AUTH: "יש לפתוח את הנוהל מתוך הבוט בטלגרם", // 401 / missing initData
  PROC_ERR_UNAVAILABLE: "הנוהל אינו זמין יותר", // 404 / not published
  PROC_ERR_BOT_DOWN: "הבוט אינו זמין כרגע — נסו שוב בעוד רגע", // 503 on quiz start
};

/** Day names in order Sunday–Saturday */
export const DAY_NAMES = [
  messages.DAY_SUNDAY,
  messages.DAY_MONDAY,
  messages.DAY_TUESDAY,
  messages.DAY_WEDNESDAY,
  messages.DAY_THURSDAY,
  messages.DAY_FRIDAY,
  messages.DAY_SATURDAY,
];

/** Short day names (ראשון–שבת) for compact admin tables/headers. */
export const DAY_NAMES_SHORT = [
  "ראשון",
  "שני",
  "שלישי",
  "רביעי",
  "חמישי",
  "שישי",
  "שבת",
];

/** Shift type keys, in canonical daily order */
export const SHIFT_TYPES = ["morning", "afternoon", "night"];

/** Map shift_type key to Hebrew label */
export const SHIFT_LABELS = {
  morning: messages.LABEL_MORNING,
  afternoon: messages.LABEL_AFTERNOON,
  night: messages.LABEL_NIGHT,
};

/**
 * Default shift hours — used as fallback when the API is unreachable.
 * Editable by admin via /admin/settings page (stored in DB).
 * Format: { shift_type: { from_hour, to_hour } }
 */
export const SHIFT_DEFAULTS = {
  morning: { from_hour: "07:00", to_hour: "16:30" },
  afternoon: { from_hour: "15:00", to_hour: "23:00" },
  night: { from_hour: "23:00", to_hour: "07:00" },
};

/**
 * All half-hour time slots from "00:00" to "23:30" (48 values).
 * Used to populate the time dropdowns so guards/admins pick a value
 * instead of typing — no ":" to type, and only half-hour multiples are selectable.
 */
export const HALF_HOUR_OPTIONS = Array.from({ length: 48 }, (_, i) => {
  const h = String(Math.floor(i / 2)).padStart(2, "0");
  const m = i % 2 === 0 ? "00" : "30";
  return `${h}:${m}`;
});

/**
 * Half-hour slots ordered along the *security day*, which runs 07:00 → 07:00 the
 * next morning: 07:00, 07:30, … 23:30, 00:00, … 06:30. Used by the positions
 * editor so the dropdowns read in the order an admin thinks about a shift.
 * Index of "07:00" in HALF_HOUR_OPTIONS is 14 (7 * 2).
 */
export const DAY_HALF_HOUR_OPTIONS = [
  ...HALF_HOUR_OPTIONS.slice(14),
  ...HALF_HOUR_OPTIONS.slice(0, 14),
];

// ── Security-day constrained time options (constraint forms) ──────────────────
// No shift may start before 07:00; a night shift may end no later than 07:00 the
// next morning. These drive the from/to dropdowns so guards/admins can't even
// pick an out-of-range value (backend enforces the same rules as a backstop).

/** Start (from) options for every shift type: 07:00 … 23:30. */
export const START_OPTIONS = HALF_HOUR_OPTIONS.slice(14);

/** End (to) options for morning/evening — same evening, no wrap: 07:30 … 23:30. */
export const END_OPTIONS_DAY = HALF_HOUR_OPTIONS.slice(15);

/**
 * End (to) options for night — may wrap into the next morning but not past
 * 07:00: 07:30 … 23:30, then 00:00 … 07:00.
 */
export const END_OPTIONS_NIGHT = [
  ...HALF_HOUR_OPTIONS.slice(15),
  ...HALF_HOUR_OPTIONS.slice(0, 15),
];

/** The option list for a given dropdown field ("from"/"to") and shift type. */
export function shiftTimeOptions(field, shiftType) {
  if (field === "from") return START_OPTIONS;
  return shiftType === "night" ? END_OPTIONS_NIGHT : END_OPTIONS_DAY;
}

const ANCHOR_MIN = 7 * 60; // 07:00

function minutesFromAnchor(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  return (h * 60 + m - ANCHOR_MIN + 1440) % 1440;
}

/**
 * Validate one shift window against the security-day rules. Returns a Hebrew
 * error message, or null when the window is valid. Mirrors the backend's
 * ``_validate_form_window``.
 */
export function checkShiftWindow(shiftType, fromHour, toHour) {
  const [fh, fm] = fromHour.split(":").map(Number);
  if (fh * 60 + fm < ANCHOR_MIN) return messages.ERR_SHIFT_BEFORE_ANCHOR;
  if (shiftType === "night") {
    const start = minutesFromAnchor(fromHour);
    const end = minutesFromAnchor(toHour) || 1440; // 07:00 → end of the day
    if (end <= start) return messages.ERR_NIGHT_PAST_ANCHOR;
  } else if (fromHour >= toHour) {
    return messages.ERR_END_BEFORE_START;
  }
  return null;
}

/**
 * Validate every active shift across the form's days. Returns the first error
 * message found, or null when all windows are valid. Blocks submit.
 */
export function validateShiftHours(days) {
  for (const d of days) {
    if (d.blocked) continue;
    for (const st of SHIFT_TYPES) {
      const sh = d.shifts?.[st];
      if (!sh?.active || !sh.from_hour || !sh.to_hour) continue;
      const err = checkShiftWindow(st, sh.from_hour, sh.to_hour);
      if (err) return err;
    }
  }
  return null;
}
