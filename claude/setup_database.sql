-- This script sets up the necessary PostgreSQL database and tables for Aisora.

-- Create the database (run as postgres superuser)
-- CREATE DATABASE aisora_claude;

-- Connect to the database before running the rest:
-- \c aisora_claude

-- Create the query_log table.
CREATE TABLE IF NOT EXISTS query_log (
    id SERIAL PRIMARY KEY,
    sender TEXT NOT NULL,                          -- Phone number of the sender
    query TEXT NOT NULL,                           -- Message from the user
    response TEXT NOT NULL,                        -- Claude's response
    conversation_id TEXT NOT NULL,                 -- UUID for grouping conversations
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Timestamp of the message
    is_group TEXT DEFAULT FALSE,                   -- Whether the message was sent in a group
    group_id TEXT,                                 -- Group ID if message was sent in a group
    sender_name TEXT,                              -- Name of the sender if available
    country TEXT,                                  -- Country based on phone number
    city TEXT,                                     -- City based on phone number
    possible_carrier TEXT,                         -- Possible carrier based on phone number
    location TEXT,                                 -- General location information
);

-- Create index for faster queries.
CREATE INDEX idx_conversation_id ON query_log(conversation_id);
CREATE INDEX idx_sender ON query_log(sender);
CREATE INDEX idx_timestamp ON query_log(timestamp);

-- Create a view for recent conversations.
CREATE OR REPLACE VIEW recent_conversations AS
SELECT 
    conversation_id,
    sender,
    sender_name,
    MAX(timestamp) as last_interaction,
    COUNT(*) as message_count
FROM query_log
GROUP BY conversation_id, sender, sender_name
ORDER BY last_interaction DESC;
