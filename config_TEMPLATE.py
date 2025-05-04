# Be sure to remove "_TEMPLATE" from the filename before using it.
# Configuration file for Claugnal, a Claude-based AI assistant for Signal. This file contains sensitive information. Do not share it with anyone.

# Your Claude API key
ANTHROPIC_API_KEY = "<API_KEY>"

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
AI_ASSISTANT_FIRST_NAME = "Claugnal"
AI_ASSISTANT_LAST_NAME = ""

# The system prompt for the AI assistant
SYSTEM_PROMPT = """
<PROMPT>
"""
