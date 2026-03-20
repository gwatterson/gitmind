FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends git semgrep && \
    rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY app/ ./app/

# Create secrets directory
RUN mkdir -p /app/secrets

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
