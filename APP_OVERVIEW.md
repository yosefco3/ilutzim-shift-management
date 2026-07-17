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

**Part B:** `ActivationProfile` → `Position` (day_schedules JSON, required_attributes, is_event + event_required_count) · `RequirementAttribute` (אוצר מילים) · `WeekProfileAssignment` (שבוע↔פרופיל) · `ScheduleAssignment` (week×position×day×user + segment) · `SavedSchedule` (snapshot JSON לשבוע) · `ActualSchedule` → `ActualPosition`/`ActualAssignment`/`ActualReinforcement` (עותק 1:1 עריך, נזרע ברולאובר).

**Stage 3:** `AttendanceEvent` (החתמה IN/OUT + GPS) · `AttendanceShift` (זיווג מול הסידור; violations) · `AttendanceAdjustment` (תיקון ידני, audit) · `AttendanceAlertSent` (מניעת כפל התראות).

**Procedures (סד"פ) — `backend/app/procedures/`:** `Procedure` (title/body; DRAFT/PUBLISHED/ARCHIVED) · `QuizQuestion` (בנק MCQ; source AI/MANUAL + edited_at — ריג'נרציה מוחקת רק AI לא-ערוכות) · `QuizAttempt` (מדגם שאלות + תשובות snapshot; unique חלקי על IN_PROGRESS) · `QuizPollLink` (poll_id טלגרם → attempt/question + סדר תשובות מעורבב) · `ProcedureReminderSent` (תזכורת אחת per מאבטח+נוהל). ג'נרציית שאלות: Claude API (מודל בהגדרה `procedure_ai_model`, ברירת מחדל claude-opus-4-8; ANTHROPIC_API_KEY אופציונלי — בלעדיו generate מחזיר 503 והאפליקציה עולה רגיל). מבחן: quiz polls בבוט, מעבר ≥`procedure_pass_threshold` (80), מדגם `procedure_quiz_size` (7).

## Endpoints (קבוצות עיקריות)
- `/auth` — התחברות אדמין · `/submissions` — הגשות מאבטח (Telegram initData)
- `/admin/users` · `/admin/weeks` (open/close/publish/lock) · `/admin/notifications` · `/admin/export` · `/admin/settings` · `/admin/import/constraints`
- `/admin/builder/*` (Part B) — profiles / positions / attributes / board / **pool** / assignments / warnings / saved-schedules
- `/admin/actual/*` — הסידור בפועל (עמדות, שיבוצים, מתגברים, ייצוא Excel/PNG, save-as-profile)
- `/admin/attendance/*` — events / shifts / adjustments / comparison / דוחות שכר
- `/admin/procedures/*` — נהלים (סד"פ): CRUD + upload docx + generate + questions + publish + results (תחת `PROCEDURES_ENABLED`)
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
| `PROCEDURES_ENABLED` + `VITE_PROCEDURES_ENABLED` | **off** | off (טרם — יודלק בצעד האחרון של הפיצ'ר) |

## דיפלוי
- **Railway**, live מאז 2026-06-20 (דומיין הפרוד לא מתועד בריפו הציבורי — נמצא ב-Railway/cloudflared). ענף הדיפלוי: **`production`** (push = deploy).
- **כלל ברזל:** אחרי כל step ירוק — commit ואז push ל-`development` **וגם** `development:production`.
- docker-entrypoint מריץ `alembic upgrade head` + seed אדמין בכל דיפלוי — אין צעד מיגרציה ידני בפרוד.
- לוגים בפרוד ברמת WARNING — `logger.info` לא נראה; אל תסיק מצב פיצ'ר מהיעדר לוג.
- runbooks: `PROPAGATE_DEMO_PROD.md` (רענון דמו), `HANDOVER_OWNERSHIP.md` (העברת בעלות), `README.md` (showcase).

## טסטים
- Backend: ~880 טסטים / 103 קבצים (`backend/tests/`, SQLite in-memory + fixtures ב-conftest).
- Frontend: ~430 טסטים / 52 קבצים (`frontend/admin/tests/`, vitest+RTL).
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
