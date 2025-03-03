FROM python:3.10-slim

WORKDIR /app

# Install essential build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


RUN pip install torch==2.1.0

# Install llama-cpp-python with CUDA support
# Note: This needs CUDA support in the host system
RUN CMAKE_ARGS="-DGGML_CUDA=on" pip install --no-cache-dir llama-cpp-python

# Copy app code
COPY ./app/* /app/
COPY ./models /app/models
COPY ./.streamlit /app/.streamlit

# Launch Streamlit
CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]