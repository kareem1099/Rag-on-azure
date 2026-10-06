// MiniRAG on Azure Container Apps.
//
// Resources: Log Analytics, Container Registry, PostgreSQL Flexible Server (pgvector),
// Storage (Azure Files for uploaded assets), Container Apps environment and three apps:
//   minirag-api         FastAPI (public HTTPS)
//   minirag-prometheus  Prometheus (internal only)
//   minirag-grafana     Grafana (public HTTPS)
//
// Deployed by deploy.sh in two passes: deployApps=false creates the registry so images
// can be built, then deployApps=true creates the container apps.

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Create the container apps. False on the first pass, before images exist in the registry.')
param deployApps bool = true

@description('Image tag to deploy for all three images.')
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

@description('Non-secret app settings from .env.app (POSTGRES_* connection keys are set here and ignored if present).')
param appEnv object = {}

@secure()
@description('Secret app settings from .env.app, e.g. GEMINI_API_KEY, COHERE_API_KEY, APP_API_KEY.')
param appSecrets object = {}

@secure()
@description('Bearer token Prometheus uses to scrape /metrics.')
param metricsToken string

param grafanaAdminUser string = 'admin'

@secure()
param grafanaAdminPassword string

param apiCpu string = '1.0'
param apiMemory string = '2Gi'
param apiMinReplicas int = 1
param apiMaxReplicas int = 1

var suffix = uniqueString(resourceGroup().id)
var acrName = 'miniragacr${suffix}'
var storageName = 'miniragst${take(suffix, 13)}'
var postgresServerName = 'minirag-pg-${suffix}'
var assetsShareName = 'minirag-assets'

var apiAppName = 'minirag-api'
var prometheusAppName = 'minirag-prometheus'
var grafanaAppName = 'minirag-grafana'

// Keys owned by this template; values for them in appEnv/appSecrets are dropped.
var managedKeys = [
  'POSTGRES_HOST'
  'POSTGRES_PORT'
  'POSTGRES_USERNAME'
  'POSTGRES_PASSWORD'
  'POSTGRES_MAIN_DATABASE'
  'POSTGRES_SSL'
  'METRICS_TOKEN'
]

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

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource assetsShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: assetsShareName
  properties: {
    shareQuota: 20
  }
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

resource assetsStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: containerEnv
  name: 'assets'
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: assetsShare.name
      accessMode: 'ReadWrite'
    }
  }
}

var registries = [
  {
    server: acr.properties.loginServer
    identity: pullIdentity.id
  }
]

var plainEnv = [for item in filter(items(appEnv), i => !contains(managedKeys, i.key)): {
  name: item.key
  value: string(item.value)
}]

var userSecrets = filter(items(appSecrets), i => !contains(managedKeys, i.key) && !empty(i.value))

var userSecretValues = [for item in userSecrets: {
  name: toLower(replace(item.key, '_', '-'))
  value: item.value
}]

var userSecretEnv = [for item in userSecrets: {
  name: item.key
  secretRef: toLower(replace(item.key, '_', '-'))
}]

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
      secrets: concat(userSecretValues, [
        { name: 'postgres-password', value: postgresAdminPassword }
        { name: 'metrics-token', value: metricsToken }
      ])
    }
    template: {
      containers: [
        {
          name: 'fastapi'
          image: '${acr.properties.loginServer}/minirag:${imageTag}'
          resources: {
            cpu: json(apiCpu)
            memory: apiMemory
          }
          env: concat(plainEnv, userSecretEnv, managedEnv)
          volumeMounts: [
            {
              volumeName: 'assets'
              mountPath: '/app/assets'
            }
          ]
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
      volumes: [
        {
          name: 'assets'
          storageType: 'AzureFile'
          storageName: assetsStorage.name
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

resource prometheusApp 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: prometheusAppName
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
        external: false
        targetPort: 9090
        transport: 'http'
        allowInsecure: true
      }
      registries: registries
      secrets: [
        { name: 'metrics-token', value: metricsToken }
      ]
    }
    template: {
      containers: [
        {
          name: 'prometheus'
          image: '${acr.properties.loginServer}/minirag-prometheus:${imageTag}'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'FASTAPI_HOST', value: apiApp!.properties.configuration.ingress.fqdn }
          ]
          volumeMounts: [
            {
              volumeName: 'secrets'
              mountPath: '/etc/prometheus/secrets'
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'secrets'
          storageType: 'Secret'
          secrets: [
            { secretRef: 'metrics-token', path: 'metrics-token' }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
  dependsOn: [
    acrPull
  ]
}

resource grafanaApp 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: grafanaAppName
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
        targetPort: 3000
        transport: 'auto'
        allowInsecure: false
      }
      registries: registries
      secrets: [
        { name: 'grafana-admin-password', value: grafanaAdminPassword }
      ]
    }
    template: {
      containers: [
        {
          name: 'grafana'
          image: '${acr.properties.loginServer}/minirag-grafana:${imageTag}'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'GF_SECURITY_ADMIN_USER', value: grafanaAdminUser }
            { name: 'GF_SECURITY_ADMIN_PASSWORD', secretRef: 'grafana-admin-password' }
            { name: 'GF_USERS_ALLOW_SIGN_UP', value: 'false' }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
  dependsOn: [
    acrPull
    prometheusApp
  ]
}

output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output postgresHost string = postgres.properties.fullyQualifiedDomainName
output postgresServerName string = postgres.name
output storageAccountName string = storage.name
output assetsShareName string = assetsShare.name
output apiUrl string = deployApps ? 'https://${apiApp!.properties.configuration.ingress.fqdn}' : ''
output grafanaUrl string = deployApps ? 'https://${grafanaApp!.properties.configuration.ingress.fqdn}' : ''
