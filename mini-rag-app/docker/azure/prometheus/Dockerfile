FROM prom/prometheus:v3.3.0

COPY docker/azure/prometheus/prometheus.yml.tmpl /etc/prometheus/prometheus.yml.tmpl
COPY docker/azure/prometheus/entrypoint.sh /etc/prometheus/entrypoint.sh

ENTRYPOINT ["/bin/sh", "/etc/prometheus/entrypoint.sh"]
