#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then exec /bin/bash "$0" "$@"; fi
set -euo pipefail
cd /opt/churn-mlops
work=$(mktemp -d /tmp/churn-release.XXXXXX)
trap 'rm -rf -- "$work"' EXIT
curl --fail --location --proto '=https' --retry 3 \
    'https://github.com/beyondmarks-ai/MLOps/archive/__COMMIT__.tar.gz' -o "$work/release.tar.gz"
chown mlops:mlops "$work" "$work/release.tar.gz"
runuser -u mlops -- tar -xzf "$work/release.tar.gz" --strip-components=1 -C /opt/churn-mlops
compose=(docker compose --env-file .env -f deploy/compose.azure.yml)
if ! "${compose[@]}" build > "$work/build.log" 2>&1; then
    tail -n 60 "$work/build.log"
    exit 1
fi
"${compose[@]}" up -d --wait --wait-timeout 300
for service in api api2; do
    "${compose[@]}" exec -T "$service" curl --fail --silent --show-error \
        --retry 60 --retry-delay 2 --retry-all-errors --max-time 5 \
        http://localhost:8000/health
done
printf '%s\n' '__COMMIT__' > .deployed-commit
printf '\nCHURN_DEPLOYED___COMMIT__\n'
