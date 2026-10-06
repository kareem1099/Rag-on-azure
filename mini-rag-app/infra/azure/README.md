# Deploying MiniRAG to Azure Container Apps

```
  users ── HTTPS ──▶  minirag-api (FastAPI, Container Apps, scales to zero)
                          │ SSL                      │
          PostgreSQL Flexible Server (pgvector)   Azure Files: /app/assets
```

| Old (VM / docker compose) | Azure |
|---|---|
| `fastapi` + `nginx` | `minirag-api` Container App (HTTPS ingress replaces nginx) |
| `pgvector` container | Azure Database for PostgreSQL Flexible Server, `VECTOR` extension enabled |
| `fastapi_data` volume | Azure Files share `minirag-assets` mounted at `/app/assets` |
| `prometheus`, `grafana`, exporters, `cloudflared` | dropped to save credit: use the app's **Monitoring** blades (Azure Monitor / Log Analytics) |
| self-hosted runner (`deploy.yml`) | GitHub-hosted runner + OIDC login (`deploy-azure.yml`) |

Why Postgres is a separate (billed) service here: on the VM the database container shared the machine
you already paid for. Container Apps has no shared disk that is safe for a database, so the data lives
in a managed server. `Standard_B1ms` with 32 GB is part of the 12-month free services on
Azure free / Azure for Students accounts; check *Free services* in the portal.

## 1. One-time provisioning

Needs the [Azure CLI](https://aka.ms/azure-cli) and an account with **Owner** (or Contributor +
User Access Administrator) on the subscription, because the template assigns `AcrPull` to a managed identity.

```bash
az login
az account set --subscription "<subscription name or id>"

cd mini-rag-app
# Uses the same env file as docker compose:
#   docker/env/.env.app  (API keys, model settings, POSTGRES_PASSWORD)
./infra/azure/deploy.sh minirag-rg westeurope
```

Notes:
- `POSTGRES_PASSWORD` becomes the Azure Postgres admin password; Azure requires 8+ characters with
  three of: upper case, lower case, digit, symbol. The admin user is `minirag_admin` (`postgres` is reserved),
  `POSTGRES_HOST` / `POSTGRES_USERNAME` / `POSTGRES_SSL` from `.env.app` are overridden automatically.
- Keys ending in `_KEY`, `_PASSWORD`, `_TOKEN`, `_SECRET` are stored as Container App secrets.
- Re-run the script any time you change `.env.app`; it is idempotent.
- Default size is Postgres `Standard_B1ms` and the API at 0.5 vCPU / 1 GiB with **scale to zero**:
  no cost while idle, but the first request after a quiet period takes ~10-30 s. Set `apiMinReplicas`
  to 1 in `main.bicep` to keep it warm (costs more).

At the end it prints the API URL and the ACR name.

## 2. Move the data from the VM (optional)

On the VM:

```bash
cd ~/workspace/mini-rag/mini-rag-app/docker
docker compose exec -T pgvector pg_dump -U postgres -Fc minirag > minirag.dump
```

Allow your IP on the Azure server, then restore (needs `pg_restore` 17):

```bash
PG_SERVER=$(az postgres flexible-server list -g minirag-rg --query '[0].name' -o tsv)
az postgres flexible-server firewall-rule create -g minirag-rg -n "$PG_SERVER" \
  --rule-name migrate --start-ip-address <your-ip> --end-ip-address <your-ip>

pg_restore --no-owner --no-acl --clean --if-exists \
  -d "host=$PG_SERVER.postgres.database.azure.com user=minirag_admin dbname=minirag sslmode=require" \
  minirag.dump

az postgres flexible-server firewall-rule delete -g minirag-rg -n "$PG_SERVER" --rule-name migrate --yes
```

Uploaded files (`/app/assets`) go to the file share:

```bash
docker run --rm -v docker_fastapi_data:/data -v "$PWD":/out alpine tar czf /out/assets.tgz -C /data .
mkdir assets && tar xzf assets.tgz -C assets
ST=$(az storage account list -g minirag-rg --query '[0].name' -o tsv)
az storage file upload-batch --account-name "$ST" -d minirag-assets -s assets
az containerapp revision restart -g minirag-rg -n minirag-api \
  --revision $(az containerapp revision list -g minirag-rg -n minirag-api --query '[0].name' -o tsv)
```

## 3. Deploy on every push (GitHub Actions)

```bash
./infra/azure/setup-github-oidc.sh minirag-rg kareem1099/alla-basera DALEL-EL-SHAB-ELMOSLEM
```

Then in GitHub → Settings → Secrets and variables → Actions add the secrets
`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` and the variables
`AZURE_RESOURCE_GROUP`, `AZURE_ACR_NAME`, `AZURE_DEPLOY_ENABLED=true`.

With `AZURE_DEPLOY_ENABLED=true`, pushes to `DALEL-EL-SHAB-ELMOSLEM` run `deploy-azure.yml`
(build the image in ACR, roll out a new revision, health check) and the old self-hosted
`deploy.yml` is skipped. Delete the variable to switch back to the VM.

## Good to know

- Requests through Container Apps ingress time out after **240 s** (nginx had 300 s).
- `/metrics` still exists but needs `Authorization: Bearer <METRICS_TOKEN>`; nothing scrapes it on Azure.
- Set a budget alert (Cost Management → Budgets) so you hear about spending before the credit runs out.
- Postgres accepts connections from Azure services (`0.0.0.0` firewall rule) with SSL and the admin
  password. For stricter isolation, move the environment and the server into a VNet with private access.
- Logs: `az containerapp logs show -g minirag-rg -n minirag-api --follow`, or Log Analytics in the portal.
