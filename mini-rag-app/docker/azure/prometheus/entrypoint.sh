#!/bin/sh
set -e

: "${FASTAPI_HOST:?FASTAPI_HOST is required (the FastAPI container app FQDN)}"

sed "s|__FASTAPI_HOST__|${FASTAPI_HOST}|g" /etc/prometheus/prometheus.yml.tmpl > /tmp/prometheus.yml

exec /bin/prometheus \
    --config.file=/tmp/prometheus.yml \
    --storage.tsdb.path=/prometheus \
    --storage.tsdb.retention.time="${PROMETHEUS_RETENTION:-15d}" \
    --web.enable-lifecycle \
    "$@"
