targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment that can be used as part of naming resource convention')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('Name of the container app')
param mcpServerContainerAppName string = ''

@description('Name of the container apps environment')
param containerAppsEnvironmentName string = ''

@description('Name of the container registry')
param containerRegistryName string = ''

@description('Name of the log analytics workspace')
param logAnalyticsName string = ''

@description('Name of the resource group')
param resourceGroupName string = ''

@description('Container image name (set by azd deploy)')
param mcpServerImageName string = ''

var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = { 'azd-env-name': environmentName }

// Organize resources in a resource group
resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: !empty(resourceGroupName) ? resourceGroupName : '${abbrs.resourcesResourceGroups}${environmentName}'
  location: location
  tags: tags
}

// Log Analytics workspace
module logAnalytics './modules/log-analytics.bicep' = {
  name: 'log-analytics'
  scope: rg
  params: {
    name: !empty(logAnalyticsName) ? logAnalyticsName : '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
    location: location
    tags: tags
  }
}

// Container Registry
module containerRegistry './modules/container-registry.bicep' = {
  name: 'container-registry'
  scope: rg
  params: {
    name: !empty(containerRegistryName) ? containerRegistryName : '${abbrs.containerRegistryRegistries}${resourceToken}'
    location: location
    tags: tags
  }
}

// Container Apps Environment
module containerAppsEnvironment './modules/container-apps-environment.bicep' = {
  name: 'container-apps-environment'
  scope: rg
  params: {
    name: !empty(containerAppsEnvironmentName) ? containerAppsEnvironmentName : '${abbrs.appManagedEnvironments}${resourceToken}'
    location: location
    tags: tags
    logAnalyticsWorkspaceName: logAnalytics.outputs.name
  }
}

// MCP Server Container App
module mcpServer './modules/container-app.bicep' = {
  name: 'mcp-server'
  scope: rg
  params: {
    name: !empty(mcpServerContainerAppName) ? mcpServerContainerAppName : '${abbrs.appContainerApps}mcp-${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'mcp-server' })
    containerAppsEnvironmentName: containerAppsEnvironment.outputs.name
    containerRegistryName: containerRegistry.outputs.name
    imageName: mcpServerImageName
    targetPort: 8000
    env: [
      {
        name: 'TRANSPORT'
        value: 'all'
      }
      {
        name: 'HOST'
        value: '0.0.0.0'
      }
      {
        name: 'PORT'
        value: '8000'
      }
    ]
  }
}

output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerRegistry.outputs.loginServer
output AZURE_CONTAINER_REGISTRY_NAME string = containerRegistry.outputs.name
output MCP_SERVER_URI string = mcpServer.outputs.uri
output MCP_SERVER_STREAMABLE_HTTP_ENDPOINT string = '${mcpServer.outputs.uri}mcp'
output MCP_SERVER_SSE_ENDPOINT string = '${mcpServer.outputs.uri}sse'
output MCP_SERVER_TEST_UI string = mcpServer.outputs.uri
