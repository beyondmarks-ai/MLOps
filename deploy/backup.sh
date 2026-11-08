#!/usr/bin/env bash
set -euo pipefail
cd /opt/churn-mlops
backup_dir=$(mktemp -d /tmp/churn-backup.XXXXXX)
trap 'rm -rf -- "$backup_dir"' EXIT
stamp=$(date -u +%Y%m%dT%H%M%SZ)
docker compose --env-file .env -f deploy/compose.azure.yml exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -u root --single-transaction --no-tablespaces churn' | gzip > "$backup_dir/mysql-$stamp.sql.gz"
docker compose --env-file .env -f deploy/compose.azure.yml exec -T postgres pg_dumpall -U airflow | gzip > "$backup_dir/postgres-$stamp.sql.gz"
chmod 755 "$backup_dir"
chmod 644 "$backup_dir"/*.gz
docker compose --env-file .env -f deploy/compose.azure.yml run --rm --no-deps -v "$backup_dir:/backup:ro" api python scripts/upload_backup.py
