import pymongo
import psycopg2
from psycopg2 import sql
import os

# MongoDB connection details (match the Docker Compose settings)
mongo_client = pymongo.MongoClient("mongodb://localhost:27017/")
mongo_db = mongo_client["JiraRepos"]
mongo_collection = mongo_db["Apache"]

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
# Create table in PostgreSQL (adjust the schema as necessary)
create_table_query = '''
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
);
'''
pg_cursor.execute(create_table_query)
pg_conn.commit()
print("issues_comments table created successfully")

# Fetch data from MongoDB (limit to 10 documents)
mongo_data = mongo_collection.find({ "fields.comments": { "$elemMatch": { "$exists": True } } })

print("mongodb data retrived successfully")
# Check if any documents were returned
if mongo_data.count == 0:
    print("Error: No documents found in MongoDB matching the query.")
# Insert data into PostgreSQL
bot_authors_file = 'known_bot_authors.txt'
def load_known_bot_authors():
    if not os.path.exists(bot_authors_file):
        return set()
    with open(bot_authors_file, 'r') as file:
        return set(file.read().splitlines())
known_bot_authors = load_known_bot_authors()

count=0


for doc in mongo_data:
    insert_query = sql.SQL('''
        INSERT INTO issues_comments (mongo_id, issue_id, comment_id, author_name, author_display_name, author_time_zone, body, is_bot, created, updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''')
    
    comments = doc.get("fields", {}).get("comments", [])
    for i, comment in enumerate(comments, 1):
        if comment.get("author", {}).get("displayName") in known_bot_authors:
            is_bot = True
        else:
            is_bot= False
        comment_data = (
                str(doc["_id"]),
                doc["key"],
                comment.get("id"),
                comment.get("author", {}).get("name"),
                comment.get("author", {}).get("displayName"),
                comment.get("author", {}).get("timeZone"),
                comment.get("body"),
                is_bot,
                comment.get("created"),
                comment.get("updated")
            )
        pg_cursor.execute(insert_query, comment_data)
    
    count = count + 1
    if count%1000 == 0:
        print(f"added comments for {count} issues")

# Commit the transaction and close the connections
pg_conn.commit()
pg_cursor.close()
pg_conn.close()
mongo_client.close()
