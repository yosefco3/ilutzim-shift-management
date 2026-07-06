#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backfill structured guard attributes from existing free-text notes.

Earlier imports dumped a guard's constraining attributes (אחמ"ש / רכב סיור /
חמוש) into the submission's free-text ``general_notes`` and left ``User.roles``
empty — so the schedule builder couldn't tell who is אחמ"ש and raised false
"חוסר מאפיין נדרש" warnings.

This one-off pass walks every submission's notes, lifts the recognised
attribute tokens into the guard's ``User.roles`` (union — never drops a manual
role) and rewrites the note to its residual text. After this the board enforces
the attributes correctly with no re-import.

    python3 scripts/backfill_guard_attributes.py            # dry-run (no writes)
    python3 scripts/backfill_guard_attributes.py --commit   # write to the DB
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


async def _run(commit: bool) -> int:
    from sqlalchemy import select

    from app.database import async_session_factory
    from app.models.user import User
    from app.models.weekly_submission import WeeklySubmission
    from app.services.constraints_import.attributes import split_notes

    changed_users = 0
    changed_notes = 0

    async with async_session_factory() as session:
        users = {
            u.id: u
            for u in (await session.execute(select(User))).scalars().all()
        }
        subs = (await session.execute(select(WeeklySubmission))).scalars().all()

        for sub in subs:
            roles, cleaned = split_notes(sub.general_notes)
            user = users.get(sub.user_id)
            note_changed = cleaned != sub.general_notes
            role_add = []
            if user is not None and roles:
                role_add = [r for r in roles if r not in (user.roles or [])]

            if not role_add and not note_changed:
                continue

            who = user.full_name if user else str(sub.user_id)
            if role_add:
                print(f"  {who}: roles += {role_add}  (had {list(user.roles or [])})")
                user.roles = list(user.roles or []) + role_add
                changed_users += 1
            if note_changed:
                print(f"  {who}: notes {sub.general_notes!r} → {cleaned!r}")
                sub.general_notes = cleaned
                changed_notes += 1

        if commit:
            await session.commit()
            print(f"\n✓ committed — {changed_users} role updates, {changed_notes} note rewrites")
        else:
            await session.rollback()
            print(f"\n(dry-run) would apply {changed_users} role updates, {changed_notes} note rewrites")
            print("re-run with --commit to write.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill guard attributes from notes")
    parser.add_argument("--commit", action="store_true", help="write to the DB (default: dry-run)")
    args = parser.parse_args()

    _reexec_in_backend_venv()
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))

    import logging
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    return asyncio.run(_run(args.commit))


if __name__ == "__main__":
    raise SystemExit(main())
