#!/usr/bin/env bash
# Generate strong random secrets for the Railway production environment.
# Paste the output into the Railway service Variables (never commit them).
set -euo pipefail

gen() { python3 -c "import secrets; print(secrets.token_hex(32))"; }

echo "# ── Ilutzim production secrets (paste into Railway Variables) ──"
echo "JWT_SECRET_KEY=$(gen)"
echo "ADMIN_API_KEY=$(gen)"
echo
echo "# Reminder: set a strong SEED_ADMIN_PASSWORD too (>=10 chars, letter + digit)."
