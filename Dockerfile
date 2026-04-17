FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY azure_pricing_server.py .
COPY __main__.py .
COPY __init__.py .
COPY static/ static/

# Expose the default port
EXPOSE 8000

# Default: run with all transports (SSE + Streamable HTTP + Test UI) on 0.0.0.0
ENTRYPOINT ["python", "azure_pricing_server.py"]
CMD ["--transport", "all", "--host", "0.0.0.0", "--port", "8000"]
