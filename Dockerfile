FROM python:3.10-slim

WORKDIR /app

# Install only essential build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install optimized llama-cpp-python with AVX2/FMA optimizations for CPU
RUN pip install --upgrade pip && \
    CMAKE_ARGS="-DLLAMA_AVX2=on -DLLAMA_FMA=on" pip install --no-cache-dir llama-cpp-python

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY ./app/* /app/

# Copy model files
COPY ./models /app/models

# Explicitly copy the .streamlit directory
COPY ./.streamlit /app/.streamlit

# Launch Streamlit
CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]