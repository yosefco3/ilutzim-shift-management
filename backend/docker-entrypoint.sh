#!/bin/bash
set -e

echo "=== Ilutzim Backend Entry Point ==="

# Wait for database using Python + SQLAlchemy
echo "Waiting for database..."
python -c "
import asyncio, os, sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def wait_for_db():
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        print('  DATABASE_URL not set, skipping DB wait')
        return
    engine = create_async_engine(url)
    for i in range(30):
        try:
            async with engine.connect() as conn:
                await conn.execute(text('SELECT 1'))
            print('  Database is ready!')
            break
        except Exception:
            print(f'  Database not ready (attempt {i+1}/30)...')
            import time; time.sleep(2)
    else:
        print('  ERROR: Database not available after 60s')
        sys.exit(1)
    await engine.dispose()

asyncio.run(wait_for_db())
"

# Run Alembic migrations
echo "Running database migrations..."
alembic upgrade head
echo "  Migrations complete."

# Seed admin user (idempotent)
echo "Seeding admin user (if not exists)..."
python -m app.seed
echo "  Seed complete."

echo "=== Starting application ==="
exec "$@"