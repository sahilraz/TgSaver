#!/usr/bin/env bash
# Database Backup Script for TgSaverBot
set -euo pipefail

BACKUP_DIR="/var/backups/tgsaver"
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/tgsaver_db_$TIMESTAMP.sql.gz"

echo "Backing up database to $BACKUP_FILE..."
pg_dump -U tgsaver tgsaver | gzip > "$BACKUP_FILE"

# Keep last 14 days of backups
find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime +14 -delete
echo "Backup completed successfully."
