#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Propagate the full 065 demo dataset into a target DB (typically PRODUCTION).

One re-runnable command that makes the app demo-ready for any meeting date —
everything is anchored to *today* (Israel time), so re-running refreshes the
demo to the current calendar:

    last week     LOCKED + published — full board + actual schedule (editable
                  in "סידור בפועל")
    current week  LOCKED + published — full board + actual schedule
    next week     OPEN — 50 constraint submissions (the 065 fuzzy availability)

Also seeds the 50-guard 065 roster (with attributes) and the 065 activation
profile (39 positions), bound to all three weeks.

⚠️  DESTRUCTIVE: wipes schedule_weeks, users and activation_profiles (all their
cascades: submissions, assignments, actual schedules, attendance events).
Admins, system settings and the attribute vocabulary are preserved.

USAGE
    python3 scripts/propagate_demo_to_prod.py                 # dry-run (plan only)
    python3 scripts/propagate_demo_to_prod.py --commit        # asks for confirmation
    python3 scripts/propagate_demo_to_prod.py --commit --yes  # non-interactive

The target DB is taken from DATABASE_URL (env). ``scripts/propagate_demo_to_prod.sh``
wraps this with the Railway public URL — that is the production entry point.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"
FIXTURES_DIR = REPO_ROOT / "scripts" / "constraints_065"

BOARD_SEED = 650  # deterministic boards; per-week offset added below


def _reexec_in_backend_venv() -> None:
    try:
        import fastapi  # noqa: F401
        return
    except Exception:
        pass
    venv_py = BACKEND / ".venv" / "bin" / "python"
    if venv_py.exists() and Path(sys.executable) != venv_py:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(BACKEND) + os.pathsep + env.get("PYTHONPATH", "")
        os.execve(str(venv_py), [str(venv_py), __file__, *sys.argv[1:]], env)


def _mask_db(url: str) -> str:
    """host:port/db without credentials, for the confirmation prompt."""
    tail = url.rsplit("@", 1)[-1]
    return tail.split("?")[0]


# ── week anchoring ────────────────────────────────────────────────────────────

def demo_weeks(today: date) -> dict[str, tuple[date, date]]:
    """last/current/next Sunday→Saturday windows around *today*.

    ``week_range`` returns the UPCOMING week (next Sunday), which is exactly
    the OPEN submission target; current and last are derived from it.
    """
    from app.utils.date_utils import week_range

    nstart, nend = week_range(today)
    return {
        "last": (nstart - timedelta(days=14), nend - timedelta(days=14)),
        "current": (nstart - timedelta(days=7), nend - timedelta(days=7)),
        "next": (nstart, nend),
    }


# ── plausible board generator ────────────────────────────────────────────────
# build_fixtures has positions + roster + availability but NOT the real board,
# so past-week assignments are generated: category+attribute aware, greedy,
# deterministic, with day-to-day position continuity like a real board.

def generate_board(rng: random.Random, guards: list[dict], positions: list[dict]):
    """Yield (position_index, day_index, guard_name) for one week.

    positions: [{"idx", "shift" (בוקר/ערב/לילה), "req" (attr labels)}]
    guards:    build_fixtures.GUARDS dicts (cat/base/patrol/weekend).
    """
    import build_fixtures as bf

    workdays: dict[str, int] = {g["name"]: 0 for g in guards}
    prev_holder: dict[int, str] = {}
    by_name = {g["name"]: g for g in guards}

    def tiers(pos: dict) -> list[list[str]]:
        """Candidate names, best tier first."""
        if bf.ACHMASH in pos["req"]:
            return [[g["name"] for g in guards if g["base"] == bf.ACHMASH]]
        if bf.PATROL in pos["req"]:
            return [[g["name"] for g in guards if g["patrol"]]]
        shift = pos["shift"]
        if shift == "בוקר":
            return [
                [g["name"] for g in guards if g["cat"] == "morning" and g["base"] != bf.ACHMASH],
                [g["name"] for g in guards if g["cat"] == "morning"],
            ]
        if shift == "ערב":
            return [
                [g["name"] for g in guards if g["cat"] == "evening"],
                [g["name"] for g in guards if g["cat"] == "morning" and g["base"] == bf.ARMED],
            ]
        return [  # לילה
            [g["name"] for g in guards if g["cat"] == "night"],
            [g["name"] for g in guards if g["cat"] == "evening"],
            [g["name"] for g in guards if g["cat"] == "morning" and g["base"] == bf.ARMED],
        ]

    for day in range(7):
        busy: set[str] = set()
        weekend = day in (5, 6)
        for pos in positions:
            def ok(name: str) -> bool:
                g = by_name[name]
                if name in busy or workdays[name] >= 6:
                    return False
                if weekend and not g["weekend"]:
                    # a real board still borrows a few non-weekend guards
                    return rng.random() < 0.30
                return True

            pick = None
            prev = prev_holder.get(pos["idx"])
            if prev is not None and ok(prev) and rng.random() < 0.75:
                pick = prev  # position continuity, like a real board
            else:
                for tier in tiers(pos):
                    avail = [n for n in tier if ok(n)]
                    if avail:
                        avail.sort(key=lambda n: (workdays[n], rng.random()))
                        pick = avail[0]
                        break
            if pick is None:
                prev_holder.pop(pos["idx"], None)  # gap — happens on weekends
                continue
            busy.add(pick)
            workdays[pick] += 1
            prev_holder[pos["idx"]] = pick
            yield pos["idx"], day, pick


