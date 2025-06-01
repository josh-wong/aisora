-- This script sets up the necessary PostgreSQL database and tables for Aisora.

-- Create the database (run as postgres superuser)
-- CREATE DATABASE aisora_claude;

-- Connect to the database before running the rest:
-- \c aisora_claude

-- Create the query_log table.
CREATE TABLE IF NOT EXISTS query_log (
    id SERIAL PRIMARY KEY,
    sender TEXT NOT NULL,                          -- Phone number of the sender
    restricted_user BOOLEAN DEFAULT FALSE,  -- Whether the user is restricted
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
    attachment_paths TEXT                          -- Location where attachments are on the server
);

-- Create index for faster queries.
CREATE INDEX idx_conversation_id ON query_log(conversation_id);
CREATE INDEX idx_sender ON query_log(sender);
CREATE INDEX idx_timestamp ON query_log(timestamp);

-- Create the user restrictions table for content filtering.
CREATE TABLE IF NOT EXISTS user_restrictions (
    id SERIAL PRIMARY KEY,
    sender TEXT NOT NULL,
    is_restricted BOOLEAN DEFAULT FALSE,
    restriction_reason TEXT,
    restriction_level TEXT DEFAULT 'warning',
    violation_count INTEGER DEFAULT 0,
    last_violation_date TIMESTAMP,
    restriction_date TIMESTAMP,
    expiration_date TIMESTAMP,
    appeal_status TEXT DEFAULT 'none',
    appeal_date TIMESTAMP,
    notes TEXT
);

-- Create the filtered requests table for content filtering.
CREATE TABLE IF NOT EXISTS filtered_requests (
    id SERIAL PRIMARY KEY,
    sender TEXT NOT NULL,
    content TEXT,
    filtered_reason TEXT,
    category TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
