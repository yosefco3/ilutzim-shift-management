"""
Centralized Hebrew messages for the entire application.
ALL Hebrew text must live here — no Hebrew strings outside this file.
"""


class Messages:
    """Container for all Hebrew text constants used in the system."""

    # ── Bot messages ──────────────────────────────────────────────────
    BOT_WELCOME: str = "שלום! 👋\nברוכים הבאים למערכת ניהול המשמרות.\nאנא שתפו את מספר הטלפון שלכם לצורך אימות."
    BOT_SHARE_CONTACT_BUTTON: str = "📱 שתף מספר טלפון"
    BOT_AUTH_SUCCESS: str = "✅ אימות הצליח! ברוכים הבאים למערכת."
    BOT_AUTH_FAIL: str = "❌ מספר הטלפון לא נמצא במערכת. אנא פנה למנהל."
    BOT_WEEK_OPEN: str = "📢 חלון הגשת האילוצים נפתח!\nאנא הגישו את האילוצים שלכם לשבוע הקרוב."
    BOT_REMINDER: str = "⏰ תזכורת: טרם הגשת את האילוצים שלך לשבוע הקרוב.\nהחלון ייסגר בקרוב!"
    BOT_SUBMISSION_SUMMARY: str = "📋 סיכום הגשה:\nשם: {name}\nאילוצים: {constraints}\nסטטוס: {status}"
    BOT_DEVIATION_WARNING: str = "⚠️ התראת חריגה:\n{name} — {deviation}\nימים חריגים: {days}"
    BOT_LOCKOUT: str = "🔒 השבוע נעול — לא ניתן להגיש אילוצים."
    BOT_SUBMIT_ANYWAY: str = "🔓 באפשרותך להגיש בכל זאת (עקיפת מנעול):"
    BOT_OPEN_WEBAPP_BUTTON: str = "🖥️ פתח את אפליקציית האילוצים"

    # ── Error messages ────────────────────────────────────────────────
    ERR_WEEK_LOCKED: str = "השבוע נעול, לא ניתן להגיש"
    ERR_USER_NOT_FOUND: str = "משתמש לא נמצא"
    ERR_USER_DEACTIVATED: str = "חשבון המשתמש מושבת"
    ERR_AUTH_FAILED: str = "אימות נכשל"
    ERR_CONFLICT: str = "התנגשות שינויים — נסה שוב"
    ERR_VALIDATION: str = "שגיאת אימות נתונים"
    SUBMISSION_CLOSED: str = "ההגשה סגורה כרגע. אין שבוע פתוח להגשה."
    SUBMISSION_WRONG_WEEK: str = "ניתן להגיש רק לשבוע הפתוח הנוכחי."

    # ── UI Labels ─────────────────────────────────────────────────────
    LABEL_AVAILABLE: str = "זמין"
    LABEL_UNAVAILABLE: str = "לא זמין"
    LABEL_BLOCKED: str = "חסום"
    LABEL_MORNING: str = "בוקר"
    LABEL_AFTERNOON: str = "צהריים"
    LABEL_NIGHT: str = "לילה"

    # ── Excel export labels ───────────────────────────────────────────
    EXCEL_HEADER_NAME: str = "שם"
    EXCEL_HEADER_PHONE: str = "טלפון"
    EXCEL_HEADER_NOTES: str = "הערות"
    EXCEL_HEADER_THRESHOLDS: str = "סף מינימום"
    EXCEL_HEADER_DEVIATION: str = "חריגה"
    EXCEL_REPORT_TITLE: str = "דוח משמרות — {start} עד {end}"

    # ── Submission status labels ──────────────────────────────────────
    STATUS_SUBMITTED: str = "הוגש"
    STATUS_SUBMITTED_VARIANCE: str = "הוגש עם חריגה"
    STATUS_PENDING: str = "ממתין להגשה"
    STATUS_AUTO_ABSENCE: str = "העדרות אוטומטית"

    # ── Validation messages ─────────────────────────────────────────────
    VAL_INVALID_PHONE: str = "מספר טלפון לא תקין — חייב להתחיל ב-05 עם 10 ספרות או +972 עם 9 ספרות"
    VAL_INVALID_PREFERRED_SHIFT: str = "משמרת מועדפת לא תקינה — בוקר, ערב או לילה בלבד"
    VAL_DATE_RANGE: str = "תאריך סיום חייב להיות אחרי תאריך התחלה"
    VAL_DATE_RANGE_SAME_OK: str = "תאריך סיום חייב להיות מאוחר או שווה לתאריך התחלה"
    VAL_SAME_START_END: str = "שעת התחלה וסיום לא יכולות להיות זהות"
    VAL_BAD_TIME: str = "שעה לא חוקית"
    VAL_UNAVAILABLE_WITH_SHIFTS: str = "יום לא זמין לא יכול להכיל משמרות"
    VAL_AVAILABLE_NO_SHIFTS: str = "יום זמין חייב להכיל לפחות משמרת אחת"
    VAL_EMPTY_DAYS: str = "חובה להגיש לפחות יום אחד"
    # The security day runs 07:00 → 07:00; submitted shifts must stay inside it.
    VAL_SHIFT_BEFORE_ANCHOR: str = "לא ניתן להתחיל משמרת לפני 07:00"
    VAL_NIGHT_PAST_ANCHOR: str = "משמרת לילה חייבת להסתיים עד 07:00 בבוקר למחרת"
    # Single-open + no-reopen: OPEN is allowed only for the upcoming, never-opened
    # week, and only when no other week is already OPEN.
    VAL_WEEK_ALREADY_RAN: str = "לא ניתן לפתוח מחדש שבוע שחלון-ההגשה שלו כבר רץ"
    VAL_WEEK_NOT_UPCOMING: str = "ניתן לפתוח רק את השבוע הקרוב שטרם התחיל"
    VAL_ANOTHER_WEEK_OPEN: str = "כבר קיים שבוע פתוח — לא ניתן לפתוח שבוע נוסף"
