import psycopg2
import os

# Database connection parameters
DB_NAME = 'issues'
DB_USER = 'postgres'
DB_PASSWORD = 'pass'
DB_HOST = 'localhost'
DB_PORT = '5432'

# Criteria for identifying bot comments
bot_keywords = ['bot', 'git', 'system', 'AI']
bot_authors_file = 'known_bot_authors.txt'
BATCH_SIZE = 10000  # Adjust batch size based on memory and performance

def load_known_bot_authors():
    if not os.path.exists(bot_authors_file):
        return set()
    with open(bot_authors_file, 'r') as file:
        return set(file.read().splitlines())

def save_known_bot_authors(bot_authors):
    with open(bot_authors_file, 'w') as file:
        file.write('\n'.join(bot_authors))

def append_known_bot_author(author_name):
    with open(bot_authors_file, 'a') as file:
        file.write(f"{author_name}\n")

def is_bot_comment(author_name, author_display_name, body):
    for keyword in bot_keywords:
        if author_name and keyword in author_name.lower():
            return True
        if author_display_name and keyword in author_display_name.lower():
            return True
    
    for keyword in ["this message is automatically generated",]:
        if body and keyword in body.lower():
            return True
    return False

def process_batch(cursor, comments, known_bot_authors):
    for comment in comments:
        comment_id, author_name, author_display_name, body = comment
        if author_display_name in known_bot_authors:
            cursor.execute("UPDATE issues_comments SET is_bot = TRUE WHERE id = %s", (comment_id,))
            
        #     is_bot = True
        # else:
        #     is_bot = is_bot_comment(author_name, author_display_name, body)
        #     if is_bot:
        #         known_bot_authors.add(author_display_name)
        #         append_known_bot_author(author_display_name)

        # if is_bot:
        #     cursor.execute("UPDATE comments SET is_bot = TRUE WHERE id = %s", (comment_id,))

def main():
    known_bot_authors = load_known_bot_authors()

    # Connect to the database
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )
    cursor = conn.cursor()

    # Fetch comments in batches
    offset = 0

    while True:
        cursor.execute(
            "SELECT id, author_name, author_display_name, body FROM issues_comments ORDER BY id LIMIT %s OFFSET %s",
            (BATCH_SIZE, offset)
        )
        comments = cursor.fetchall()
        if not comments:
            break

        process_batch(cursor, comments, known_bot_authors)
        conn.commit()  # Commit after each batch
        offset += BATCH_SIZE

    # Save the updated known bot authors list
    save_known_bot_authors(known_bot_authors)

    # Close the cursor and connection
    cursor.close()
    conn.close()
    
if __name__ == "__main__":
    main()