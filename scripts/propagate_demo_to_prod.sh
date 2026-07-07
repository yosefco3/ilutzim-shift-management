#!/usr/bin/env bash
# רענון דמו בפרודקשן — פקודה אחת, מכל מקום עם הריפו + railway CLI מחובר.
#
#     scripts/propagate_demo_to_prod.sh
#
# מושך את DATABASE_PUBLIC_URL מ-Railway ומריץ את propagate_demo_to_prod.py
# (--commit --yes). לוקח ~5–10 דקות (חיבור מרחוק, המון round-trips).
# בטוח להריץ שוב אם נקטע — הריצה הבאה מנקה וזורעת מחדש.
set -euo pipefail
cd "$(dirname "$0")/.."

URL=$(railway variables --service Postgres --kv | grep '^DATABASE_PUBLIC_URL=' | cut -d= -f2-)
if [ -z "$URL" ]; then
    echo "לא נמצא DATABASE_PUBLIC_URL — ודא ש-railway מחובר (railway login && railway link)" >&2
    exit 1
fi

DATABASE_URL="$URL" exec backend/.venv/bin/python scripts/propagate_demo_to_prod.py --commit --yes "$@"
