# Configuration file for the Signal AI assistant. This file contains sensitive information. Do not share it with anyone.
# Be sure to remove "_TEMPLATE" from the filename before using it.

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

# The system prompt for the AI assistant
SYSTEM_PROMPT = """
<PROMPT>
"""
