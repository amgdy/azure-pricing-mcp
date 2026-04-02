#!/usr/bin/env bash
set -e

echo "📦 Installing Python dependencies..."
pip install --user -r requirements.txt

echo "✅ Dev container setup complete!"
echo ""
echo "Available commands:"
echo "  python azure_pricing_server.py                         # Streamable HTTP (default)"
echo "  python azure_pricing_server.py --transport all         # SSE + Streamable HTTP"
echo "  python azure_pricing_server.py --transport sse         # SSE only"
echo "  python azure_pricing_server.py --transport stdio       # stdio only"
echo "  azd up                                                 # Deploy to Azure Container Apps"
echo "  docker build -t azure-pricing-mcp .                    # Build container image"
