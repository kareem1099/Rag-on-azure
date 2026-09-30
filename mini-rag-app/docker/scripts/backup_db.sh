#!/bin/bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
KEEP_DAYS="${KEEP_DAYS:-7}"
STAMP=$(date +%Y%m%d_%H%M%S)
TARGET="$BACKUP_DIR/minirag_$STAMP.dump"

mkdir -p "$BACKUP_DIR"

docker exec pgvector pg_dump -U postgres -d minirag -Fc --no-owner --no-privileges > "$TARGET.tmp"
mv "$TARGET.tmp" "$TARGET"

find "$BACKUP_DIR" -name "minirag_*.dump" -mtime +"$KEEP_DAYS" -delete

echo "$(date -Is) backup ok: $TARGET ($(du -h "$TARGET" | cut -f1))"
