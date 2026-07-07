#!/usr/bin/env bash
# איפוס דמו בפרודקשן — להריץ אחרי ההדגמה לבוס.
#
#     scripts/reset_prod_demo.sh
#
# מושך את DATABASE_PUBLIC_URL מ-Railway ומריץ את reset_prod_demo.py.
# מבקש אישור אינטראקטיבי (בלי --yes בכוונה — מחיקה חד-כיוונית).
set -euo pipefail
cd "$(dirname "$0")/.."

URL=$(railway variables --service Postgres --kv | grep '^DATABASE_PUBLIC_URL=' | cut -d= -f2-)
if [ -z "$URL" ]; then
    echo "לא נמצא DATABASE_PUBLIC_URL — ודא ש-railway מחובר (railway login && railway link)" >&2
    exit 1
fi

DATABASE_URL="$URL" exec backend/.venv/bin/python scripts/reset_prod_demo.py --commit "$@"
