#!/bin/sh
set -e

echo "Running database migrations..."
python -m alembic upgrade head || echo "Migration failed or already up to date"

echo "Starting server..."
exec python -m app.server
