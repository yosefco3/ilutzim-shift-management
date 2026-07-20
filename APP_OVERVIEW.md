# APP_OVERVIEW — Ilutzim · אילוצים

> עדכון אחרון: 2026-07-17
> מסמך חי. עדכן אחרי כל שינוי שנוגע בפיצ'רים/מודלים/endpoints/workflow/ארכיטקטורה.
> **הערה:** המסמך שוחזר ב-2026-07-09 (המקור אבד בייצוא הריפו) ומאז **נכנס לגיט**
> (`!/APP_OVERVIEW.md` ב-.gitignore). הריפו ציבורי — לא לכתוב כאן דומיינים/סודות.

## מה זה
פלטפורמת שיבוץ ונוכחות מקצה-לקצה לצוותי אבטחה: מאבטח מגיש זמינות שבועית בטלגרם
(WebApp) → אדמין בונה סידור על לוח גרירה עם מנוע אזהרות חי → פרסום אישי בטלגרם
(הודעה + PNG) → "סידור בפועל" עריך לשבוע הרץ → שעון נוכחות בטלגרם מוצלב מול
הסידור בפועל → דוחות שכר Excel. צינור אחד, מקור אמת אחד.

## סטאק
- **Backend:** Python 3.12 · FastAPI (async) · SQLAlchemy 2 + Alembic · PostgreSQL · aiogram 3 (polling) · APScheduler
- **Frontend:** React 19 · Vite (פורט 3001, proxy `/api` → `:8000`) · React Router · vitest + Testing Library
- הרצה: `.claude/launch.json` — שרתי `backend` (uvicorn :8000) ו-`admin-frontend` (:3001); או `dev.sh`
- טסטים: `cd backend && .venv/bin/python -m pytest -q` · `npm --prefix frontend/admin test` (לא `npx vitest` מהשורש!)
- גרפים: `python scripts/test_graph.py` → `TEST_GRAPH.md` · `code-review-graph update`

## ארכיטקטורה
```
Telegram Bot (aiogram, polling)     React 19 admin+guards (frontend/admin)
            └──────────────┬──────────────┘
                     FastAPI (backend/app)
        ┌──────────────────┼───────────────────┐
   Part A (core)   Part B (schedule_builder)   attendance (Stage 3)
        └──────────────────┴───────────────────┘
                       PostgreSQL
```
- **Part A — `backend/app/`**: users/admins, שבועות, הגשות, auth, ייצוא, הגדרות, בוט, scheduler. פעיל תמיד.
- **Part B — `backend/app/schedule_builder/`**: פרופילים → עמדות → לוח → שיבוצים → סידור שמור/בפועל.
  נרשם רק כש-`SCHEDULE_BUILDER_ENABLED=true`. **כלל תלות: B→A מותר, A לא מכיר את B.**
- **Stage 3 — `backend/app/attendance/`**: החתמות → זיווג משמרות → השוואה → דוחות שכר → התראות אדמין.
  נרשם רק כש-`ATTENDANCE_ENABLED=true`.
- **בוט — `backend/app/bot/`**: משימת רקע (start_polling) — הגשות, אימות, שעון נוכחות, ברודקאסטים.
- **Frontend — `frontend/admin/`**: אפליקציה אחת, 17 עמודים; `/submit`+`/submit/success` הם צד-המאבטח (בלי navbar, אימות Telegram initData).
- **מנוע אזהרות רכות** (9 סוגים) חי פעמיים: קנוני ב-`app/schedule_builder/services/warnings_service.py`,
  עותק JS ל-feedback חי ב-`frontend/admin/src/utils/warnings.js` — נעולים בטסט golden-fixture משותף (`warningsParity`).
- **ציר היום-הביטחוני 07:00→07:00**: כל חשבון זמן עובר דרך `intervals.py` / `intervals.js` (mirror).

## מודלים
**Part A:** `User` (מאבטח; roles JSON: ARMED/UNARMED/AHMASH/PATROL_VEHICLE; `is_reinforcement` = מתגבר חיצוני, מסונן מכל צרכני by-guard) · `Admin` (טבלה נפרדת, email+password) · `ScheduleWeek` (status: CLOSED/OPEN/LOCKED; opened_at/published_at) · `WeeklySubmission` (unique user+week) → `DailyStatus` → `ShiftWindow` · `SystemSetting` (key-value; ברירות מחדל ב-`SETTINGS_DEFAULTS`).

