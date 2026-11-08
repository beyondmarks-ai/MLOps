#!/usr/bin/env bash
set -euo pipefail
cd /opt/churn-mlops
work=$(mktemp -d /tmp/churn-restore.XXXXXX)
database="churn_restore_${RANDOM}_${RANDOM}"
created=0
compose=(docker compose --env-file .env -f deploy/compose.azure.yml)
mysql() { "${compose[@]}" exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -u root "$@"' sh "$@"; }
cleanup() {
    if [ "$created" = 1 ]; then mysql -e "DROP DATABASE $database"; fi
    rm -rf -- "$work"
}
trap cleanup EXIT
"${compose[@]}" run --rm --no-deps --user 0:0 -v "$work:/restore" -v /opt/churn-mlops/scripts/download_backup.py:/app/scripts/download_backup.py:ro api python scripts/download_backup.py
mysql -e "CREATE DATABASE $database"
created=1
mysql "$database" < "$work/mysql.sql"
count=$(mysql -N -e "SELECT COUNT(*) FROM $database.samples")
test "$count" -gt 0
printf 'Verified isolated restore: %s training samples; live database untouched.\n' "$count"
