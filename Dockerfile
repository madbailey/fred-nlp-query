FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy package metadata and install Python packages
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -e .

# Launch FastAPI
CMD ["uvicorn", "fred_query.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
