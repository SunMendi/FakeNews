#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/mehedi/Documents/fakenews"
LOCK_FILE="/tmp/fakenews_fetch_news.lock"
LOG_FILE="$PROJECT_ROOT/fetch_news_cron.log"
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
MANAGE_PY="$PROJECT_ROOT/core/manage.py"

cd "$PROJECT_ROOT"

{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] cron_fetch_news: started"

  # Quick DB connectivity check so logs show root cause immediately.
  if ! "$PYTHON_BIN" "$MANAGE_PY" check --database default >/dev/null 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] cron_fetch_news: DB not reachable, skipping this run"
    exit 1
  fi

  # Prevent overlapping runs. If lock is busy, this invocation exits immediately.
  if ! flock -n "$LOCK_FILE" "$PYTHON_BIN" "$MANAGE_PY" fetch_news; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] cron_fetch_news: lock busy or fetch_news failed"
    exit 1
  fi

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] cron_fetch_news: completed"
} >> "$LOG_FILE" 2>&1
