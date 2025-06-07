# IMPORTANT: Be sure to remove "_TEMPLATE" from the filename before using it.

# Configuration file for Aisora, an AI assistant for Signal.
# This file contains sensitive information. Do not share it with anyone.
import os
import platform

# AI model and configurations
AI_CONFIG = {
    'use_llama': True,
    'model': {
        'context_window': 4096, # Context window size for Llama model
        'path': r"<PATH_TO_LOCAL_GGUF_FILE>" # Windows path to the Llama GGUF model file
    }
}

# PostgreSQL database settings
DB_CONFIG = {
    'dbname': '<DATABASE_NAME>',
    'user': '<USERNAME>',
    'password': '<PASSWORD>',
    'host': 'localhost',
    'port': '5432'
}

# Signal messenger settings
SIGNAL_CONFIG = {
    'phone_number': "+<PHONE_NUMBER>", # The registered Signal phone number for the AI assistant. Must start with '+', followed by your country code and phone number.
    'assistant_nickname': "<NICKNAME>", # AI assistant name for mentions in group chats
    'notification_recipients': "active_chats", # Recipients for system notifications (startup, shutdown). Set to "active_chats" to notify all users with whom the assistant has active chats. Or specify a list of phone numbers, like ["+1234567890", "+0987654321"].
    'active_chat_period_days': 8 # Number of days to consider a chat "active" for notifications and status tracking
}

# Usage limits and messaging
USAGE_CONFIG = {
    'enabled': True, # Set to False to disable usage limits entirely.
    'daily_message_limit': 10, # Set the messages per day per user. Set to 0 for unlimited messages.
    'warning': {
        'threshold': 5, # When the user has this many messages left, they wil receive a warning message.
        'message': "⚠️ You've used {used} of your {limit} daily messages. You have {remaining} messages remaining for today.",
    },
    'limit_reached_message': "⚠️ You've reached your daily limit of {limit} messages. Your limit will reset in 24 hours."
}

# For WSL accessing Windows file paths
windows_model_path = AI_CONFIG['model']['path']
if os.path.exists('/proc/version') and 'Microsoft' in open('/proc/version').read():
    # Running in WSL - Convert the Windows path to the WSL path.
    # Convert backslashes to forward slashes for WSL.
    wsl_ready_path = windows_model_path.replace('\\', '/')
    # Convert drive letter to WSL mount point.
    LLAMA_MODEL_PATH = f"/mnt/{wsl_ready_path[0].lower()}/{wsl_ready_path[2:]}"
    print(f"WSL mode: Using model at {LLAMA_MODEL_PATH}")
elif platform.system() == "Windows":
    LLAMA_MODEL_PATH = windows_model_path
    print(f"Windows mode: Using model at {LLAMA_MODEL_PATH}")
else: # Regular Linux/Mac - Still use the WSL path to the Windows drive.
    # This path is for Ubuntu WSL accessing the Windows drive.
    wsl_ready_path = windows_model_path.replace('\\', '/')
    LLAMA_MODEL_PATH = f"/mnt/{wsl_ready_path[0].lower()}/{wsl_ready_path[2:]}"
    print(f"Linux mode: Using model at {LLAMA_MODEL_PATH}")
    
    # Check if the model exists and print a helpful message if not.
    if not os.path.exists(LLAMA_MODEL_PATH):
        print(f"Warning: Model file not found at {LLAMA_MODEL_PATH}")
        print("Please ensure your Windows drive is mounted properly in WSL")

# The system prompt for the AI assistant
SYSTEM_PROMPT = """
<PROMPT>
"""

# System prompt for image descriptions - used when the AI is asked to describe images
IMAGE_SYSTEM_PROMPT = SYSTEM_PROMPT + """
When shown an image without a specific question, always describe the image in detail without asking for clarification. Never ask what the user wants to know about the image - just provide a comprehensive description. Note that only one image will be processed at a time (the most recently sent one). IMPORTANT: Do not under any circumstances ask for clarification or ask what specific information the user wants about the image. Your task is to directly describe what you see in the image in detail, without waiting for further instructions. DO NOT end your response with questions like 'What would you like to know about this image?' or 'Is there something specific you want to know?' - simply provide the complete visual description. This is a critical requirement.
"""
