import mysql.connector
from mysql.connector import Error
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_connection():
    try:
        connection = mysql.connector.connect(
            host='localhost',
            database='tourbook',
            user='root',
            password='$r1ya777',
            autocommit=True,
            connect_timeout=30
        )
        if connection.is_connected():
            logger.info("Connected to MySQL database")
            return connection
    except Error as e:
        logger.error(f"Error connecting to MySQL: {e}")
        return None

def execute_query(query, params=None, fetch=False, fetch_one=False):
    connection = create_connection()
    if connection is None:
        logger.error("No database connection")
        if fetch or fetch_one:
            return [] if fetch else None
        else:
            return False
            
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(query, params or ())
        
        if fetch_one:
            result = cursor.fetchone()
            logger.info("Query executed successfully. Fetched one row.")
            return result
        elif fetch:
            result = cursor.fetchall()
            logger.info(f"Query executed successfully. Fetched {len(result)} rows.")
            return result
        else:
            connection.commit()
            # For INSERT queries, return lastrowid if available
            if query.strip().upper().startswith('INSERT'):
                result = cursor.lastrowid or True
            else:
                # For UPDATE/DELETE queries, return True if rows were affected
                result = cursor.rowcount > 0
            logger.info(f"Query executed successfully. Rows affected: {cursor.rowcount}")
            return result
    except Error as e:
        logger.error(f"Error executing query: {e}")
        logger.error(f"Query: {query}")
        logger.error(f"Params: {params}")
        connection.rollback()
        if fetch_one:
            return None
        elif fetch:
            return []
        else:
            return False
    finally:
        cursor.close()
        connection.close()

# Database initialization function
def initialize_database():
    """Initialize database with required tables and columns"""
    try:
        # Check and add missing columns to packages table
        package_columns = [
            ('is_active', 'BOOLEAN DEFAULT TRUE'),
            ('max_slots', 'INT DEFAULT 0')
        ]
        
        for column_name, column_def in package_columns:
            check_column_query = """
            SELECT COUNT(*) as exists_flag 
            FROM information_schema.columns 
            WHERE table_schema = 'tourbook' 
            AND table_name = 'packages' 
            AND column_name = %s
            """
            result = execute_query(check_column_query, (column_name,), fetch=True)
            
            if result and result[0]['exists_flag'] == 0:
                alter_query = f"ALTER TABLE packages ADD COLUMN {column_name} {column_def}"
                execute_query(alter_query)
                logger.info(f"Added column {column_name} to packages table")
        
        # Only create essential tables (remove all the new feature tables)
        essential_tables = {
            'package_images': """
                CREATE TABLE IF NOT EXISTS package_images (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    package_id INT NOT NULL,
                    image_url VARCHAR(255) NOT NULL,
                    is_primary BOOLEAN DEFAULT FALSE,
                    display_order INT DEFAULT 0,
                    FOREIGN KEY (package_id) REFERENCES packages(id) ON DELETE CASCADE
                )
            """
        }
        
        for table_name, create_query in essential_tables.items():
            execute_query(create_query)
            logger.info(f"Created/verified table: {table_name}")
        
        # Create basic indexes for performance
        indexes = [
            "CREATE INDEX idx_bookings_user_id ON bookings(user_id)",
            "CREATE INDEX idx_bookings_package_id ON bookings(package_id)",
            "CREATE INDEX idx_feedback_user_id ON feedback(user_id)",
            "CREATE INDEX idx_feedback_package_id ON feedback(package_id)",
            "CREATE INDEX idx_packages_destination ON packages(destination)",
            "CREATE INDEX idx_packages_category ON packages(category)"
        ]

        # Single loop for index creation with proper error handling
        for index_query in indexes:
            try:
                execute_query(index_query)
                logger.info(f"Created index: {index_query}")
            except Exception as e:
                if "Duplicate key name" in str(e) or "already exists" in str(e):
                    logger.info(f"Index already exists: {index_query}")
                else:
                    logger.warning(f"Failed to create index {index_query}: {e}")
        
        # Update existing packages with default values if needed
        update_packages = """
        UPDATE packages 
        SET is_active = COALESCE(is_active, TRUE),
            max_slots = COALESCE(max_slots, available_slots)
        """
        execute_query(update_packages)
        logger.info("Updated existing packages with default values")
        
        logger.info("Database initialization completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        return False

initialize_database()