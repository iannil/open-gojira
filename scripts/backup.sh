#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Gojira Database Backup Script
#
# Usage:
#   ./backup.sh [BACKUP_DIR]
#
# Arguments:
#   BACKUP_DIR  Directory to store backups (default: ./backups)
#
# Environment variables (for PostgreSQL):
#   PGHOST       PostgreSQL host (default: postgres)
#   PGPORT       PostgreSQL port (default: 5432)
#   POSTGRES_DB  Database name (default: gojira)
#   POSTGRES_USER Database user (default: gojira)
#   KEEP_BACKUPS Number of backups to retain (default: 30)
#
# Supports both SQLite and PostgreSQL:
#   - Detects database type from DATABASE_URL or falls back to PG variables.
#   - SQLite: uses sqlite3 .backup command.
#   - PostgreSQL: uses pg_dump.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

BACKUP_DIR="${1:-./backups}"
KEEP_BACKUPS="${KEEP_BACKUPS:-30}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# PostgreSQL defaults
PGHOST="${PGHOST:-postgres}"
PGPORT="${PGPORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-gojira}"
POSTGRES_USER="${POSTGRES_USER:-gojira}"

# ── Ensure backup directory exists ──────────────────────────────────────────
mkdir -p "$BACKUP_DIR"

echo "=== Gojira Database Backup ==="
echo "  Timestamp : $TIMESTAMP"
echo "  Target    : $BACKUP_DIR"
echo ""

# ── Determine database type ────────────────────────────────────────────────
DATABASE_URL="${DATABASE_URL:-}"

if [[ "$DATABASE_URL" == postgres* ]]; then
    # ── PostgreSQL Backup ───────────────────────────────────────────────────
    echo "[PostgreSQL] Starting backup..."

    # Extract connection info from DATABASE_URL if set
    if [[ -n "$DATABASE_URL" ]]; then
        # Parse postgresql+psycopg2://user:pass@host:port/dbname
        DB_PART="${DATABASE_URL#*://}"
        CREDENTIALS="${DB_PART%%@*}"
        DB_USER="${CREDENTIALS%%:*}"
        REST="${DB_PART#*@}"
        DB_HOST_PORT="${REST%%/*}"
        DB_NAME="${REST#*/}"

        # Export for pg_dump
        export PGHOST="${DB_HOST_PORT%%:*}"
        export PGPORT="${DB_HOST_PORT##*:}"
        export PGUSER="$DB_USER"
        export PGDATABASE="$DB_NAME"
    fi

    BACKUP_FILE="$BACKUP_DIR/gojira_${TIMESTAMP}.sql.gz"

    PGPASSWORD="${POSTGRES_PASSWORD:-}" pg_dump \
        -h "$PGHOST" \
        -p "$PGPORT" \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        --no-owner \
        --no-privileges \
        --clean \
        --if-exists \
        | gzip > "$BACKUP_FILE"

    echo "[PostgreSQL] Backup completed: $BACKUP_FILE"
    echo "[PostgreSQL] Size: $(du -h "$BACKUP_FILE" | cut -f1)"

elif [[ "$DATABASE_URL" == sqlite* ]] || [[ -z "$DATABASE_URL" ]]; then
    # ── SQLite Backup ───────────────────────────────────────────────────────
    echo "[SQLite] Starting backup..."

    # Resolve SQLite database path
    if [[ -n "$DATABASE_URL" ]]; then
        # Strip sqlite:/// prefix
        DB_PATH="${DATABASE_URL#sqlite:///}"
    else
        DB_PATH="data/gojira.db"
    fi

    if [[ ! -f "$DB_PATH" ]]; then
        echo "[ERROR] SQLite database not found at: $DB_PATH"
        exit 1
    fi

    BACKUP_FILE="$BACKUP_DIR/gojira_${TIMESTAMP}.db"

    sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

    if command -v gzip &>/dev/null; then
        gzip "$BACKUP_FILE"
        BACKUP_FILE="${BACKUP_FILE}.gz"
    fi

    echo "[SQLite] Backup completed: $BACKUP_FILE"
    echo "[SQLite] Size: $(du -h "$BACKUP_FILE" | cut -f1)"

else
    echo "[ERROR] Unsupported DATABASE_URL scheme: $DATABASE_URL"
    exit 1
fi

# ── Cleanup old backups ────────────────────────────────────────────────────
echo ""
echo "[Cleanup] Retaining last $KEEP_BACKUPS backups..."

# Count and remove excess backups (sorted by modification time, oldest first)
TOTAL=$(find "$BACKUP_DIR" -name "gojira_*" -type f | wc -l | tr -d ' ')

if [[ "$TOTAL" -gt "$KEEP_BACKUPS" ]]; then
    REMOVE_COUNT=$((TOTAL - KEEP_BACKUPS))
    find "$BACKUP_DIR" -name "gojira_*" -type f -printf '%T+ %p\n' \
        | sort \
        | head -n "$REMOVE_COUNT" \
        | awk '{print $2}' \
        | xargs rm -f
    echo "[Cleanup] Removed $REMOVE_COUNT old backup(s)."
else
    echo "[Cleanup] Only $TOTAL backup(s) found, no cleanup needed."
fi

echo ""
echo "=== Backup Complete ==="
