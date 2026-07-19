"""
Copy/sync one activation profile's POSITIONS from the local dev DB to prod.

Surgical, unlike propagate_demo_to_prod.py (which wipes prod): positions are
merged BY NAME into the prod profile so existing schedule_assignments on
same-named positions keep their position ids:

  - name in both      → UPDATE day_schedules / required_attributes /
                        display_order / is_event / event_required_count
  - name only in dev  → INSERT
  - name only in prod → DELETE (cascades that position's assignments — the
                        plan prints how many BEFORE anything is written)

Duplicate names are legal (two ב-1 rows = two guards on the same position) —
positions are keyed by (name, occurrence#) with occurrences ordered by
display_order, so the Nth dev occurrence syncs onto the Nth prod occurrence.

Dry-run by default; pass --apply to write. Everything runs in one prod
transaction. Usage (from the repo root, backend venv):

    URL=$(railway variables --service Postgres --kv | grep '^DATABASE_PUBLIC_URL=' | cut -d= -f2-)
    PROD_DATABASE_URL="$URL" backend/.venv/bin/python scripts/copy_profile_to_prod.py "שגרה" [--apply]

The profile must exist on BOTH sides (matched by exact name); the profile row
itself (name/kind/default) is left untouched — only its positions sync.
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

POS_COLS = (
    "name, day_schedules, required_attributes, display_order, "
    "is_event, event_required_count"
)


def _as_json(value):
    return value if isinstance(value, (dict, list)) else json.loads(value)


def _norm(row):
    return (
        _as_json(row.day_schedules),
        sorted(_as_json(row.required_attributes)),
        row.display_order,
        row.is_event,
        row.event_required_count,
    )


def _key_by_occurrence(rows):
    """{(name, occurrence#): row} with occurrences ordered by display_order.

    Names may legally repeat (two ב-1 rows = two guards on that position);
    a plain name key would silently collapse them.
    """
    keyed = {}
    counts = {}
    for row in sorted(rows, key=lambda r: (r.name, r.display_order)):
        idx = counts.get(row.name, 0)
        counts[row.name] = idx + 1
        keyed[(row.name, idx)] = row
    return keyed


async def _profile_id(conn, name: str):
    row = (
        await conn.execute(
            text("SELECT id FROM activation_profiles WHERE name=:n"), {"n": name}
        )
    ).first()
    return row.id if row else None


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", help="profile name, e.g. שגרה")
    parser.add_argument("--apply", action="store_true", help="write to prod")
    args = parser.parse_args()

    prod_url = os.environ.get("PROD_DATABASE_URL")
    if not prod_url:
        print("PROD_DATABASE_URL not set (railway variables → DATABASE_PUBLIC_URL)")
        return 1
    prod_url = prod_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    from app.database import get_session  # dev side — backend/.env

    async with get_session() as dev:
        dev_pid = await _profile_id(dev, args.profile)
        if dev_pid is None:
            print(f"dev: profile {args.profile!r} not found")
            return 1
        dev_rows = _key_by_occurrence(
            (
                await dev.execute(
                    text(f"SELECT {POS_COLS} FROM positions WHERE profile_id=:i"),
                    {"i": dev_pid},
                )
            ).all()
        )

    eng = create_async_engine(prod_url)
    async with eng.begin() as prod:
        prod_pid = await _profile_id(prod, args.profile)
        if prod_pid is None:
            print(f"prod: profile {args.profile!r} not found")
            return 1
        prod_rows = _key_by_occurrence(
            (
                await prod.execute(
                    text(
                        f"SELECT {POS_COLS}, id FROM positions WHERE profile_id=:i"
                    ),
                    {"i": prod_pid},
                )
            ).all()
        )

        to_insert = sorted(set(dev_rows) - set(prod_rows))
        to_delete = sorted(set(prod_rows) - set(dev_rows))
        shared = set(dev_rows) & set(prod_rows)
        to_update = sorted(n for n in shared if _norm(dev_rows[n]) != _norm(prod_rows[n]))

        # Assignments that the deletes would cascade — shown before any write.
        doomed = []
        for name in to_delete:
            count = (
                await prod.execute(
                    text(
                        "SELECT count(*) FROM schedule_assignments "
                        "WHERE position_id=:p"
                    ),
                    {"p": prod_rows[name].id},
                )
            ).scalar()
            if count:
                doomed.append((name, count))

        print(f"plan for {args.profile!r}: dev {len(dev_rows)} positions → prod {len(prod_rows)}")
        print(f"  insert {len(to_insert)}: {to_insert}")
        print(f"  update {len(to_update)} (same name, new content)")
        print(f"  delete {len(to_delete)}: {to_delete}")
        if doomed:
            print(f"  ⚠ deletes cascade assignments: {doomed}")

        if not args.apply:
            print("dry-run only — rerun with --apply to write")
            return 0

        for name in to_update:
            d = dev_rows[name]
            await prod.execute(
                text(
                    "UPDATE positions SET day_schedules=:ds, required_attributes=:ra, "
                    "display_order=:o, is_event=:e, event_required_count=:c, "
                    "updated_at=now() WHERE id=:i"
                ),
                {
                    "ds": json.dumps(_as_json(d.day_schedules)),
                    "ra": json.dumps(_as_json(d.required_attributes)),
                    "o": d.display_order,
                    "e": d.is_event,
                    "c": d.event_required_count,
                    "i": prod_rows[name].id,
                },
            )
        for key in to_insert:
            d = dev_rows[key]
            await prod.execute(
                text(
                    "INSERT INTO positions (id, profile_id, name, day_schedules, "
                    "required_attributes, display_order, is_event, "
                    "event_required_count, created_at, updated_at) VALUES "
                    "(gen_random_uuid(), :p, :n, :ds, :ra, :o, :e, :c, now(), now())"
                ),
                {
                    "p": prod_pid,
                    "n": key[0],
                    "ds": json.dumps(_as_json(d.day_schedules)),
                    "ra": json.dumps(_as_json(d.required_attributes)),
                    "o": d.display_order,
                    "e": d.is_event,
                    "c": d.event_required_count,
                },
            )
        for name in to_delete:
            await prod.execute(
                text("DELETE FROM positions WHERE id=:i"),
                {"i": prod_rows[name].id},
            )

        final = (
            await prod.execute(
                text("SELECT count(*) FROM positions WHERE profile_id=:i"),
                {"i": prod_pid},
            )
        ).scalar()
        print(f"applied ✔ prod {args.profile!r} now has {final} positions")
    await eng.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
