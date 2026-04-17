"""
Entry point for running the Azure Pricing MCP Server as a module.

Usage:
    python -m azure_pricing_server                           # Default: streamable-http on 0.0.0.0:8000
    python -m azure_pricing_server --transport stdio          # Local stdio transport
    python -m azure_pricing_server --transport sse            # SSE transport
    python -m azure_pricing_server --transport streamable-http --port 9000  # Custom port
"""

from azure_pricing_server import main

if __name__ == "__main__":
    main()