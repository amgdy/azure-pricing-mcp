# Azure Pricing MCP Server 💰

A Model Context Protocol (MCP) server that provides tools for querying Azure retail pricing information using the Azure Retail Prices API. Supports **remote access** via Streamable HTTP, SSE, and stdio transports.

## 🚀 Quick Start

1. **Clone/Download** this repository
2. **Install dependencies**: `pip install -r requirements.txt`
3. **Start the server**:
   ```bash
   # Remote server (Streamable HTTP - recommended)
   python azure_pricing_server.py

   # Or with SSE transport
   python azure_pricing_server.py --transport sse

   # Or with stdio transport (local only)
   python azure_pricing_server.py --transport stdio
   ```
4. **Connect your MCP client** to `http://localhost:8000/mcp` (Streamable HTTP) or `http://localhost:8000/sse` (SSE)

## ✨ Features

- **🌐 Remote MCP Server**: Supports Streamable HTTP, SSE, and stdio transports
- **🔍 Azure Price Search**: Search for Azure service prices with flexible filtering
- **⚖️ Service Comparison**: Compare prices across different regions and SKUs
- **💡 Cost Estimation**: Calculate estimated costs based on usage patterns
- **💰 Savings Plan Information**: Get Azure savings plan pricing when available
- **🌍 Multi-Currency**: Support for multiple currencies (USD, EUR, etc.)
- **📊 Real-time Data**: Uses live Azure Retail Prices API

## 🔌 Supported Transports

| Transport | Endpoint | Use Case |
|-----------|----------|----------|
| **Streamable HTTP** (default) | `http://host:port/mcp` | Remote clients, cloud deployment, production |
| **SSE** (Server-Sent Events) | `http://host:port/sse` | Real-time streaming, legacy MCP clients |
| **stdio** | stdin/stdout | Local integration with Claude Desktop, VS Code |

## 🛠️ Tools Available

| Tool | Description | Example Use |
|------|-------------|-------------|
| `azure_price_search` | Search Azure retail prices with filters | Find VM prices in specific regions |
| `azure_price_compare` | Compare prices across regions/SKUs | Compare storage costs across regions |
| `azure_cost_estimate` | Estimate costs based on usage | Calculate monthly costs for 8hr/day usage |
| `azure_discover_skus` | Discover available SKUs for a service | Find all VM types for a service |
| `azure_sku_discovery` | Intelligent SKU discovery with fuzzy matching | "Find app service plans" or "web app pricing" |

## 📋 Installation

### Quick Install
```bash
# Install dependencies
pip install -r requirements.txt
```

### Automated Setup (Alternative)
```bash
# Windows PowerShell
.\setup.ps1

# Cross-platform (Python)
python setup.py
```

### Manual Setup
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

## 🚀 Running the Server

### Remote Server (Streamable HTTP - Recommended)
```bash
# Default: Streamable HTTP on localhost:8000
python azure_pricing_server.py

# Custom host and port
# Custom host and port (expose to all interfaces)
python azure_pricing_server.py --host 0.0.0.0 --port 9000

# As a Python module
python -m azure_pricing_server --transport streamable-http --port 8000
```

### Remote Server (SSE)
```bash
python azure_pricing_server.py --transport sse --port 8000
```

### Local Server (stdio)
```bash
python azure_pricing_server.py --transport stdio
```

### Command-Line Options
```
usage: azure_pricing_server.py [-h] [--transport {stdio,sse,streamable-http}]
                                [--host HOST] [--port PORT]

options:
  --transport {stdio,sse,streamable-http}  Transport protocol (default: streamable-http)
  --host HOST                               Host to bind to (default: 127.0.0.1)
  --port PORT                               Port to bind to (default: 8000)
```

## 🔧 Client Configuration

### Claude Desktop (Remote - Streamable HTTP)
```json
{
  "mcpServers": {
    "azure-pricing": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Claude Desktop (Local - stdio)
```json
{
  "mcpServers": {
    "azure-pricing": {
      "command": "python",
      "args": ["-m", "azure_pricing_server", "--transport", "stdio"],
      "cwd": "/path/to/azure_pricing"
    }
  }
}
```

### VS Code (Remote)
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

### VS Code (Local - stdio)
```json
{
  "mcp": {
    "servers": {
      "azure-pricing": {
        "command": "python",
        "args": ["-m", "azure_pricing_server", "--transport", "stdio"],
        "cwd": "/path/to/azure_pricing"
      }
    }
  }
}
```

## 💬 Example Queries

Once configured with Claude, you can ask:

- **Basic Pricing**: "What's the price of Azure SQL Database?"
- **Comparisons**: "Compare VM prices between East US and West Europe"
- **Cost Estimation**: "Estimate costs for running a D4s_v3 VM 12 hours per day"
- **Savings**: "What are the reserved instance savings for virtual machines?"
- **GPU Pricing**: "Show me all GPU-enabled VMs with pricing"
- **Service Discovery**: "Find all App Service plan pricing" or "What storage options are available?"
- **SKU Discovery**: "Show me all web app hosting plans"

## 🧪 Testing

### Test the Remote Server
```bash
# Start the server
python azure_pricing_server.py

# In another terminal, test with curl:
# Initialize session
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'

# List tools (use session ID from response headers)
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: <SESSION_ID>" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

### Test Setup and Connectivity
```bash
# Windows PowerShell
.\test_setup.ps1

# Cross-platform test
python -m azure_pricing_server --test
```

## 📚 Documentation

- **[QUICK_START.md](QUICK_START.md)** - Step-by-step setup guide
- **[USAGE_EXAMPLES.md](USAGE_EXAMPLES.md)** - Detailed usage examples and API responses
- **[config_examples.json](config_examples.json)** - Example configurations for Claude Desktop and VS Code

## 🔌 API Integration

This server uses the official Azure Retail Prices API:
- **Endpoint**: `https://prices.azure.com/api/retail/prices`
- **Version**: `2023-01-01-preview` (latest, supports savings plans)
- **Authentication**: None required (public API)
- **Rate Limits**: Generous limits for retail pricing data

## 🌟 Key Features

### Multi-Transport Support
- **Streamable HTTP**: Modern, efficient remote protocol on `/mcp` endpoint
- **SSE**: Server-Sent Events for real-time streaming on `/sse` endpoint
- **stdio**: Standard I/O for local subprocess integration

### Smart Filtering
- Filter by service name, family, region, SKU
- Support for partial matches and contains operations
- Case-sensitive filtering for precise results

### Cost Optimization
- Automatic savings plan detection
- Reserved instance pricing comparisons
- Multi-region cost analysis
- Intelligent SKU discovery for finding the best pricing options

### Developer Friendly
- Comprehensive error handling
- Detailed logging for troubleshooting
- Flexible parameter support
- Cross-platform setup scripts (PowerShell and Python)

## 🤝 Contributing

This project follows the Spec-Driven Development (SDD) methodology. Contributions are welcome!

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details

## 🙋‍♂️ Support

- Check [QUICK_START.md](QUICK_START.md) for setup issues
- Review [USAGE_EXAMPLES.md](USAGE_EXAMPLES.md) for query patterns
- Open an issue for bugs or feature requests

---

*Built with the Model Context Protocol (MCP) SDK for seamless integration with Claude and other AI assistants. Supports remote deployment via Streamable HTTP and SSE transports.*