# ── DB phases ─────────────────────────────────────────────────────────────────

async def wipe(session) -> dict[str, int]:
    from sqlalchemy import delete, func, select

    from app.models.schedule_week import ScheduleWeek
    from app.models.user import User
    from app.schedule_builder.models.activation_profile import ActivationProfile

    counts = {}
    for label, model in (
        ("weeks", ScheduleWeek), ("users", User), ("profiles", ActivationProfile),
    ):
        counts[label] = (await session.execute(select(func.count(model.id)))).scalar()
        await session.execute(delete(model))
    await session.commit()
    return counts


async def seed_profile_and_weeks(session, weeks: dict):
    """065 profile + 39 positions; three weeks with real-lifecycle states."""
    from app.constants import WeekStatus
    from app.models.schedule_week import ScheduleWeek
    from app.schedule_builder.models.activation_profile import ActivationProfile
    from app.schedule_builder.models.position import Position
    from app.schedule_builder.models.week_profile_assignment import (
        WeekProfileAssignment,
    )
    from app.schedule_builder.repositories.attribute_repository import (
        AttributeRepository,
    )
    from app.schedule_builder.services.attribute_service import AttributeService

    import build_fixtures as bf
    import seed_profile as sp  # only for the label→key mapping helpers

    await AttributeService(AttributeRepository(session)).seed_default_attributes()

    profile_json = bf.build_profile()
    profile = ActivationProfile(
        name=profile_json["profile_name"],
        kind=profile_json.get("profile_type"),
        description="דמו — נזרע ע\"י propagate_demo_to_prod",
        is_default=True,
        display_order=0,
    )
    session.add(profile)
    await session.flush()

    positions_meta = []
    for i, pos in enumerate(sp._to_db_positions(profile_json)):
        session.add(Position(
            profile_id=profile.id,
            name=pos["name"],
            day_schedules=pos["day_schedules"],
            required_attributes=pos["required_attributes"],
            display_order=i,
        ))
        src = profile_json["positions"][i]
        positions_meta.append(
            {"idx": i, "shift": src["shift_origin"], "req": src["required_attributes"]}
        )

    week_rows = {}
    for key, (start, end) in weeks.items():
        is_open = key == "next"
        week = ScheduleWeek(
            start_date=start,
            end_date=end,
            status=WeekStatus.OPEN if is_open else WeekStatus.LOCKED,
            # opened_at: the Tuesday before the week, 10:00 — the usual auto-open
            opened_at=datetime.combine(start - timedelta(days=5), time(10, 0)),
            # published Thursday evening before the week starts; the open week
            # has no schedule yet so it is not published
            published_at=None if is_open else datetime.combine(
                start - timedelta(days=3), time(18, 0)
            ),
        )
        session.add(week)
        week_rows[key] = week
    await session.flush()
    for week in week_rows.values():
        session.add(WeekProfileAssignment(week_id=week.id, profile_id=profile.id))
    await session.commit()
    return profile, positions_meta, week_rows


