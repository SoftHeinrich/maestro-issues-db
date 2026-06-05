#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MAESTRO_ROOT="${MAESTRO_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
ENV_FILE="${ENV_FILE:-$MAESTRO_ROOT/.env}"
BACKUP_DIR="${EXPERIMENT_RATINGS_BACKUP_DIR:-$MAESTRO_ROOT/backups/experiment-ratings}"
RETENTION_DAYS="${EXPERIMENT_RATINGS_BACKUP_RETENTION_DAYS:-60}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-psql}"
TABLE_NAME="${EXPERIMENT_RATINGS_TABLE:-public.experiment_ratings}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

POSTGRES_DB="${POSTGRES_DB:-issues}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-pass}"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_name="experiment_ratings_${timestamp}.dump"
backup_path="$BACKUP_DIR/$backup_name"
tmp_path="$BACKUP_DIR/.$backup_name.tmp"
metadata_path="$backup_path.meta"

cleanup() {
  rm -f "$tmp_path"
}
trap cleanup EXIT

row_count="$(
  docker exec \
    -e PGPASSWORD="$POSTGRES_PASSWORD" \
    "$POSTGRES_CONTAINER" \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At \
    -c "SELECT COUNT(*) FROM $TABLE_NAME;"
)"

docker exec \
  -e PGPASSWORD="$POSTGRES_PASSWORD" \
  "$POSTGRES_CONTAINER" \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --format=custom \
    --table="$TABLE_NAME" \
    --no-owner \
    --no-acl \
  > "$tmp_path"

mv "$tmp_path" "$backup_path"
sha256sum "$backup_path" > "$backup_path.sha256"

cat > "$metadata_path" <<EOF
created_at_utc=$timestamp
postgres_container=$POSTGRES_CONTAINER
postgres_db=$POSTGRES_DB
table=$TABLE_NAME
row_count=$row_count
backup_file=$backup_name
EOF

ln -sfn "$backup_name" "$BACKUP_DIR/latest.dump"
ln -sfn "$(basename "$metadata_path")" "$BACKUP_DIR/latest.meta"

find "$BACKUP_DIR" -type f \( \
    -name 'experiment_ratings_*.dump' -o \
    -name 'experiment_ratings_*.dump.sha256' -o \
    -name 'experiment_ratings_*.dump.meta' \
  \) -mtime +"$RETENTION_DAYS" -delete

echo "Backed up $TABLE_NAME ($row_count rows) to $backup_path"
