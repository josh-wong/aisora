import os
import platform

# Your registered Signal phone number (must start with '+', followed by your country code and phone number)
SIGNAL_NUMBER = "+<PHONE_NUMBER>"

# Bot name for mentions in group chats
AI_ASSISTANT_NICKNAME = "<NICKNAME>"

# Model configuration
USE_PHI = True
MODEL_CONFIG = {
    "context_window": 4096, # Context window size for Phi model
}

# Path to the Phi GGUF model file
windows_model_path = r"<PATH_TO_LOCAL_GGUF_FILE>"

# For WSL accessing Windows file paths
if os.path.exists('/proc/version') and 'Microsoft' in open('/proc/version').read():
    # Running in WSL - Convert the Windows path to the WSL path.
    # Convert backslashes to forward slashes for WSL.
    wsl_ready_path = windows_model_path.replace('\\', '/')
    # Convert drive letter to WSL mount point.
    PHI_MODEL_PATH = f"/mnt/{wsl_ready_path[0].lower()}/{wsl_ready_path[2:]}"
    print(f"WSL mode: Using model at {PHI_MODEL_PATH}")
elif platform.system() == "Windows":
    PHI_MODEL_PATH = windows_model_path
    print(f"Windows mode: Using model at {PHI_MODEL_PATH}")
else:  # Regular Linux/Mac - Still use the WSL path to the Windows drive.
    # This path is for Ubuntu WSL accessing the Windows drive.
    wsl_ready_path = windows_model_path.replace('\\', '/')
    PHI_MODEL_PATH = f"/mnt/{wsl_ready_path[0].lower()}/{wsl_ready_path[2:]}"
    print(f"Linux mode: Using model at {PHI_MODEL_PATH}")
    
    # Check if the model exists and print a helpful message if not.
    if not os.path.exists(PHI_MODEL_PATH):
        print(f"Warning: Model file not found at {PHI_MODEL_PATH}")
        print("Please ensure your Windows drive is mounted properly in WSL")

# Your PostgreSQL database configuration
DB_CONFIG = {
    'dbname': '<DATABASE_NAME>',
    'user': '<USERNAME>',
    'password': '<PASSWORD>',
    'host': 'localhost',
    'port': '5432'
}

# System prompt that defines how the AI should behave
SYSTEM_PROMPT = """
<PROMPT>
"""
