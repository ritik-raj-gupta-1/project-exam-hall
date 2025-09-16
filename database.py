import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get the database URL from environment variables
DATABASE_URL = os.getenv("DATABASE_URL")

# --- Modified Section ---
# Use a global variable to store the pool instance to prevent re-initialization
db_pool = None

def initialize_db_pool():
    """
    Initializes the database connection pool if it doesn't already exist.
    """
    global db_pool
    if db_pool is None:
        try:
            db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, dsn=DATABASE_URL)
            print("Database connection pool created successfully.")
        except (Exception, psycopg2.DatabaseError) as error:
            print("Error while connecting to PostgreSQL:", error)
            db_pool = None

def get_db_connection():
    """
    Retrieves a connection from the pool.
    """
    if db_pool is None:
        initialize_db_pool()
    if db_pool:
        return db_pool.getconn()
    raise Exception("Database pool is not initialized.")

def put_db_connection(conn):
    """
    Returns a connection to the pool.
    """
    if db_pool and conn:
        db_pool.putconn(conn)