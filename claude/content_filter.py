import re
import json
import os
from datetime import datetime
from db_utils import get_db_connection
from psycopg2.extras import RealDictCursor

# Categories of inappropriate content
INAPPROPRIATE_CATEGORIES = {
    "illegal_activities": [
        r"hack(ing)?\s+(into|someone|system)",
        r"stea(l|ling)\s+(identity|money|credit\s*card)",
        r"(make|create|obtain)\s+(fake|counterfeit|forged)\s+(passport|id|license)",
        r"(buy|sell|manufacture)\s+illegal\s+(drugs|weapons|firearms)",
        r"(child|minor).{1,20}(porn|explicit|sexual)",
    ],
    "harmful_content": [
        r"(how\s+to\s+)?(make|create|build)\s+(bomb|explosive|weapon|poison)",
        r"(instructions|steps)\s+(for|to)\s+(kill|murder|harm)",
        r"(torture|abuse)\s+(method|technique)",
        r"sui[c]+ide\s+(instructions|methods|ways)",
        r"(spread|create|distribute)\s+malware",
    ],
    "explicit_content": [
        r"(explicit|graphic|detailed).{1,10}(sex|porn)",
        r"sex.{1,10}with.{1,10}(underage|children|minors)",
        r"(rape|assault).{1,10}(fantasy|story|scenario)",
    ],
    "unethical_requests": [
        r"(write|create)\s+(school|college|university)\s+(essay|paper|assignment)",
        r"(cheat|hack).{1,20}(exam|test|quiz)",
        r"(manipulate|deceive|trick)\s+(someone|people|a person)",
        r"(spread|create)\s+(misinformation|fake\s+news|propaganda)",
        r"(deepfake|fake).{1,10}(imagery|video|audio)",
    ],
    "hate_speech": [
        r"(hate|violent)\s+speech\s+(against|targeting)",
        r"(racial|ethnic|religious)\s+slur",
        r"(promoting|encouraging|inciting)\s+violence",
    ]
}

# List of generally inappropriate terms (simplified detection)
INAPPROPRIATE_TERMS = [
    # Violence-related terms
    r"\bmurder\b", r"\bkill\b", r"\bassault\b", r"\btorture\b",
    
    # Drug-related terms
    r"\bcocaine\b", r"\bheroin\b", r"\bmeth(amphetamine)?\b",
    
    # Explicit terms (limited set, add with caution)
    r"\bporn(ography)?\b", 
    
    # Illegal activities
    r"\bhack(ing)?\b", r"\bphish(ing)?\b", r"\bscam(ming)?\b"
]

# Common legitimate contexts that might be misinterpreted.
LEGITIMATE_CONTEXTS = [
    r"(discuss|analyze|research|study|historical|context|academic|legal)",
    r"(fiction(al)?|story|novel|movie|film|book|literature|creative)",
    r"(help|therapy|support|counseling|mental health)",
    r"(news|reporting|journalism|article)",
    r"(security|prevention|protection)"
]

def check_user_restrictions(sender):
    """Check if a user is restricted based on their history."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Check if the user_restrictions table exists.
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'user_restrictions'
                    ) AS table_exists;
                """)
                
                result = cur.fetchone()
                if not result or not result['table_exists']:
                    print("The user_restrictions table doesn't exist yet")
                    return False
                
                # Check if the user is restricted.
                cur.execute("""
                    SELECT is_restricted, restriction_reason, restriction_level
                    FROM user_restrictions
                    WHERE sender = %s
                """, (sender,))
                
                result = cur.fetchone()
                if result and result['is_restricted']:
                    return {
                        'is_restricted': True,
                        'reason': result['restriction_reason'],
                        'level': result['restriction_level']
                    }
                
                return False
                
    except Exception as e:
        print(f"Error checking user restrictions: {e}")
        return False

