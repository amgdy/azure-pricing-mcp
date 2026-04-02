# Quick Start Guide - Azure Pricing MCP Server

## Prerequisites

- Python 3.10 or higher
- An MCP client (Claude Desktop, VS Code with Copilot, or any MCP-compatible client)

## Installation

### Option 1: Quick Install
```bash
# Install dependencies
pip install -r requirements.txt
```

### Option 2: Virtual Environment (Recommended)
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Option 3: Automated Setup (Windows)
```bash
# Run the setup script
.\setup.ps1
```

## Running the Server

### Remote Server (Recommended)
```bash
# Start with Streamable HTTP transport (default)
python azure_pricing_server.py

# The server will be available at:
#   Streamable HTTP: http://localhost:8000/
```

### Other Transport Options
```bash
# SSE transport
python azure_pricing_server.py --transport sse
#   SSE endpoint: http://localhost:8000/sse

# stdio transport (local only)
python azure_pricing_server.py --transport stdio

# Custom host and port
python azure_pricing_server.py --host 127.0.0.1 --port 9000
```

## Testing the Setup

### Test 1: Start the server and verify
```bash
# Start the server
python azure_pricing_server.py

# In another terminal, test the endpoint:
curl -X POST http://localhost:8000/ \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

### Test 2: Full MCP Server
```bash
# Test complete MCP server functionality
python test_server.py
```

## Client Configuration

### Claude Desktop (Remote - Recommended)

1. Start the server: `python azure_pricing_server.py`
2. Find your Claude Desktop config file:
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Linux**: `~/.config/Claude/claude_desktop_config.json`

3. Add the MCP server configuration:
```json
{
  "mcpServers": {
    "azure-pricing": {
      "url": "http://localhost:8000/"
    }
  }
}
```

4. Restart Claude Desktop

### Claude Desktop (Local - stdio)

No server process needed. Add to your config:
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

1. Start the server: `python azure_pricing_server.py`
2. Add to VS Code settings.json:
```json
{
  "mcp": {
    "servers": {
      "azure-pricing": {
        "url": "http://localhost:8000/"
      }
    }
  }
}
```

## Usage

Once configured, you can ask Claude questions like:

- "What's the price of a Standard_D2s_v3 VM in East US?"
- "Compare Azure storage prices between regions"
- "Estimate monthly costs for running a web application"
- "What are the cheapest compute options available?"
- "Find all App Service plan pricing"
- "Show me all web app hosting plans"

## Available Tools

1. **azure_price_search** - Search prices with filters
2. **azure_price_compare** - Compare prices across regions/SKUs  
3. **azure_cost_estimate** - Estimate costs based on usage
4. **azure_discover_skus** - Discover available SKUs for a service
5. **azure_sku_discovery** - Intelligent SKU discovery with fuzzy matching
6. **get_customer_discount** - Get customer discount information

## Troubleshooting

### Common Issues

**"Connection refused" when connecting remotely:**
- Make sure the server is running: `python azure_pricing_server.py`
- Check the port is not blocked by a firewall
- Verify the URL matches the transport (e.g., `/` for Streamable HTTP)

**"Import errors" when running:**
- Make sure dependencies are installed: `pip install -r requirements.txt`
- If using a virtual environment, make sure it's activated

**"No results found":**
- Check service name spelling (case-sensitive)
- Try broader search terms
- Verify region names

**"Server not responding in Claude":**
- For remote: Verify the server is running and the URL is correct
- For stdio: Check Claude Desktop config file syntax and file path
- Restart Claude Desktop after changes

### Getting Help

1. Check the server logs (printed to console)
2. Test the endpoint with curl
3. Review `USAGE_EXAMPLES.md` for query examples
4. Ensure all dependencies are installed

## Next Steps

- Review `USAGE_EXAMPLES.md` for detailed usage patterns
- Customize the server for your specific needs
- Deploy the server to a cloud environment for team access
- Integrate with your existing cost management workflows