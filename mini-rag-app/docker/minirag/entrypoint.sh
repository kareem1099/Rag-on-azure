#!/bin/bash
set -e

echo "Running database migrations..."
cd /app/models/dbschemas/minirag
alembic upgrade head
cd /app

exec "$@"
