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
COPY apps/ ./apps/
COPY src/ ./src/
COPY notebooks/ ./notebooks/
COPY fixtures/ ./fixtures/
COPY generate_report.py .
COPY output/ ./output/

# Expose port
EXPOSE 8000

# Run the API
CMD ["uvicorn", "packages.python.accessflow_ml.cli:app", "--host", "0.0.0.0", "--port", "8000"]
