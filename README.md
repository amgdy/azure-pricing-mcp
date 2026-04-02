# Azure Pricing MCP Server 💰

A [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server for querying **Azure retail pricing** data. Comes with a built-in test UI, supports remote deployment via Streamable HTTP and SSE, and can be deployed to Azure Container Apps with a single command.

## Quick Start

```bash
pip install -r requirements.txt
python azure_pricing_server.py --transport all
```

Open **http://localhost:8000/** for the test UI or point your MCP client to `http://localhost:8000/mcp`.

## Endpoints

| Path | Purpose |
|------|---------|
| `/` | Test UI — browser-based tool runner |
| `/mcp` | Streamable HTTP transport (recommended for MCP clients) |
| `/sse` | SSE transport (legacy MCP clients) |

When using a single transport (`--transport streamable-http`), the MCP endpoint is at `/mcp`.

## Tools

| Tool | Description |
|------|-------------|
| `azure_price_search` | Search retail prices with service, region, SKU, and price-type filters |
| `azure_price_compare` | Compare prices across regions or SKUs |
| `azure_cost_estimate` | Estimate hourly/daily/monthly/yearly costs with savings-plan info |
| `azure_discover_skus` | List available SKUs for a service |
| `azure_sku_discovery` | Fuzzy service-name matching (e.g. "vm" → Virtual Machines) |
| `get_customer_discount` | Retrieve the default customer discount percentage |

## Client Configuration

### VS Code / GitHub Copilot (remote)

```json
{
  "mcp": {
    "servers": {
      "azure-pricing": {
        "url": "http://localhost:8000/mcp"
      }
    }
  }
}
```

### Claude Desktop (remote)

```json
{
  "mcpServers": {
    "azure-pricing": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Claude Desktop (local — stdio)

```json
{
  "mcpServers": {
    "azure-pricing": {
      "command": "python",
      "args": ["azure_pricing_server.py", "--transport", "stdio"]
    }
  }
}
```

## CLI Options

```
python azure_pricing_server.py [OPTIONS]

  --transport {stdio,sse,streamable-http,all}   (default: streamable-http)
  --host HOST                                    (default: 127.0.0.1)
  --port PORT                                    (default: 8000)
```

Use `--transport all` to serve the test UI, Streamable HTTP, and SSE on the same port.

## Docker

```bash
docker build -t azure-pricing-mcp .
docker run -p 8000:8000 azure-pricing-mcp
```

Open **http://localhost:8000/** for the test UI.

## Deploy to Azure

Requires the [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) and Docker.

```bash
azd auth login
azd up
```

`azd up` provisions an Azure Container Apps environment, builds the image, and deploys it. After deployment, the CLI prints the live endpoints:

```
MCP_SERVER_STREAMABLE_HTTP_ENDPOINT = https://<app>.azurecontainerapps.io/mcp
MCP_SERVER_SSE_ENDPOINT             = https://<app>.azurecontainerapps.io/sse
MCP_SERVER_TEST_UI                  = https://<app>.azurecontainerapps.io/
```

### DNS Rebinding Protection

The MCP SDK validates `Host` headers by default. This server **disables** the check so it works behind reverse proxies and cloud platforms. To re-enable it with an explicit allow-list:

```bash
docker run -p 8000:8000 \
  -e MCP_ALLOWED_HOSTS="myapp.azurecontainerapps.io,localhost:8000" \
  azure-pricing-mcp
```

## Project Structure

```
├── azure_pricing_server.py   # MCP server (tools + transport setup)
├── static/index.html          # Test UI (single-page app)
├── requirements.txt
├── Dockerfile
├── azure.yaml                 # azd service definition
├── infra/                     # Bicep templates for Azure deployment
│   ├── main.bicep
│   └── modules/
├── .devcontainer/             # Codespaces / Dev Container config
├── __main__.py                # python -m entry point
└── __init__.py
```

## API

This server queries the public [Azure Retail Prices API](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices) (`2023-01-01-preview`). No authentication is required.

## License

MIT
