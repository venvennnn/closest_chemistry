#!/bin/sh
set -eu
# Runs on every API boot so Railway/Render do not need a separate one-off shell.
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
