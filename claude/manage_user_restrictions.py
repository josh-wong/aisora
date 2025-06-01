# This script is for manually managing user restrictions for content filtering in a system. You likely won't need to use this since automated user restrictions are handled in contet_filter.py. However, if you want to manually restrict or unrestrict users, you can use this script.
import argparse
from datetime import datetime
from db_utils import get_db_connection

def restrict_user(sender, reason=None, level="warning"):
    """Restrict a user from using the system."""
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
                    sender_exists, current_violations = result
                    new_count = current_violations + 1
                    
                    cur.execute("""
                        UPDATE user_restrictions
                        SET is_restricted = TRUE,
                            restriction_reason = COALESCE(%s, restriction_reason),
                            restriction_level = %s,
                            violation_count = %s,
                            last_violation_date = %s,
                            restriction_date = %s
                        WHERE sender = %s
                    """, (
                        reason,
                        level,
                        new_count,
                        datetime.now(),
                        datetime.now(),
                        sender
                    ))
                else:
                    # Insert a new user restriction.
                    cur.execute("""
                        INSERT INTO user_restrictions
                        (sender, is_restricted, restriction_reason, restriction_level,
                        violation_count, last_violation_date, restriction_date)
                        VALUES (%s, TRUE, %s, %s, 1, %s, %s)
                    """, (
                        sender,
                        reason,
                        level,
                        datetime.now(),
                        datetime.now()
                    ))
                
                conn.commit()
                print(f"User {sender} has been restricted. Reason: {reason}")
                return True
                
    except Exception as e:
        print(f"Error restricting user: {e}")
        return False

def unrestrict_user(sender):
    """Remove restrictions from a user."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE user_restrictions
                    SET is_restricted = FALSE,
                        appeal_status = 'approved',
                        appeal_date = %s,
                        notes = CONCAT(COALESCE(notes, ''), '\nRestriction removed on ', %s)
                    WHERE sender = %s
                """, (
                    datetime.now(),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    sender
                ))
                
                if cur.rowcount > 0:
                    conn.commit()
                    print(f"Restrictions removed from user {sender}")
                    return True
                else:
                    print(f"User {sender} not found or not restricted")
                    return False
                
    except Exception as e:
        print(f"Error removing user restriction: {e}")
        return False

def list_restricted_users():
    """List all restricted users."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT sender, restriction_reason, restriction_level, 
                           violation_count, restriction_date
                    FROM user_restrictions
                    WHERE is_restricted = TRUE
                    ORDER BY restriction_date DESC
                """)
                
                results = cur.fetchall()
                
                if not results:
                    print("No restricted users found.")
                    return []
                
                print("\nCurrent Restricted Users:")
                print("-" * 80)
                print(f"{'User ID':<20} {'Level':<10} {'Violations':<10} {'Restriction Date':<20} {'Reason'}")
                print("-" * 80)
                
                for row in results:
                    sender, reason, level, count, date = row
                    date_str = date.strftime("%Y-%m-%d %H:%M:%S") if date else "N/A"
                    reason_disp = (reason[:50] + '...') if reason and len(reason) > 50 else reason or "N/A"
                    
                    print(f"{sender:<20} {level:<10} {count:<10} {date_str:<20} {reason_disp}")
                
                return results
                
    except Exception as e:
        print(f"Error listing restricted users: {e}")
        return []

def get_violation_history(sender):
    """Get violation history for a specific user."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get user restriction info.
                cur.execute("""
                    SELECT * FROM user_restrictions
                    WHERE sender = %s
                """, (sender,))
                
                user_info = cur.fetchone()
                
                if not user_info:
                    print(f"No restriction record found for user {sender}")
                    return None
                
                # Get filtered-request history.
                cur.execute("""
                    SELECT * FROM filtered_requests
                    WHERE sender = %s
                    ORDER BY timestamp DESC
                """, (sender,))
                
                filtered_requests = cur.fetchall()
                
                # Display user info.
                print("\nUser restriction information:")
                print("-" * 80)
                if user_info:
                    is_restricted = user_info[2] # Assuming column index 2 is is_restricted.
                    status = "RESTRICTED" if is_restricted else "Not restricted"
                    print(f"User ID: {sender}")
                    print(f"Status: {status}")
                    print(f"Violation count: {user_info[5]}") # Assuming column index 5 is violation_count
                    print(f"Last violation: {user_info[6]}") # Assuming column index 6 is last_violation_date
                    print(f"Restriction reason: {user_info[3]}")
                    print(f"Restriction level: {user_info[4]}")
                
                # Display filtered requests.
                if filtered_requests:
                    print("\nFiltered request history:")
                    print("-" * 80)
                    for i, req in enumerate(filtered_requests, 1):
                        timestamp = req[5].strftime("%Y-%m-%d %H:%M:%S") if req[5] else "N/A"
                        content = req[2][:50] + "..." if req[2] and len(req[2]) > 50 else req[2] or "N/A"
                        reason = req[3][:50] + "..." if req[3] and len(req[3]) > 50 else req[3] or "N/A"
                        
                        print(f"{i}. [{timestamp}] Category: {req[4]}")
                        print(f"   Content: {content}")
                        print(f"   Reason: {reason}")
                        print()
                else:
                    print("\nNo filtered requests found for this user.")
                
                return {
                    "user_info": user_info,
                    "filtered_requests": filtered_requests
                }
                
    except Exception as e:
        print(f"Error getting user violation history: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Manage user restrictions for content filtering')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Restrict-user command.
    restrict_parser = subparsers.add_parser('restrict', help='Restrict a user')
    restrict_parser.add_argument('sender', help='User ID (phone number) to restrict')
    restrict_parser.add_argument('--reason', help='Reason for restriction')
    restrict_parser.add_argument('--level', choices=['warning', 'moderate', 'severe'], 
                                default='warning', help='Restriction level')
    
    # Unrestrict-user command.
    unrestrict_parser = subparsers.add_parser('unrestrict', help='Remove restrictions from a user')
    unrestrict_parser.add_argument('sender', help='User ID to unrestrict')
    
    # List restricted-users command.
    subparsers.add_parser('list', help='List all restricted users')
    
    # Show user violation history.
    history_parser = subparsers.add_parser('history', help='Show violation history for a user')
    history_parser.add_argument('sender', help='User ID to check')
    
    # Parse arguments.
    args = parser.parse_args()
    
    if args.command == 'restrict':
        restrict_user(args.sender, args.reason, args.level)
    elif args.command == 'unrestrict':
        unrestrict_user(args.sender)
    elif args.command == 'list':
        list_restricted_users()
    elif args.command == 'history':
        get_violation_history(args.sender)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
