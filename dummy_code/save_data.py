import psycopg2
import json


# SQL query to run
QUERY = """
SELECT 
    ic.author_display_name,
    ic.body as comment,
    cr.classification_result,
    cr.classification_result->'property'->'prediction' as property,
    cr.classification_result->'executive'->'prediction' as executive,
    cr.classification_result->'existence'->'prediction' as existence
FROM 
    issues_comments ic
JOIN 
    classification_results cr ON ic.id = cr.issue_comment_id
WHERE 
    cr.classification_result->'property'->>'prediction' = 'true'
    OR cr.classification_result->'executive'->>'prediction' = 'true'
    OR cr.classification_result->'existence'->>'prediction' = 'true'
ORDER BY 
    ic.id, cr.created DESC;
"""

def fetch_and_save_results(query, output_file):
    conn = None
    results = []
    try:
        conn = psycopg2.connect(
            dbname="issues",
            user="postgres",
            password="pass",
            host="localhost",
            port="5432"
        )
        cur = conn.cursor()
        
        # Execute the query
        cur.execute(query)
        
        # Fetch all the results
        rows = cur.fetchall()
        
        # Get column names from cursor
        colnames = [desc[0] for desc in cur.description]
        
        # Process the results into a list of dictionaries
        for row in rows:
            result = dict(zip(colnames, row))
            results.append(result)
        
        # Save results to a JSON file
        with open(output_file, 'w') as json_file:
            json.dump(results, json_file, indent=4)
        
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()

if __name__ == "__main__":
    output_file = 'classification_results.json'
    fetch_and_save_results(QUERY, output_file)
    print(f"Results saved to {output_file}")
