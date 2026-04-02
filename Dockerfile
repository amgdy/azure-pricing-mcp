FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY azure_pricing_server.py .
COPY __main__.py .
COPY __init__.py .

# Expose the default port
EXPOSE 8000

# Default: run with all transports (SSE + Streamable HTTP) on 0.0.0.0
# Override TRANSPORT env var to use a single transport mode:
#   TRANSPORT=streamable-http  (Streamable HTTP only)
#   TRANSPORT=sse              (SSE only)
#   TRANSPORT=stdio            (stdio only)
#   TRANSPORT=all              (SSE + Streamable HTTP together, default)
ENV TRANSPORT=all
ENV HOST=0.0.0.0
ENV PORT=8000

ENTRYPOINT ["python", "azure_pricing_server.py"]
CMD ["--transport", "all", "--host", "0.0.0.0", "--port", "8000"]
