#!/usr/bin/env python
"""
Dev-only CLI: seed (or wipe) the attendance demo history.

    cd backend
    .venv/bin/python scripts/seed_attendance_demo.py            # seed 8 weeks
    .venv/bin/python scripts/seed_attendance_demo.py --weeks 8 --seed 42
    .venv/bin/python scripts/seed_attendance_demo.py --wipe     # remove all demo data

Refuses to run unless ENVIRONMENT=dev. See app/attendance/dev_seed.py for the
engine and STAGE_3_PROMPTS/02_5_demo_history_and_locked_access/ for the spec.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Initialize the full model registry FIRST — entering the attendance package
# before app.models would trip its registration import cycle.
import app.models  # noqa: E402,F401

from app.attendance.dev_seed import run  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed attendance demo history (dev only)")
    parser.add_argument("--weeks", type=int, default=8, help="how many past weeks to fill")
    parser.add_argument("--wipe", action="store_true", help="remove all demo data and exit")
    parser.add_argument("--seed", type=int, default=42, help="deterministic random seed")
    args = parser.parse_args()
    asyncio.run(run(weeks=args.weeks, wipe_only=args.wipe, seed=args.seed))


if __name__ == "__main__":
    main()
