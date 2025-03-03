import os
import sys
import subprocess
import ctypes
from ctypes import *

# Check system CUDA
print("=== SYSTEM CUDA CHECK ===")
try:
    subprocess.run(["nvidia-smi"], check=True)
    print("nvidia-smi works - GPU drivers installed")
except:
    print("nvidia-smi failed - GPU drivers not available in container")

# Check CUDA libraries
print("\n=== CUDA LIBRARIES CHECK ===")
try:
    cuda = ctypes.CDLL("libcuda.so")
    print("libcuda.so found")
except:
    print("libcuda.so not found")

# Check Python CUDA access
print("\n=== PYTHON CUDA ACCESS ===")
try:
    import torch
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA version: {torch.version.cuda}")
        print(f"GPU device: {torch.cuda.get_device_name(0)}")
        print(f"GPU memory: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.2f} GB")
except ImportError:
    print("PyTorch not installed")

# Check llama-cpp-python CUDA compilation
print("\n=== LLAMA-CPP-PYTHON CUDA COMPILATION CHECK ===")
try:
    import llama_cpp
    print(f"llama_cpp version: {llama_cpp.__version__}")
    
    # Check if CUDA was enabled during compilation
    cuda_info = getattr(llama_cpp, "_cuda_info", None)
    if cuda_info:
        print(f"CUDA info: {cuda_info}")
        print("CUDA support compiled into llama-cpp-python")
    else:
        print("No _cuda_info attribute found. Let's check another way:")
        
    # Alternative check - try to create a model with CUDA settings
    try:
        from llama_cpp import Llama
        # Don't actually load a model, just check if the CUDA params are accepted
        params = {
            "model_path": "/nonexistent_path.gguf",
            "n_gpu_layers": 1,
            "verbose": True
        }
        # This should fail with a file not found error, not a CUDA error
        # if CUDA is properly compiled in
        try:
            Llama(**params)
        except FileNotFoundError:
            print("CUDA params accepted - CUDA support confirmed")
        except TypeError as e:
            if "unexpected keyword argument" in str(e) and "n_gpu_layers" in str(e):
                print("CUDA params rejected - likely NO CUDA support in this build")
            else:
                print(f"Other error: {e}")
    except Exception as e:
        print(f"Error testing CUDA in llama_cpp: {e}")
        
except ImportError:
    print("llama_cpp not installed")

print("\n=== ENVIRONMENT VARIABLES ===")
for key, value in os.environ.items():
    if "CUDA" in key or "NVIDIA" in key or "GPU" in key:
        print(f"{key}={value}")