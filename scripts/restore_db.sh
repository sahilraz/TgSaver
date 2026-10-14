#!/usr/bin/env bash
# Database Restore Script for TgSaverBot
set -euo pipefail

if [ -z "${1:-}" ]; then
    echo "Usage: $0 /path/to/backup.sql.gz"
    exit 1
fi

BACKUP_FILE="$1"
if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file $BACKUP_FILE does not exist."
    exit 1
fi

echo "Restoring database from $BACKUP_FILE..."
gunzip -c "$BACKUP_FILE" | psql -U tgsaver tgsaver
echo "Database restored successfully."
