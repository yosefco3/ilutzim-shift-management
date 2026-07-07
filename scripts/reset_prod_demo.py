#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reset a DB (typically PRODUCTION) back to a clean, empty state after a demo.

The counterpart of ``propagate_demo_to_prod.py``: removes EVERYTHING the demo
seeded — weeks, guards, profiles and all their cascades (submissions,
assignments, actual schedules, attendance events) — and leaves the app the way
a fresh install looks:

    * admins, system settings and the attribute vocabulary — preserved
    * one upcoming Sun–Sat week, CLOSED (same as app.seed's initial week)
    * zero guards / profiles / positions / submissions / schedules

USAGE
    python3 scripts/reset_prod_demo.py                 # dry-run (plan only)
    python3 scripts/reset_prod_demo.py --commit        # asks for confirmation
    python3 scripts/reset_prod_demo.py --commit --yes  # non-interactive

The target DB is taken from DATABASE_URL (env). ``scripts/reset_prod_demo.sh``
wraps this with the Railway public URL — that is the production entry point.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"


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
    tail = url.rsplit("@", 1)[-1]
    return tail.split("?")[0]


async def run(commit: bool) -> int:
    from sqlalchemy import delete, func, select

    from app.constants import WeekStatus
    from app.database import get_session
    from app.models.schedule_week import ScheduleWeek
    from app.models.user import User
    from app.schedule_builder.models.activation_profile import ActivationProfile
    from app.utils.date_utils import today_il, week_range

    start, end = week_range(today_il())

    async with get_session() as session:
        counts = {}
        for label, model in (
            ("שבועות", ScheduleWeek), ("מאבטחים", User), ("פרופילים", ActivationProfile),
        ):
            counts[label] = (
                (await session.execute(select(func.count(model.id)))).scalar()
            )
        print("יימחקו (כולל כל מה שתלוי בהם — הגשות, שיבוצים, סידור בפועל, נוכחות):")
        for label, n in counts.items():
            print(f"  {label}: {n}")
        print(f"יישמרו: אדמינים, הגדרות מערכת, אוצר התכונות")
        print(f"ייווצר: שבוע ריק {start} – {end} (CLOSED, כמו התקנה נקייה)")
        if not commit:
            print("\n— הרצה יבשה. הוסף --commit כדי לאפס. —")
            return 0

        for model in (ScheduleWeek, User, ActivationProfile):
            await session.execute(delete(model))
        session.add(ScheduleWeek(
            start_date=start, end_date=end, status=WeekStatus.CLOSED,
        ))
        await session.commit()

        remaining = {}
        for label, model in (
            ("שבועות", ScheduleWeek), ("מאבטחים", User), ("פרופילים", ActivationProfile),
        ):
            remaining[label] = (
                (await session.execute(select(func.count(model.id)))).scalar()
            )

    print("\n=== אחרי האיפוס ===")
    for label, n in remaining.items():
        print(f"  {label}: {n}")
    print("✅ הדמו נמחק. המערכת נקייה ומוכנה לשימוש אמיתי.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset the demo data out of a DB")
    parser.add_argument("--commit", action="store_true", help="actually delete (default: dry-run)")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args()

    _reexec_in_backend_venv()
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))

    import logging
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://"):
        os.environ["DATABASE_URL"] = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    import app.models  # noqa: F401 — init the model registry before anything else
    import app.schedule_builder.models  # noqa: F401
    import app.attendance.models  # noqa: F401

    from app.config import settings

    print(f"DB יעד: {_mask_db(settings.DATABASE_URL)}")
    if args.commit and not args.yes:
        print("⚠️  זה ימחק את כל נתוני הדמו (שבועות/מאבטחים/פרופילים) מה-DB הזה.")
        if not sys.stdin.isatty() or input("להמשיך? הקלד 'yes': ").strip().lower() not in ("yes", "y"):
            print("בוטל.")
            return 1

    return asyncio.run(run(args.commit))


if __name__ == "__main__":
    raise SystemExit(main())
