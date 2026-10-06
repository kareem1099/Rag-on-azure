#!/usr/bin/env bash
# Provision (or update) the whole MiniRAG stack on Azure Container Apps.
#
# Usage:
#   ./deploy.sh <resource-group> [location]
#
# Reads settings from ../../docker/env/.env.app (the same file the docker compose
# setup uses; override with ENV_DIR=...). Safe to re-run: it rebuilds the image
# and re-applies main.bicep. Day-to-day code deploys go through the
# GitHub Actions workflow instead (.github/workflows/deploy-azure.yml).
set -euo pipefail

RESOURCE_GROUP="${1:?usage: deploy.sh <resource-group> [location]}"
LOCATION="${2:-westeurope}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_DIR="${ENV_DIR:-$APP_DIR/docker/env}"
IMAGE_TAG="${IMAGE_TAG:-$(git -C "$APP_DIR" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)}"

[[ -f "$ENV_DIR/.env.app" ]] || { echo "Missing $ENV_DIR/.env.app (copy it from .env.example.app and fill it in)"; exit 1; }

command -v az >/dev/null || { echo "Azure CLI (az) is required: https://aka.ms/azure-cli"; exit 1; }
az account show >/dev/null || { echo "Run 'az login' first"; exit 1; }

PARAMS_FILE="$(mktemp)"
trap 'rm -f "$PARAMS_FILE"' EXIT

# Builds the ARM parameters file from the env files. Keys ending in _KEY/_PASSWORD/_TOKEN/_SECRET
# become container app secrets; everything else is a plain env var.
build_params() {
    local deploy_apps="$1"
    python3 - "$ENV_DIR" "$deploy_apps" "$IMAGE_TAG" "$LOCATION" > "$PARAMS_FILE" <<'PY'
import json, re, secrets, sys

env_dir, deploy_apps, image_tag, location = sys.argv[1:5]


def read_env(path):
    values = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


app = read_env(f"{env_dir}/.env.app")

# Set by main.bicep from the Azure resources; ignored if present in .env.app.
managed_keys = {"POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USERNAME", "POSTGRES_PASSWORD",
                "POSTGRES_MAIN_DATABASE", "POSTGRES_SSL", "METRICS_TOKEN"}
secret_pattern = re.compile(r"_(KEY|PASSWORD|TOKEN|SECRET)$")

# The env/secret arrays are built here rather than with Bicep loops: ARM re-evaluates loop
# output that starts with "[" (e.g. FILE_ALLOWED_EXTENSIONS) as a template expression.
app_env, app_secrets = [], []
for key, value in app.items():
    if key in managed_keys:
        continue
    if secret_pattern.search(key):
        if value:
            secret_name = key.lower().replace("_", "-")
            app_secrets.append({"name": secret_name, "value": value})
            app_env.append({"name": key, "secretRef": secret_name})
    else:
        app_env.append({"name": key, "value": value})

params = {
    "location": location,
    "deployApps": deploy_apps == "true",
    "imageTag": image_tag,
    "postgresAdminPassword": app["POSTGRES_PASSWORD"],
    "postgresDatabaseName": app.get("POSTGRES_MAIN_DATABASE", "minirag"),
    "appEnv": app_env,
    "appSecrets": {"items": app_secrets},
    "metricsToken": app.get("METRICS_TOKEN") or secrets.token_hex(32),
}

print(json.dumps({
    "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
    "contentVersion": "1.0.0.0",
    "parameters": {k: {"value": v} for k, v in params.items()},
}))
PY
}

deploy() {
    az deployment group create \
        --resource-group "$RESOURCE_GROUP" \
        --name "minirag-$(date +%Y%m%d%H%M%S)" \
        --template-file "$SCRIPT_DIR/main.bicep" \
        --parameters "@$PARAMS_FILE" \
        --query "properties.outputs" -o json
}

# Reads one output of the last deployment.
output() { python3 -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]]["value"])' "$1" <<<"$OUTPUTS"; }

echo "==> Resource group $RESOURCE_GROUP ($LOCATION)"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" -o none

echo "==> Base infrastructure (registry, PostgreSQL, storage, environment)"
build_params false
OUTPUTS="$(deploy)"
ACR_NAME="$(output acrName)"

echo "==> Building image in $ACR_NAME with tag $IMAGE_TAG"
az acr build -r "$ACR_NAME" -t "minirag:$IMAGE_TAG" -f "$APP_DIR/docker/minirag/Dockerfile" "$APP_DIR"

echo "==> Container app"
build_params true
OUTPUTS="$(deploy)"

cat <<EOF

Done.
  API:      $(output apiUrl)/api/v1/healthy
  Postgres: $(output postgresHost)

For GitHub Actions set these repository variables:
  AZURE_RESOURCE_GROUP = $RESOURCE_GROUP
  AZURE_ACR_NAME       = $(output acrName)
EOF