async def import_constraints_for(week_start: date, week_end: date) -> int:
    """Generate the 065 workbook for the target week and commit it (creates users)."""
    import build_fixtures as bf

    from app.database import get_session
    from app.repositories.schedule_week_repository import ScheduleWeekRepository
    from app.repositories.submission_repository import SubmissionRepository
    from app.repositories.user_repository import UserRepository
    from app.services.constraints_import.commit import ConstraintsCommitService
    from app.services.constraints_import.parser import parse_constraints_xlsx
    from app.services.submission_service import SubmissionService

    bf.WEEK_TITLE = f"אילוצים שהוגשו — {week_start.isoformat()} עד {week_end.isoformat()}"
    os.makedirs(bf.OUT_DIR, exist_ok=True)
    xlsx_path = bf.build_constraints()
    parsed = parse_constraints_xlsx(Path(xlsx_path).read_bytes())

    async with get_session() as session:
        service = ConstraintsCommitService(
            user_repo=UserRepository(session),
            week_repo=ScheduleWeekRepository(session),
            submission_service=SubmissionService(
                submission_repo=SubmissionRepository(session),
                user_repo=UserRepository(session),
                week_repo=ScheduleWeekRepository(session),
            ),
        )
        resp = await service.commit(parsed)
    return resp.summary.imported


async def fix_guard_attributes(session) -> int:
    """Exact roles + preferred shift per the 065 roster (notes parsing is fuzzy)."""
    from sqlalchemy import select

    from app.constants import ShiftType, UserRole
    from app.models.user import User

    import build_fixtures as bf

    base_role = {
        bf.ACHMASH: UserRole.AHMASH.value,
        bf.ARMED: UserRole.ARMED.value,
        bf.UNARMED: UserRole.UNARMED.value,
    }
    pref = {
        "morning": ShiftType.MORNING.value,
        "evening": ShiftType.AFTERNOON.value,
        "night": ShiftType.NIGHT.value,
        "super": None,
    }
    def norm(name: str) -> str:
        # the import parser strips apostrophes/geresh from names — match it
        return name.replace("’", "").replace("'", "").strip()

    users = (await session.execute(select(User))).scalars().all()
    by_name = {norm(u.full_name): u for u in users}
    fixed = 0
    for g in bf.GUARDS:
        user = by_name.get(norm(g["name"]))
        if user is None:
            print(f"  ⚠️ מאבטח מהרוסטר לא נמצא ב-DB: {g['name']}")
            continue
        roles = [base_role[g["base"]]]
        if g["patrol"]:
            roles.append(UserRole.PATROL_VEHICLE.value)
        user.roles = roles
        user.preferred_shift = pref[g["cat"]]
        fixed += 1
    await session.commit()
    return fixed


async def seed_boards(session, week_rows: dict, positions_meta: list[dict]) -> dict:
    """Full plausible boards for the last + current weeks."""
    from sqlalchemy import select

    from app.models.user import User
    from app.schedule_builder.models.position import Position
    from app.schedule_builder.models.schedule_assignment import ScheduleAssignment

    import build_fixtures as bf

    users = (await session.execute(select(User))).scalars().all()
    user_by_name = {u.full_name: u for u in users}
    positions = (
        (await session.execute(select(Position).order_by(Position.display_order)))
        .scalars().all()
    )
    counts = {}
    for offset, key in enumerate(("last", "current")):
        week = week_rows[key]
        rng = random.Random(BOARD_SEED + offset)
        n = 0
        for pos_idx, day, name in generate_board(rng, bf.GUARDS, positions_meta):
            user = user_by_name.get(name)
            if user is None:
                continue
            session.add(ScheduleAssignment(
                week_id=week.id,
                position_id=positions[pos_idx].id,
                day_index=day,
                user_id=user.id,
            ))
            n += 1
        counts[key] = n
    await session.commit()
    return counts


async def seed_actual(week_rows: dict) -> None:
    from app.database import get_session
    from app.schedule_builder.dependencies import build_actual_schedule_service

    async with get_session() as session:
        service = build_actual_schedule_service(session)
        for key in ("last", "current"):
            await service.ensure_for_week(week_rows[key].id, source="rollover")