**Part B:** `ActivationProfile` (day_labels JSON) → `Position` (day_schedules JSON, required_attributes, is_event + event_required_count) · `RequirementAttribute` (אוצר מילים) · `WeekProfileAssignment` (שבוע↔פרופיל) · `ScheduleAssignment` (week×position×day×user + segment) · `SavedSchedule` (snapshot JSON לשבוע) · `ActualSchedule` → `ActualPosition`/`ActualAssignment`/`ActualReinforcement` (עותק 1:1 עריך, נזרע ברולאובר).

**Stage 3:** `AttendanceEvent` (החתמה IN/OUT + GPS) · `AttendanceShift` (זיווג מול הסידור; violations) · `AttendanceAdjustment` (תיקון ידני, audit) · `AttendanceAlertSent` (מניעת כפל התראות).

**Procedures (סד"פ) — `backend/app/procedures/`:** `Procedure` (title/body; DRAFT/PUBLISHED/ARCHIVED; `body_text` טקסט שטוח עם סמני `*bold*` + `body_html` — snapshot HTML מחוטא מה-docx, mammoth→nh3, מאוכלס בהעלאה ונקרא בעמוד ה-WebApp; עריכת טקסט באדמין לא נוגעת ב-`body_html`) · `QuizQuestion` (בנק MCQ; source AI/MANUAL + edited_at — ריג'נרציה מוחקת רק AI לא-ערוכות) · `QuizAttempt` (מדגם שאלות + תשובות snapshot; unique חלקי על IN_PROGRESS) · `QuizPollLink` (poll_id טלגרם → attempt/question + סדר תשובות מעורבב) · `ProcedureReminderSent` (תזכורת אחת per מאבטח+נוהל) · `ProcedureReadReceipt` (חותמת פתיחה ראשונה של עמוד הקריאה; unique procedure+user, INSERT…ON CONFLICT DO NOTHING). ג'נרציית שאלות: Claude API (מודל בהגדרה `procedure_ai_model`, ברירת מחדל claude-opus-4-8; ANTHROPIC_API_KEY אופציונלי — בלעדיו generate מחזיר 503 והאפליקציה עולה רגיל). מבחן: quiz polls בבוט, מעבר ≥`procedure_pass_threshold` (80), מדגם `procedure_quiz_size` (7). **קריאה ב-WebApp** (לא בבוט): הבוט שולח כרטיס קצר (כותרת + כפתור `📖 קרא נוהל` מסוג web_app + `▶️ התחל מבחן`); העמוד `/procedure/:id` מרנדר `body_html` (או fallback ל-`body_text`), רושם read receipt, ויכול להתחיל מבחן (השאלון עצמו נשאר 100% ב-quiz polls של טלגרם). עוגנים: `bot/quiz_sender.py` (שולחי ה-poll המשותפים לבוט ול-WebApp), `bot/webapp.py:procedure_webapp_url` (cache-busting `v=`).

## Endpoints (קבוצות עיקריות)
- `/auth` — התחברות אדמין + `/auth/admin/admins*` ניהול אדמינים (SUPER_ADMIN בלבד) · `/submissions` — הגשות מאבטח (Telegram initData)
- `/admin/users` · `/admin/weeks` (open/close/publish/lock) · `/admin/notifications` · `/admin/export` · `/admin/settings` · `/admin/import/constraints`
- `/admin/builder/*` (Part B) — profiles / positions / attributes / board / **pool** / assignments / warnings / saved-schedules
- `/admin/actual/*` — הסידור בפועל (עמדות, שיבוצים, מתגברים, ייצוא Excel/PNG, save-as-profile)
- `/admin/attendance/*` — events / shifts / adjustments / comparison / דוחות שכר
- `/admin/procedures/*` — נהלים (סד"פ): CRUD + upload docx (+ body_html snapshot) + generate + questions + publish + results (תחת `PROCEDURES_ENABLED`)
- `/procedures/*` (guard, Telegram initData) — עמוד קריאת הנוהל: `GET /procedures/{id}` (PUBLISHED בלבד + read receipt) ו-`POST /procedures/{id}/quiz/start` (שולח את ה-poll הראשון לצ'אט)
- `GET /health` — Railway healthcheck

## Workflow / Lifecycle
**מחזור שבוע (3 מצבים, החלטת 2026-07-04):**
- `CLOSED` — מצב עבודה: בונים לוח, עורכים, **פרסום לא משנה סטטוס** (רק חותם published_at ומשדר).
- `OPEN` — חלון הגשות (לכל היותר שבוע OPEN אחד — unique partial index). פתיחה ידנית/אוטומטית + ברודקאסט.
- `LOCKED` — סופי ובלתי-הפיך. מגיעים אליו **רק ברולאובר יום א' 00:00** (או catch-up באתחול). אין reopening.
- ברולאובר גם נזרע ה-ActualSchedule (עותק הביצוע) לשבוע שנכנס.

**POOL של לוח הסידור:** מוגש מ-`AvailabilityService.build_pool` — מי שהגיש (עם זמינות/שעות),
ומאז 2026-07-09 גם מי שלא הגיש (בסוף, `submitted: false`, נשלט ע"י ההגדרה `pool_show_unsubmitted`,
ברירת מחדל ON; endpoint האזהרות תמיד כולל אותם). הסידור בפועל מציג תמיד את כל הפעילים.

**ג'ובים (APScheduler, Asia/Jerusalem):** רולאובר שבועי · auto-open/auto-lock (קונפיג ב-SystemSettings,
resync בלי restart) · sweep נוכחות יומי 04:30 · התראות נוכחות כל 10 דק'.

## דגלי פיצ'ר
| דגל | ברירת מחדל | בפרודקשן |
|---|---|---|
| `SCHEDULE_BUILDER_ENABLED` + `VITE_SCHEDULE_BUILDER_ENABLED` | on | on (שניהם נדרשים — ה-VITE מגלה בnavbar) |
| `ATTENDANCE_ENABLED` + `VITE_ATTENDANCE_ENABLED` | off | **on** (מאומת 2026-07-05) |
| `ACTUAL_SCHEDULE_ENABLED` + `VITE_ACTUAL_SCHEDULE_ENABLED` | off | **on** (מאומת 2026-07-05) |
| `pool_show_unsubmitted` (SystemSetting, לא env) | on | on |
| `PROCEDURES_ENABLED` + `VITE_PROCEDURES_ENABLED` | **off** | **on** (אומת מול Railway ‏2026-07-18, כולל `ANTHROPIC_API_KEY`); webapp-view בפרוד מאז מיזוג 2026-07-18 (deployment `00986a78`) |

## דיפלוי
- **Railway**, live מאז 2026-06-20 (דומיין הפרוד לא מתועד בריפו הציבורי — נמצא ב-Railway/cloudflared). ענף הדיפלוי: **`production`** (push = deploy).
- **כלל ברזל:** אחרי כל step ירוק — commit ואז push ל-`development` **וגם** `development:production`.
- docker-entrypoint מריץ `alembic upgrade head` + seed אדמין בכל דיפלוי — אין צעד מיגרציה ידני בפרוד.
- לוגים בפרוד ברמת WARNING — `logger.info` לא נראה; אל תסיק מצב פיצ'ר מהיעדר לוג.
- runbooks: `PROPAGATE_DEMO_PROD.md` (רענון דמו), `HANDOVER_OWNERSHIP.md` (העברת בעלות), `README.md` (showcase).

## טסטים
- Backend: ~1010 טסטים / 107 קבצים (`backend/tests/`, SQLite in-memory + fixtures ב-conftest).
- Frontend: ~480 טסטים / 56 קבצים (`frontend/admin/tests/`, vitest+RTL).
- CI: GitHub Actions (pytest + vitest) על כל push. `scripts/test_history.json` הוא הארטיפקט היחיד שנכנס לגיט.

## היסטוריית שינויים משמעותיים
> עד 2026-07-06 ההיסטוריה שוחזרה מזיכרונות + `features-prompts/` (הייצוא מחק את הגיט-לוג).

| תאריך | שינוי | קבצים עיקריים |
|---|---|---|
| ~2026-06 | Part B — בונה הסידור: פרופילים, עמדות, לוח, POOL, שיבוצים, אזהרות, פרסום PNG | `backend/app/schedule_builder/`, `frontend/admin/src/pages/builder/` |
| 2026-06-20 | דיפלוי ראשון ל-Railway (service יחיד + feature flags) | `Dockerfile`, `railway.json`, `docker-entrypoint.sh` |
| 2026-07-03 | פישוט מוצר: אדמין יחיד, אין reopening לשבוע; הקשחת אבטחה | `features-prompts/security_hardening/` |
| 2026-07-04 | מחזור-חיים מחודש: פרסום שומר CLOSED, LOCKED רק ברולאובר | `app/services/week_service.py` |
| 2026-07-05 | "סידור בפועל" live בפרוד (14 צעדים, כולל מתגברים+דוח) + נוכחות Stage 3 live | `app/schedule_builder/…/actual_*`, `app/attendance/` |
| 2026-07-06 | ייצוא הריפו לציבורי (portfolio) · CI GitHub Actions · שחזור .gitignore | `.github/workflows/ci.yml` |
| 2026-07-07 | פרופוגציית דמו 065 לפרוד בפקודה אחת + סקריפט reset אחרי-דמו | `scripts/propagate_demo_to_prod.*`, `scripts/reset_prod_demo.*` |
| 2026-07-09 | `pool_show_unsubmitted` — מי שלא הגיש מופיע בסוף ה-POOL עם תג, סוויטש בהגדרות | `availability_service.py`, `GuardPool.jsx`, `SettingsPage.jsx` |
| 2026-07-09 | המסמך הזה שוחזר | `APP_OVERVIEW.md` |
| 2026-07-17 | procedure_quiz בקאנד (סד"פ + מבחן AI בטלגרם) — 5 מודלים, ג'נרציה ב-Claude API, quiz polls, תזכורת; dark מאחורי `PROCEDURES_ENABLED=off` | `backend/app/procedures/`, `bot/handlers/procedures.py`, מיגרציה `f4a1c3e5b7d9` |
| 2026-07-17 | procedure_quiz פרונטאנד אדמין — ProceduresPage (יצירה/העלאת docx/ג'נרציה) + ProcedureDetailPage (עורך שאלות, פרסום, תוצאות); `VITE_PROCEDURES_ENABLED` ברירת מחדל **off** (`=== 'true'`, בשונה משאר הדגלים) | `frontend/admin/src/pages/Procedure*.jsx`, `App.jsx`, `Navbar.jsx`, `adminApiClient.js` |
| 2026-07-18 | נוהל ברירת-מחדל: `Procedure.is_default` (unique חלקי, אחד בלבד); כל פרסום/שידור-מחדש קובע אותו; תזכורות רק עליו; ⭐ ראשון בבוט; כפתורי פרסום פר-שורה + תג בטבלת האדמין | מיגרציה `a6c8e0f2b4d6`, `procedure_service.py`, `reminder_service.py`, `ProceduresPage.jsx` |
| 2026-07-18 | procedure_webapp_view — קריאת נוהל עוברת ל-WebApp: `body_html` (mammoth→nh3, עמודת snapshot מחוטא בהעלאה); מיגרציה `c0a1e1f2a3b4` | `procedures/models/procedure.py`, `services/docx_service.py`, `controllers/procedure_controller.py`, `schemas/`, מיגרציה `c0a1e1f2a3b4` |
| 2026-07-18 | procedure_webapp_view — read receipts + endpoint קריאה למאבטח: `ProcedureReadReceipt` (חותמת פתיחה ראשונה, ON CONFLICT DO NOTHING), `GET /procedures/{id}` (PUBLISHED בלבד, passed flag, best-effort receipt), עמודת "קרא" בתוצאות | מיגרציה `d0b2c3d4e5f6`, `models/procedure_read_receipt.py`, `repositories/read_receipt_repository.py`, `procedure_service.py` |
| 2026-07-18 | procedure_webapp_view — התחלת מבחן מה-WebApp: חילוץ שולחי ה-poll ל-`bot/quiz_sender.py` (משותף לבוט ול-WebApp), `POST /procedures/{id}/quiz/start` (404/409/503) | `bot/quiz_sender.py`, `bot/handlers/procedures.py`, `controllers/procedure_controller.py` |
| 2026-07-18 | procedure_webapp_view — כרטיס קצר במקום צ'אנקים: כל נקודת מגע (פרסום/צפייה/תזכורת) שולחת כרטיס אחד עם כפתור web_app `📖 קרא נוהל` + `▶️ התחל מבחן`; נמחקה מכונת הצ'אנקים ב-`notifications.py` | `bot/webapp.py`, `bot/keyboards/procedures.py`, `bot/notifications.py`, `publish_service.py`, `scheduler.py` |
| 2026-07-18 | procedure_webapp_view — עמוד קריאה למאבטח `/procedure/:id` (RTL, body_html / fallback, read receipt, התחלת מבחן + סגירת WebApp, מסכי שגיאה עבריים) | `frontend/admin/src/pages/ProcedureViewPage.jsx`, `App.jsx`, `api/guardApiClient.js`, `styles/guard.css` |
| 2026-07-18 | procedure_webapp_view — אדמין: `body_html` עובר ב-upload/create/update + רמז ליד עורך הטקסט; עמודת "קרא" בטבלת התוצאות | `adminApiClient.js`, `ProceduresPage.jsx`, `ProcedureDetailPage.jsx` |
| 2026-07-18 | submit_reply_keyboard — כפתור "📝 הגשת/עריכת אילוצים" (web_app) במקלדת הקבועה בזמן שבוע OPEN; מקלדת מורכבת (הגשה+החתמה) בכל תשובת בוט וב-/start; ברודקאסט פתיחה נושא אותה (במקום כפתור inline), ברודקאסטי סגירה/נעילה מסירים את שורת ההגשה | `bot/keyboards/reply_kb.py`, `bot/handlers/attendance.py`, `bot/core.py`, `bot/notifications.py` |
| 2026-07-18 | quiz guard-rails — מבחן אחד בו-זמנית (התחלה על נוהל אחר נחסמת עם שם הנוהל החוסם) + כפתור "🚪 יציאה מהמבחן" על כל quiz poll (נטישה=ABANDONED, תשובות מאוחרות נבלעות) | `quiz_service.py`, `attempt_repository.py`, `bot/quiz_sender.py`, `bot/handlers/procedures.py`, `bot/keyboards/procedures.py` |
| 2026-07-19 | FIX submit_reply_keyboard — טלגרם לא מעביר initData ל-WebApp שנפתח מכפתור מקלדת תחתונה (prod: 401 על כל הגשה; dev: bypass אימת בתור user[0] בלי הודעת הצלחה). הכפתור הפך לכפתור טקסט ש-handler חדש עונה עליו בכפתור inline (עם initData); לחיצה על כפתור ישן כשאין שבוע פתוח מקבלת הודעה + רענון מקלדת | `bot/keyboards/reply_kb.py`, `bot/handlers/submit_button.py`, `bot/bot_router.py` |
| 2026-07-19 | חלון זמינות למבחן (שלב 1/4, quiz_availability_window) — הגדרה `procedure_quiz_window_days` (0=ללא הגבלה, ולידציה ≥0) + עמודת עוגן `procedures.quiz_window_started_at` שמתאפסת בכל נתיב פרסום כולל rebroadcast (`published_at` לא נגוע — תזכורות תלויות בו); מיגרציה `e2b3c4d5f6a7` עם backfill מ-`published_at` | `settings_service.py`, `procedures/models/procedure.py`, `procedure_service.py`, מיגרציה `e2b3c4d5f6a7` |
| 2026-07-19 | חלון זמינות למבחן (שלב 2/4) — הלפר טהור `quiz_window.py` (`is_quiz_open`/`quiz_deadline`, fallback ל-`published_at`, שניהם NULL=פתוח); שער יחיד ב-`QuizService.start_attempt` (מכסה בוט+WebApp, התחלה בלבד — ניסיון פתוח מסיים חופשי); תזכורות מדלגות על מבחן שפג (`run(now, window_days)`) | `procedures/services/quiz_window.py`, `quiz_service.py`, `reminder_service.py`, `scheduler.py` |
| 2026-07-19 | חלון זמינות למבחן (שלב 3/4) — `quiz_open` ב-`GuardProcedureOut` (העמוד יסתיר את כפתור המבחן) + `quiz_open`/`quiz_deadline_at` ב-`ProcedureOut`/`ProcedureListItem` (badge ותאריך לאדמין); חישוב ב-`quiz_window_info`/`list_all` (קריאת הגדרה אחת לרשימה) | `procedure_service.py`, `procedure_schemas.py`, `procedure_controller.py` |
| 2026-07-19 | סימון ויזואלי ל-DEV — מחלקת `dev-env` על ה-body צובעת רקע/נאבבר/קלפים בגוון כחול-נייבי עמוק. זיהוי dev = `import.meta.env.DEV` **או** hostname מקומי/`dev.*` (כי המכונה המקומית מגישה גם build דרך `vite preview`, שם DEV=false); הדומיין של פרוד (`app.safrasecure.uk`) לעולם לא נתפס. אומת בצילום מסך headless | `App.jsx`, `styles/admin.css` |
| 2026-07-19 | FIX הגדרות — `procedure_ai_model` קיבל תווית עברית ("מודל ה-AI להפקת שאלות המבחן") ושויך לקבוצת "נהלים (סד\"פ)" במקום ליפול ל"נוספות" עם מפתח גולמי | `SettingsPage.jsx`, `messages.js` |
| 2026-07-19 | חלון זמינות למבחן (שלב 4/4, הפיצ'ר הושלם) — שדה "חלון זמינות המבחן (ימים)" בקבוצת נהלים בהגדרות; עמוד הקריאה מסתיר את כפתור המבחן ומציג "המבחן כבר לא זמין" כש-`quiz_open=false` (הקריאה נשארת); רשימת האדמין עם badge "המבחן סגור" ועמוד הפרטים עם "המבחן פתוח עד…"/"פרסום מחדש יפתח"; אומת end-to-end מול שרת dev חי (409 בסגור, נפתח באיפוס עוגן) | `SettingsPage.jsx`, `ProcedureViewPage.jsx`, `ProceduresPage.jsx`, `ProcedureDetailPage.jsx`, `messages.js`, `guardMessages.js` |
| 2026-07-20 | profile-matrix-editor (שלב 1, day_labels) — מפת תוויות חופשיות פר-יום על `ActivationProfile` (JSONB, מפתחות "0".."6" 0=ראשון…6=שבת, ברירת מחדל `{}`); נחשף ב-`ProfileResponse` + `ProfileUpdate` כש-`None`=ללא שינוי ו-`{}`=ניקוי; ולידציה בסכמה בלבד: מפתח 0..6 אחרת 422, ערך עד 50 תווים אחרת 422, רווחים-בלבד נשמטים (מפתח נמחק, לא שגיאה); מועתק ב-duplicate; מיגרציה אדיטיבית `f8d0a2b4c6e8` עם `server_default='{}'`; **dark** — אין עדיין UI (מוצג רק בשלב 07, אחרי שכל העורך עובד) | `schedule_builder/models/activation_profile.py`, `schemas/profile_schemas.py`, `services/profile_service.py`, `controllers/profile_controller.py`, מיגרציה `f8d0a2b4c6e8` |
| 2026-07-20 | profile-matrix-editor (שלב 2, bulk day-schedules) — endpoint אטומי `PUT /admin/builder/profiles/{profile_id}/positions/day-schedules` שומר `day_schedules` של כל העמדות בבקשה אחת (במקום N PATCHes); סכמות `PositionDayScheduleItem` (position_id + day_schedules; `{}` תקין = שבוע סגור [EDGE D3]) ו-`PositionsBulkDaySchedules` (items min_length=1, רשימה ריקה=422); הדגל `require_non_empty` ב-`_validate_day_schedules` (ברירת מחדל True — התנהגות קיימת זהה, שעות HH:MM ומפתחות 0..6 משותפים) מאפשר `{}`; ה-service `bulk_update_day_schedules` מאמת הכל לפני כל כתיבה — פרופיל קיים, כל מזהה שייך לפרופיל ואין כפילויות, אחרת `PositionBulkMismatchException` (409, המזהים הבעייתיים בהודעה [EDGE C2], שום דבר לא נכתב [EDGE N1]); עמדות שלא הוזכרו לא נוגעות [EDGE C1]; חלון לילה end≤start תקין [EDGE D2]; מחזיר את רשימת העמדות המלאה הממוינת; **dark** — אין עדיין UI | `exceptions.py`, `schedule_builder/schemas/position_schemas.py`, `services/position_service.py`, `controllers/position_controller.py` |
| 2026-07-20 | profile-matrix-editor (שלב 3, טאב מטריצה קריא) — טאב חדש **"תצוגת לוח"** (ברירת מחדל) ב-PositionsPage: טבלת עמדות×ימים (ראשון→שבת) לקריאה בלבד, שורות ב-display_order, תא פעיל מציג חלון `start–end` (en-dash) ותא כבוי מציג `✕` מעומעם; כותרת יום מציגה שם קצר + שבב תווית מ-`profile.day_labels[String(day)]` כשקיים (תוויות נצבעות **רק** במטריצה כרגע [EDGE I2]); תג האירוע מצויר זהה לכרטיסיות (משמש `position-event-badge`); טאב **"כרטיסיות"** מציג את ה-UI הקיים כמות שהוא (כולל drag-and-copy); דיפ-לינק `?edit=` נוחת אוטומטית בטאב כרטיסיות ופותח את העורך כמקודם; קליינט `bulkUpdateDaySchedules(profileId, items)` נוסף ל-step 04; המחרוזות העבריות ב-`messages.positions` (matrix/cards/matrixHours/matrixOff); אין שינוי backend | `frontend/admin/src/pages/builder/PositionsPage.jsx`, `components/positions/ProfileMatrix.jsx`, `api/builderApiClient.js`, `utils/messages.js`, `styles/admin.css`, טסטים `tests/profileMatrix.test.jsx`, `tests/builderApiClient.test.js`, `tests/builderPositionsPage.test.jsx` |
| 2026-07-19 | multi-admin (צעדים 1-3/6) — לוגין בהתאמה מדויקת של local-part (תחילית עם 2 אדמינים = 500 לטנטי), `require_super_admin`, ו-API ניהול אדמינים תחת `/auth/admin/admins*`: רשימה/יצירה (תמיד ADMIN)/השבתה-הפעלה/איפוס סיסמה, עם מעקות: אין השבתה עצמית או של סופר-אדמין, אין איפוס לעצמך, מייל כפול=409 כולל race | `admin_repository.py`, `admin_management_service.py`, `auth_controller.py`, `dependencies.py`, `user_schemas.py`, `exceptions.py` |
| 2026-07-19 | multi-admin (צעד 4/6) — `get_current_admin` בודק `is_active` מול ה-DB בכל בקשה: השבתת אדמין מנתקת מיד (401) ולא אחרי פקיעת הטוקן; אדמין שנמחק=401 ולא 500 | `dependencies.py` |
| 2026-07-19 | multi-admin (צעדים 5-6/6, הפיצ'ר הושלם) — הלוגין שומר role ב-localStorage (נמחק ב-logout/401) + סקשן "ניהול אדמינים" בהגדרות ל-SUPER_ADMIN בלבד: טבלה, יצירה, השבתה/הפעלה עם ConfirmDialog, איפוס סיסמה inline; שורות סופר-אדמין ללא פעולות. אומת end-to-end מול שרת dev חי: יצירה→לוגין כאדמין החדש→403 על ניהול→השבתה מנתקת טוקן חי מיד→איפוס סיסמה תופס | `adminApiClient.js`, `AdminsSection.jsx`, `SettingsPage.jsx`, `messages.js`, `admin.css` |
| 2026-07-19 | multi-admin round 2 — ניהול אדמינים עבר מעמוד ההגדרות לדף ייעודי `/admins` עם קישור בנאבבר (רק לסופר-אדמין); role הפך לשדה מנוהל: יצירה עם תפקיד (אדמין/צפייה — SUPER_ADMIN לא ניתן להקצאה) + `PATCH /auth/admin/admins/{id}/role` עם select בטבלה; תשתית להרשאות-לפי-ראוט עתידיות. שם הסופר-אדמין תוקן ל"יוסף כהן" (DB + SEED_ADMIN_FULL_NAME). אומת בדפדפן חי | `admin_management_service.py`, `auth_controller.py`, `AdminsPage.jsx`, `AdminsSection.jsx`, `Navbar.jsx`, `App.jsx` |
