import psycopg2
from psycopg2 import sql
# PostgreSQL connection details (match the Docker Compose settings)
pg_conn = psycopg2.connect(
    dbname="issues",
    user="postgres",
    password="pass",
    host="localhost",
    port="5432"
)
pg_cursor = pg_conn.cursor()
print("connected to postgress")

def create_tables():
    commands = (
        """
        CREATE TABLE IF NOT EXISTS issues_comments (
            id SERIAL PRIMARY KEY,
            mongo_id TEXT,
            issue_id TEXT,
            comment_id TEXT,
            author_name TEXT,
            author_display_name TEXT,
            author_time_zone TEXT,
            body TEXT,
            is_bot BOOLEAN DEFAULT FALSE,
            created TIMESTAMP,
            updated TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS classification_results (
            id SERIAL PRIMARY KEY,
            issue_comment_id INT REFERENCES issues_comments(id),
            model_name TEXT,
            model_version TEXT,
            classification_result JSONB,
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_classification_results_issue_comment_id 
        ON classification_results(issue_comment_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_classification_results_model 
        ON classification_results(model_name, model_version)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_classification_results_jsonb_path 
        ON classification_results USING gin (classification_result jsonb_path_ops)
        """
    )
    conn = None
    try:
        conn = psycopg2.connect(
            dbname="issues",
            user="postgres",
            password="pass",
            host="localhost",
            port="5432"
        )
        cur = conn.cursor()
        for command in commands:
            cur.execute(command)
        cur.close()
        conn.commit()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()
            
if __name__ == "__main__":
    create_tables()
    print("tables created_successfully")