async def summary() -> None:
    from sqlalchemy import func, select

    from app.database import get_session
    from app.models.daily_status import DailyStatus
    from app.models.schedule_week import ScheduleWeek
    from app.models.user import User
    from app.models.weekly_submission import WeeklySubmission
    from app.schedule_builder.models.actual_assignment import ActualAssignment
    from app.schedule_builder.models.actual_schedule import ActualSchedule
    from app.schedule_builder.models.position import Position
    from app.schedule_builder.models.schedule_assignment import ScheduleAssignment

    async with get_session() as session:
        async def count(model):
            return (await session.execute(select(func.count(model.id)))).scalar()

        print("\n=== מצב ה-DB אחרי הזריעה ===")
        for label, model in (
            ("מאבטחים", User), ("עמדות", Position), ("הגשות", WeeklySubmission),
            ("סטטוסים יומיים", DailyStatus), ("שיבוצים מתוכננים", ScheduleAssignment),
            ("סידורים בפועל", ActualSchedule), ("שיבוצים בפועל", ActualAssignment),
        ):
            print(f"  {label}: {await count(model)}")
        weeks = (
            (await session.execute(select(ScheduleWeek).order_by(ScheduleWeek.start_date)))
            .scalars().all()
        )
        for w in weeks:
            pub = "פורסם" if w.published_at else "לא פורסם"
            print(f"  שבוע {w.start_date}–{w.end_date}: {w.status.value} · {pub}")


async def run(commit: bool) -> int:
    from app.utils.date_utils import today_il

    today = today_il()
    weeks = demo_weeks(today)
    print(f"היום (IL): {today}")
    for key, label in (("last", "שבוע שעבר"), ("current", "השבוע"), ("next", "שבוע הבא")):
        s, e = weeks[key]
        state = "OPEN + אילוצים" if key == "next" else "LOCKED + סידור + בפועל"
        print(f"  {label}: {s} – {e}  →  {state}")
    if not commit:
        print("\n— הרצה יבשה. הוסף --commit כדי לזרוע. —")
        return 0

    from app.database import get_session

    async with get_session() as session:
        wiped = await wipe(session)
    print(f"\n🧹 נמחקו: {wiped['weeks']} שבועות, {wiped['users']} משתמשים, "
          f"{wiped['profiles']} פרופילים (+כל מה שתלוי בהם)")

    async with get_session() as session:
        profile, positions_meta, week_rows = await seed_profile_and_weeks(session, weeks)
        print(f"🏗️  פרופיל \"{profile.name}\" — {len(positions_meta)} עמדות, שויך ל-3 שבועות")

        imported = await import_constraints_for(*weeks["next"])
        print(f"📥 יובאו אילוצים ל-{imported} מאבטחים (שבוע {weeks['next'][0]})")

        fixed = await fix_guard_attributes(session)
        print(f"🎖️  עודכנו תכונות ומשמרת מועדפת ל-{fixed} מאבטחים")

        boards = await seed_boards(session, week_rows, positions_meta)
        print(f"📋 שיבוצים: שבוע שעבר {boards['last']}, השבוע {boards['current']}")

        await seed_actual(week_rows)
        print("✅ סידור בפועל נוצר לשבוע שעבר ולשבוע הנוכחי (rollover)")

    await summary()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Propagate the 065 demo into a DB")
    parser.add_argument("--commit", action="store_true", help="actually write (default: dry-run)")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args()

    _reexec_in_backend_venv()
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))
    sys.path.insert(0, str(FIXTURES_DIR))

    import logging
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # normalize a plain postgres URL (Railway public URL) for asyncpg
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://"):
        os.environ["DATABASE_URL"] = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        url = os.environ["DATABASE_URL"]

    import app.models  # noqa: F401 — init the model registry before anything else
    import app.schedule_builder.models  # noqa: F401
    import app.attendance.models  # noqa: F401

    from app.config import settings

    print(f"DB יעד: {_mask_db(settings.DATABASE_URL)}")
    if args.commit and not args.yes:
        print("⚠️  זה ימחק את כל השבועות/המאבטחים/הפרופילים ב-DB הזה ויזרע דמו.")
        if not sys.stdin.isatty() or input("להמשיך? הקלד 'yes': ").strip().lower() not in ("yes", "y"):
            print("בוטל.")
            return 1

    return asyncio.run(run(args.commit))


if __name__ == "__main__":
    raise SystemExit(main())