def log_filtered_request(sender, content, filtered_reason, category=None):
    """Log a filtered request for audit and improvement purposes."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Check if the filtered_requests table exists.
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'filtered_requests'
                    ) AS table_exists;
                """)
                
                result = cur.fetchone()
                table_exists = result[0] if result else False
                
                if not table_exists:
                    # Create the table if it doesn't exist.
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS filtered_requests (
                            id SERIAL PRIMARY KEY,
                            sender TEXT NOT NULL,
                            content TEXT,
                            filtered_reason TEXT,
                            category TEXT,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    conn.commit()
                
                # Log the filtered request.
                cur.execute("""
                    INSERT INTO filtered_requests 
                    (sender, content, filtered_reason, category, timestamp)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    sender, 
                    content, 
                    filtered_reason, 
                    category, 
                    datetime.now()
                ))
                conn.commit()
    except Exception as e:
        print(f"Error logging filtered request: {e}")

def is_legitimate_context(content):
    """Check if the content has a legitimate context for discussing sensitive topics."""
    content_lower = content.lower()
    
    for context_pattern in LEGITIMATE_CONTEXTS:
        if re.search(context_pattern, content_lower, re.IGNORECASE):
            return True
            
    return False

def detect_inappropriate_content(content, sender=None):
    """
    Multi-layered content-filtering system.
    Returns a tuple: (is_inappropriate, reason, category)
    """
    # Skip empty content.
    if not content or not content.strip():
        return (False, None, None)
    
    # Normalize content for pattern matching.
    content_lower = content.lower()
    
    # Step 1: Check user restrictions.
    if sender:
        user_restriction = check_user_restrictions(sender)
        if user_restriction:
            return (True, 
                    f"User is restricted: {user_restriction['reason']}", 
                    "restricted_user")
    
    # Step 2: Check for obvious inappropriate terms first (quick check).
    for term in INAPPROPRIATE_TERMS:
        if re.search(term, content_lower, re.IGNORECASE):
            # If a term is found, check for legitimate context.
            if is_legitimate_context(content):
                # Allow content that discusses topics in legitimate contexts.
                continue
            return (True, 
                    f"Content contains inappropriate term: {term}", 
                    "inappropriate_term")
    
    # Step 3: More detailed category-based pattern matching.
    for category, patterns in INAPPROPRIATE_CATEGORIES.items():
        for pattern in patterns:
            if re.search(pattern, content_lower, re.IGNORECASE):
                # If a pattern found, check for legitimate context.
                if is_legitimate_context(content):
                    continue
                return (True, 
                        f"Content matches pattern in category: {category}", 
                        category)
    
    # Content passed all filters.
    return (False, None, None)

def get_restricted_content_response(category):
    """Generate an appropriate response for filtered content."""
    responses = {
        "illegal_activities": "I'm unable to provide assistance with content related to illegal activities.",
        "harmful_content": "I cannot provide information that could potentially cause harm to others.",
        "explicit_content": "I'm unable to engage with explicit or inappropriate content.",
        "unethical_requests": "I cannot assist with requests that violate ethical guidelines.",
        "hate_speech": "I cannot generate or engage with content that promotes hate speech.",
        "inappropriate_term": "Your message contains content that I'm not able to respond to.",
        "restricted_user": "Your account has been restricted due to previous violations of our content policy."
    }
    
    return responses.get(
        category, 
        "I'm unable to process this request as it may violate content guidelines."
    )

def filter_content(content, sender=None):
    """
    Main content-filtering function.
    Returns a tuple: (filtered_content, is_filtered, reason)
    If content is filtered, filtered_content will be None.
    """
    is_inappropriate, reason, category = detect_inappropriate_content(content, sender)
    
    if is_inappropriate:
        # Log the filtered request.
        if sender:
            log_filtered_request(sender, content, reason, category)
            
        response = get_restricted_content_response(category)
        return (None, True, response)
    
    # Content is appropriate
    return (content, False, None)
