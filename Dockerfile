FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY packages/ ./packages/
COPY apps/api/ ./apps/api/
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY fixtures/ ./fixtures/
COPY generate_report.py .

# Copy committed analytical fixtures for the artifact backend (overridable via volume)
COPY fixtures/phase25/ ./data/processed/
COPY fixtures/phase22-spatial.json ./data/processed/phase22-spatial.json

# Expose port
EXPOSE 8000

# Run the API
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
