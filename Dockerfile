# Use an NVIDIA CUDA base image that includes the runtime and cuDNN
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu20.04

# Set non-interactive mode to avoid timezone prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

WORKDIR /app

# Install Python, pip, and essential build dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    build-essential \
    cmake \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Create symbolic link for python command
RUN ln -sf /usr/bin/python3 /usr/bin/python

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip3 install --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt

# Install torch with CUDA support
RUN pip3 install torch==2.1.0+cu118 --extra-index-url https://download.pytorch.org/whl/cu118

# Install llama-cpp-python with CUDA support
ENV CUDA_HOME=/usr/local/cuda
ENV CUDACXX=/usr/local/cuda/bin/nvcc
RUN CMAKE_ARGS="-DGGML_CUDA=on" pip3 install --no-cache-dir llama-cpp-python


# Copy app code and other assets
COPY ./app/* /app/
COPY ./models/* /app/models/
COPY ./.streamlit /app/.streamlit

# Launch Streamlit
CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]