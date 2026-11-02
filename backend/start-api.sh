#!/bin/sh
set -eu
# Runs on every API boot so Railway/Render do not need a separate one-off shell.
alembic upgrade head
# Same-container worker so extract jobs are claimed even without a second Railway service.
# Photos stay on this disk. Set RUN_WORKER=0 if you run Dockerfile.worker instead.
if [ "${RUN_WORKER:-1}" != "0" ]; then
  python -m app.worker &
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
