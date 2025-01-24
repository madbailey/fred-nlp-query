# Dockerfile (FIXED)
FROM python:3.10-slim

WORKDIR /app

# 1. Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Create models directory before downloading
RUN mkdir -p /app/models

# 3. Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. Download LLM (only if not using volume mounts)
RUN curl -L -o /app/models/llama-3-8b.Q4_K_M.gguf \
    "https://huggingface.co/TheBloke/Llama-3-8B-GGUF/resolve/main/llama-3-8b.Q4_K_M.gguf"

# 5. Copy app code
COPY ./app/* /app/

# 6. Launch Streamlit
CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]