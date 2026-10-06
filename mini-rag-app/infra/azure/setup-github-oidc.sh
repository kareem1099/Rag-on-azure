#!/usr/bin/env bash
# One-time setup: lets the GitHub Actions workflow log in to Azure without stored passwords
# (OpenID Connect federated credential), with Contributor access on the MiniRAG resource group only.
#
# Usage:
#   ./setup-github-oidc.sh <resource-group> [owner/repo] [branch]
set -euo pipefail

RESOURCE_GROUP="${1:?usage: setup-github-oidc.sh <resource-group> [owner/repo] [branch]}"
REPO="${2:-kareem1099/rag-on-azure}"
BRANCH="${3:-main}"
APP_NAME="minirag-github-deploy"

SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
TENANT_ID="$(az account show --query tenantId -o tsv)"
RG_ID="$(az group show --name "$RESOURCE_GROUP" --query id -o tsv)"

CLIENT_ID="$(az ad app list --display-name "$APP_NAME" --query '[0].appId' -o tsv)"
if [[ -z "$CLIENT_ID" ]]; then
    CLIENT_ID="$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)"
fi
az ad sp show --id "$CLIENT_ID" >/dev/null 2>&1 || az ad sp create --id "$CLIENT_ID" -o none

CREDENTIAL_NAME="github-${BRANCH//[^A-Za-z0-9-]/-}"
if ! az ad app federated-credential list --id "$CLIENT_ID" --query "[?name=='$CREDENTIAL_NAME']" -o tsv | grep -q .; then
    az ad app federated-credential create --id "$CLIENT_ID" --parameters "{
        \"name\": \"$CREDENTIAL_NAME\",
        \"issuer\": \"https://token.actions.githubusercontent.com\",
        \"subject\": \"repo:$REPO:ref:refs/heads/$BRANCH\",
        \"audiences\": [\"api://AzureADTokenExchange\"]
    }" -o none
fi

az role assignment create --assignee "$CLIENT_ID" --role Contributor --scope "$RG_ID" -o none

cat <<EOF

Add these in GitHub -> $REPO -> Settings -> Secrets and variables -> Actions

Secrets:
  AZURE_CLIENT_ID       = $CLIENT_ID
  AZURE_TENANT_ID       = $TENANT_ID
  AZURE_SUBSCRIPTION_ID = $SUBSCRIPTION_ID

Variables:
  AZURE_RESOURCE_GROUP  = $RESOURCE_GROUP
  AZURE_ACR_NAME        = <printed at the end of deploy.sh>
  AZURE_DEPLOY_ENABLED  = true    (turns on deploy-on-push)
EOF
