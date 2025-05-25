# Configuration file for Aisora, an AI assistant for Signal. This file contains sensitive information. Do not share it with anyone.
# IMPORTANT: Be sure to remove "_TEMPLATE" from the filename before using it.

# Your Claude API key
ANTHROPIC_API_KEY = "<YOUR_API_KEY>"

# Claude model configuration
MODEL_CONFIG = {
    'model': 'claude-3-5-haiku-20241022', # Model name (for example, 'claude-3-5-haiku-20241022', 'claude-3-7-sonnet-latest')
    'max_tokens': 8192, # Maximum number of tokens in the response
    'temperature': 0.7 # Controls randomness (0.0-1.0)
}

# Your PostgreSQL database configuration
DB_CONFIG = {
    'dbname': '<DATABASE_NAME>',
    'user': '<USERNAME>',
    'password': '<PASSWORD>',
    'host': 'localhost',
    'port': '5432'
}

# Your registered Signal phone number (must start with '+', followed by your country code and phone number)
SIGNAL_NUMBER = "+<PHONE_NUMBER>"

# Bot name for mentions in group chats
AI_ASSISTANT_NICKNAME = "<NICKNAME>"

# Recipients for system notifications (startup, shutdown)
# Set to "active_chats" to notify all users with whom the assistant has active chats.
# Otherwise, provide a list of specific phone numbers: ["+1234567890", "+0987654321"]
NOTIFICATION_RECIPIENTS = "active_chats"

# Number of days to consider a chat "active" for notifications and status tracking (default value: 8 days)
ACTIVE_CHAT_PERIOD_DAYS = 8

# The system prompt for the AI assistant
SYSTEM_PROMPT = """
<PROMPT>
"""
