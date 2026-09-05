#!/usr/bin/env sh
set -eu

: "${DATABASE_URL:?DATABASE_URL must be set}"

BACKUP_DIR="${1:-./backups}"
mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/leaveprints-$STAMP.dump"

case "$DATABASE_URL" in
  postgresql+psycopg://*)
    PG_URL="postgresql://${DATABASE_URL#postgresql+psycopg://}"
    ;;
  postgres://*)
    PG_URL="postgresql://${DATABASE_URL#postgres://}"
    ;;
  *)
    PG_URL="$DATABASE_URL"
    ;;
esac

echo "Writing PostgreSQL backup to $OUT"
pg_dump --format=custom --no-owner --no-privileges "$PG_URL" > "$OUT"
echo "Backup complete: $OUT"
