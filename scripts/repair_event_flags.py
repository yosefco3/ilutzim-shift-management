"""
Repair event positions ("לא מפוצל") that an old profile-duplicate bug stripped.

Before the fix (see fix-duplicate-event-loss), duplicating a profile dropped
``is_event`` + ``event_required_count`` from every copied position, so event
positions in copies rendered as ordinary splitting ones (no event badge in
cards/matrix, no event cells on the board). This script restores them.

How it decides (pure logic in app.schedule_builder.utils.event_repair):
  - Read the BASE profile (``is_base=True``; falls back to ``is_default=True``
    with a warning on pre-migration DBs) and collect its EVENT positions,
    keyed by name → event_required_count.
  - In every OTHER profile, a same-named position that is NOT currently an event
    is a repair candidate. The base's count is written only when the candidate
    has none (a real count is never overwritten).
  - A copy position renamed after duplication won't match — names are the only
    stable identity across a duplicate. Such positions are left untouched.

Dry-run by default (prints the plan, writes nothing). Pass --apply to write, in
one transaction. Idempotent: a second run finds nothing.

Usage:

    # local/dev DB — run from backend/ so app config finds backend/.env:
    cd backend && .venv/bin/python ../scripts/repair_event_flags.py [--apply]

    # explicit DB (e.g. prod) — the override skips app config, runs from anywhere.
    # See the plan FIRST, then --apply:
    URL=$(railway variables --service Postgres --kv | grep '^DATABASE_PUBLIC_URL=' | cut -d= -f2-)
    DATABASE_URL_OVERRIDE="$URL" backend/.venv/bin/python scripts/repair_event_flags.py
    DATABASE_URL_OVERRIDE="$URL" backend/.venv/bin/python scripts/repair_event_flags.py --apply
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.schedule_builder.utils.event_repair import build_repair_plan  # noqa: E402


async def _load_and_plan(conn):
    """Read the base + candidate positions and return (base_row, plan)."""
    base = (
        await conn.execute(
            text(
                "SELECT id, name FROM activation_profiles "
                "WHERE is_base ORDER BY display_order LIMIT 1"
            )
        )
    ).first()
    if base is None:
        base = (
            await conn.execute(
                text(
                    "SELECT id, name FROM activation_profiles "
                    "WHERE is_default ORDER BY display_order LIMIT 1"
                )
            )
        ).first()
        if base is not None:
            print(
                f"⚠ no is_base profile; falling back to the default {base.name!r} "
                "as the base (pre-migration DB)"
            )
    if base is None:
        print("no base/default profile found — nothing to do")
        return None, []

    base_events = {
        r.name: r.event_required_count
        for r in (
            await conn.execute(
                text(
                    "SELECT name, event_required_count FROM positions "
                    "WHERE profile_id = :pid AND is_event"
                ),
                {"pid": base.id},
            )
        ).all()
    }

    candidates = (
        await conn.execute(
            text(
                "SELECT ap.name AS profile_name, p.id, p.name, p.is_event, "
                "p.event_required_count "
                "FROM positions p JOIN activation_profiles ap ON ap.id = p.profile_id "
                "WHERE p.profile_id <> :pid"
            ),
            {"pid": base.id},
        )
    ).all()

    return base, build_repair_plan(base_events, candidates)


def _print_plan(base, plan):
    print(f"base profile: {base.name!r}")
    if not plan:
        print("nothing to repair — all event positions look correct ✔")
        return
    print(f"{len(plan)} position(s) to repair (restore is_event + count):")
    for item in plan:
        count = "∞" if item.set_count is None else item.set_count
        print(f"  [{item.profile_name}] {item.position_name!r} → event (count={count})")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the repair")
    args = parser.parse_args()

    override = os.environ.get("DATABASE_URL_OVERRIDE")
    engine = None
    if override:
        override = override.replace("postgresql://", "postgresql+asyncpg://", 1)
        engine = create_async_engine(override)
        ctx = engine.begin()
    else:
        from app.database import get_session

        ctx = get_session()

    try:
        async with ctx as conn:
            base, plan = await _load_and_plan(conn)
            _print_plan(base, plan)
            if not plan:
                return 0
            if not args.apply:
                print("dry-run only — rerun with --apply to write")
                return 0
            for item in plan:
                await conn.execute(
                    text(
                        "UPDATE positions SET is_event = :e, "
                        "event_required_count = :c, updated_at = now() "
                        "WHERE id = :i"
                    ),
                    {"e": True, "c": item.set_count, "i": item.position_id},
                )
            # get_session() commits on clean exit; engine.begin() commits too.
            print(f"applied ✔ repaired {len(plan)} position(s)")
            return 0
    finally:
        if engine is not None:
            await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
