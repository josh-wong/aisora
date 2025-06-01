import os
from db_utils import get_db_connection

def setup_content_filter_tables():
    """
    Create the tables needed for content filtering if they don't exist:
    1. user_restrictions - Track users with restriction status.
    2. filtered_requests - Log of filtered requests for auditing.
    
    This function reads database setup from setup_database.sql.
    """
    try:
        # Define the path to the SQL script within the claude directory.
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sql_file_path = os.path.join(current_dir, 'setup_database.sql')
        
        # Read the SQL file.
        if os.path.exists(sql_file_path):
            with open(sql_file_path, 'r') as f:
                sql_script = f.read()
                
            # Execute the SQL script.
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Execute the full script, which is specific to PostgreSQL.
                    cur.execute(sql_script)
                    conn.commit()
                    print("Content filter database tables created successfully.")
        else:
            print(f"Error: SQL file not found at: {sql_file_path}")
            print("Please make sure setup_database.sql exists in the claude directory.")
    
    except Exception as e:
        print(f"Error setting up content filter tables: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    setup_content_filter_tables()
