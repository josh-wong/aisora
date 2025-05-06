import psycopg2
from psycopg2.extras import RealDictCursor
from config import DB_CONFIG

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def log_conversation(sender, query, response, conversation_id, is_group=False, group_id=None, 
                 sender_name=None, country=None, city=None, possible_carrier=None, location=None):
    """Log a conversation to the database."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                INSERT INTO query_log 
                (sender, query, response, timestamp, conversation_id, is_group, group_id, 
                sender_name, country, city, possible_carrier, location)
                VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (sender, query, response, conversation_id, is_group, group_id, 
                 sender_name, country, city, possible_carrier, location))
        conn.commit()

def get_conversation_history(conversation_id):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM query_log 
                WHERE conversation_id = %s 
                ORDER BY timestamp ASC
            """, (conversation_id,))
            return cur.fetchall()

def get_recent_conversation_history(conversation_id, limit=5):
    """Get the most recent conversation history for context"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT timestamp, query, response 
                FROM query_log 
                WHERE conversation_id = %s 
                ORDER BY timestamp DESC 
                LIMIT %s
            """, (conversation_id, limit))
            history = cur.fetchall()
            return list(reversed(history))
