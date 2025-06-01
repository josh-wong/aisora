import re
import json
import os
from datetime import datetime, timedelta
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
            if user_restriction['level'] == 'permanent':
                return (True, 
                        f"User is permanently banned: {user_restriction['reason']}", 
                        "permanent_ban")
            else:
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
        "restricted_user": "Your account has been restricted due to previous violations of our content policy.",
        "permanent_ban": "Your account has been permanently banned due to repeated violations of our content policy. Further requests will not be processed."
    }
    
    return responses.get(
        category, 
        "I'm unable to process this request as it may violate content guidelines."
    )

def check_violation_count(sender):
    """Check how many violations a user has in the last 24 hours."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Count violations in the last 24 hours.
                cur.execute("""
                    SELECT COUNT(*) FROM filtered_requests
                    WHERE sender = %s 
                    AND timestamp > NOW() - INTERVAL '24 hours'
                """, (sender,))
                
                count = cur.fetchone()[0]
                return count
                
    except Exception as e:
        print(f"Error checking violation count: {e}")
        return 0

def auto_restrict_user(sender, reason=None):
    """Automatically restrict a user after multiple violations."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Check if the user already exists in the restrictions table.
                cur.execute("""
                    SELECT id, violation_count FROM user_restrictions 
                    WHERE sender = %s
                """, (sender,))
                
                result = cur.fetchone()
                
                if result:
                    # Update the existing user record.
                    user_id, current_violations = result
                    new_count = current_violations + 1
                    
                    # Check if this user should be permanently banned (6+ violations).
                    if new_count >= 6:
                        # Permanent ban - No expiration date
                        cur.execute("""
                            UPDATE user_restrictions
                            SET is_restricted = TRUE,
                                restriction_reason = %s,
                                restriction_level = 'permanent',
                                violation_count = %s,
                                last_violation_date = %s,
                                restriction_date = %s,
                                expiration_date = NULL,
                                notes = CONCAT(COALESCE(notes, ''), '\nPermanently banned on ', %s, ' after ', %s, ' violations.')
                            WHERE sender = %s
                        """, (
                            f"Permanent ban: {reason}",
                            new_count,
                            datetime.now(),
                            datetime.now(),
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            str(new_count),
                            sender
                        ))
                        conn.commit()
                        print(f"User {sender} has been PERMANENTLY BANNED after {new_count} violations. Reason: {reason}")
                    else:
                        # Temporary 24-hour restriction.
                        expiration_time = datetime.now() + timedelta(hours=24)
                        cur.execute("""
                            UPDATE user_restrictions
                            SET is_restricted = TRUE,
                                restriction_reason = %s,
                                restriction_level = 'auto',
                                violation_count = %s,
                                last_violation_date = %s,
                                restriction_date = %s,
                                expiration_date = %s,
                                notes = CONCAT(COALESCE(notes, ''), '\nAuto-restricted on ', %s)
                            WHERE sender = %s
                        """, (
                            reason,
                            new_count,
                            datetime.now(),
                            datetime.now(),
                            expiration_time,
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            sender
                        ))
                        conn.commit()
                        print(f"User {sender} has been automatically restricted for 24 hours. Reason: {reason}")
                else:
                    # Insert a new user restriction.
                    # Set an expiration time to 24 hours from now for a new user's first violation.
                    expiration_time = datetime.now() + timedelta(hours=24)
                    cur.execute("""
                        INSERT INTO user_restrictions
                        (sender, is_restricted, restriction_reason, restriction_level,
                        violation_count, last_violation_date, restriction_date, expiration_date, notes)
                        VALUES (%s, TRUE, %s, 'auto', 1, %s, %s, %s, %s)
                    """, (
                        sender,
                        reason,
                        datetime.now(),
                        datetime.now(),
                        expiration_time,
                        f"Auto-restricted on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    ))
                    conn.commit()
                    print(f"User {sender} has been automatically restricted for 24 hours. Reason: {reason}")
                
                return True
                
    except Exception as e:
        print(f"Error auto-restricting user: {e}")
        return False

def check_and_lift_expired_restrictions():
    """Check for and lift expired restrictions."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Find expired restrictions (exclude permanent bans).
                cur.execute("""
                    UPDATE user_restrictions
                    SET is_restricted = FALSE,
                        notes = CONCAT(COALESCE(notes, ''), '\nRestriction automatically lifted on ', %s)
                    WHERE is_restricted = TRUE
                    AND expiration_date IS NOT NULL
                    AND expiration_date <= NOW()
                    AND restriction_level != 'permanent'
                """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
                
                count = cur.rowcount
                conn.commit()
                
                if count > 0:
                    print(f"Lifted restrictions for {count} users with expired restriction periods.")
                
                return count
                
    except Exception as e:
        print(f"Error lifting expired restrictions: {e}")
        return 0

def filter_content(content, sender=None):
    """
    Main content-filtering function.
    Returns a tuple: (filtered_content, is_filtered, reason)
    If content is filtered, filtered_content will be None.
    """
    # First, check for and lift any expired restrictions.
    check_and_lift_expired_restrictions()
    
    is_inappropriate, reason, category = detect_inappropriate_content(content, sender)
    
    if is_inappropriate:
        # Log the filtered request.
        if sender:
            log_filtered_request(sender, content, reason, category)
            
            # Check if this user has had multiple violations in the past 24 hours.
            violation_count = check_violation_count(sender)
            if violation_count >= 2: # Including the current violation
                auto_restrict_user(sender, f"Multiple content violations: {reason}")
                
                # After restriction, check if they're now permanently banned.
                user_status = check_user_restrictions(sender)
                if user_status and user_status['level'] == 'permanent':
                    response = get_restricted_content_response("permanent_ban")
                else:
                    response = get_restricted_content_response("restricted_user")
            else:
                response = get_restricted_content_response(category)
                
            return (None, True, response)
        else:
            response = get_restricted_content_response(category)
            return (None, True, response)
    
    # Content is appropriate
    return (content, False, None)
