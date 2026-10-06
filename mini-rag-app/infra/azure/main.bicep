// MiniRAG on Azure Container Apps.
//
// Resources: Log Analytics, Container Registry, PostgreSQL Flexible Server (pgvector),
// Container Apps environment and one app:
//   minirag-api   FastAPI (public HTTPS)
// Monitoring uses the built-in Azure Monitor / Log Analytics (no Prometheus or Grafana, to keep costs low).
//
// Deployed by deploy.sh in two passes: deployApps=false creates the registry so the image
// can be built, then deployApps=true creates the container app.

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Create the container apps. False on the first pass, before images exist in the registry.')
param deployApps bool = true

@description('Image tag to deploy.')
param imageTag string = 'latest'

@description('PostgreSQL admin login. "postgres" is reserved on Azure.')
param postgresAdminUser string = 'minirag_admin'

@secure()
@description('PostgreSQL admin password (8+ chars, 3 of: upper, lower, digit, symbol).')
param postgresAdminPassword string

@description('Database the app uses (POSTGRES_MAIN_DATABASE).')
param postgresDatabaseName string = 'minirag'

param postgresVersion string = '17'
param postgresSkuName string = 'Standard_B1ms'
param postgresSkuTier string = 'Burstable'
param postgresStorageSizeGB int = 32

@description('Container env entries from .env.app, built by deploy.sh: {name, value} or {name, secretRef}.')
param appEnv array = []

@secure()
@description('Container app secrets from .env.app, built by deploy.sh: {name, value} (API keys etc.).')
param appSecrets object

@secure()
@description('Bearer token required for /metrics (keeps it private now that nginx is gone).')
param metricsToken string

param apiCpu string = '0.5'
param apiMemory string = '1Gi'
@description('0 = scale to zero when idle (cheapest; the first request after a pause takes ~10-30 s).')
param apiMinReplicas int = 0
param apiMaxReplicas int = 1

var suffix = uniqueString(resourceGroup().id)
var acrName = 'miniragacr${suffix}'
var postgresServerName = 'minirag-pg-${suffix}'

var apiAppName = 'minirag-api'

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'minirag-logs-${suffix}'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource pullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'minirag-acr-pull'
  location: location
}

var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, pullIdentity.id, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: pullIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: postgresServerName
  location: location
  sku: {
    name: postgresSkuName
    tier: postgresSkuTier
  }
  properties: {
    version: postgresVersion
    administratorLogin: postgresAdminUser
    administratorLoginPassword: postgresAdminPassword
    storage: {
      storageSizeGB: postgresStorageSizeGB
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
  }
}

// pgvector must be allow-listed before the app runs CREATE EXTENSION vector.
resource postgresExtensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgres
  name: 'azure.extensions'
  properties: {
    value: 'VECTOR'
    source: 'user-override'
  }
}

resource postgresDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: postgresDatabaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
  dependsOn: [
    postgresExtensions
  ]
}

// 0.0.0.0 = "allow Azure services"; Container Apps (consumption) has no fixed outbound IP.
resource postgresAllowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
  dependsOn: [
    postgresDatabase
  ]
}

resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'minirag-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

var registries = [
  {
    server: acr.properties.loginServer
    identity: pullIdentity.id
  }
]

var managedEnv = [
  { name: 'POSTGRES_HOST', value: postgres.properties.fullyQualifiedDomainName }
  { name: 'POSTGRES_PORT', value: '5432' }
  { name: 'POSTGRES_USERNAME', value: postgresAdminUser }
  { name: 'POSTGRES_PASSWORD', secretRef: 'postgres-password' }
  { name: 'POSTGRES_MAIN_DATABASE', value: postgresDatabaseName }
  { name: 'POSTGRES_SSL', value: 'true' }
  { name: 'METRICS_TOKEN', secretRef: 'metrics-token' }
]

var apiHealthProbe = {
  path: '/api/v1/healthy'
  port: 8000
}

resource apiApp 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: apiAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${pullIdentity.id}': {}
    }
  }
  properties: {
    environmentId: containerEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: registries
      secrets: concat(appSecrets.items, [
        { name: 'postgres-password', value: postgresAdminPassword }
        { name: 'metrics-token', value: metricsToken }
      ])
    }
    template: {
      containers: [
        {
          // Uploaded files live on the container disk only until they are processed into Postgres;
          // the environment type here (express) does not support Azure Files mounts.
          name: 'fastapi'
          image: '${acr.properties.loginServer}/minirag:${imageTag}'
          resources: {
            cpu: json(apiCpu)
            memory: apiMemory
          }
          env: concat(appEnv, managedEnv)
          probes: [
            {
              type: 'Startup'
              httpGet: apiHealthProbe
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 30
            }
            {
              type: 'Liveness'
              httpGet: apiHealthProbe
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: apiHealthProbe
              periodSeconds: 10
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: apiMinReplicas
        maxReplicas: apiMaxReplicas
      }
    }
  }
  dependsOn: [
    acrPull
    postgresAllowAzure
  ]
}

output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output postgresHost string = postgres.properties.fullyQualifiedDomainName
output postgresServerName string = postgres.name
output apiUrl string = deployApps ? 'https://${apiApp!.properties.configuration.ingress.fqdn}' : ''
