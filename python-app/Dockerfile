FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY python-app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY python-app/server.py .
COPY python-app/test_endpoints.py .

# Copy movies data
COPY movies-v2.json.gz .

# Datadog environment variables
ENV DD_SERVICE="movies-api-python"
ENV DD_ENV="prod"
ENV DD_PROFILING_ENABLED="true"

# Expose port
EXPOSE 8080

# Run with ddtrace for profiling
CMD ["ddtrace-run", "python", "server.py"]
