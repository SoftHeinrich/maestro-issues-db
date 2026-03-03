import psycopg2
import pymongo
import json
import os

cwd = os.getcwd()
print(cwd)
# Read the JSON file
with open("sampleApache.json", "r") as json_file:
    data = json.load(json_file)

# mongo_keys = [item["key"] for item in data]
# print(mongo_keys)

mongo_issues_ids = ["Apache-"+ item['id'] for item in data]

# MongoDB connection details
mongo_client = pymongo.MongoClient("mongodb://localhost:27017/")
labels_db = mongo_client["MiningDesignDecisions"]
labels_collection = labels_db["IssueLabels"]

# Fetch predictions from MongoDB for the issue keys
mongo_data = list(labels_collection.find({"_id": {"$in": list(mongo_issues_ids)}}, {"_id": 1, "predictions": 1}))

# Extract issue keys from the JSON data
issue_keys = [item['key'] for item in data]

# issue_keys = {item.get('key') for item in data if item.get('key')}

# Connect to PostgreSQL
pg_conn = psycopg2.connect(
    dbname="issues",
    user="postgres",
    password="pass",
    host="localhost",
    port="5432"
)
pg_cursor = pg_conn.cursor()

# Prepare the SQL query to fetch issue_comments along with classification_results
query = """
SELECT ic.id AS comment_id, ic.issue_id, ic.body, cr.classification_result 
FROM issues_comments ic
LEFT JOIN classification_results cr ON ic.id = cr.issue_comment_id
WHERE ic.is_bot = false 
AND LENGTH(ic.body) > 200 
AND ic.issue_id = ANY(%s)
ORDER BY ic.id;
"""

# Execute the query with the issue_keys as pidarameter
pg_cursor.execute(query, (list(issue_keys),))

# Fetch the results
psql_data = pg_cursor.fetchall()

# Close the cursor and connection
pg_cursor.close()
pg_conn.close()


# print(len(psql_data))
# print(psql_data[0])
psql_comments_data = {}
for item in psql_data:
    if str(item[1]) in psql_comments_data:
        psql_comments_data[str(item[1])].append(item)
    else:
        psql_comments_data[str(item[1])] = [item]
        
print(len(psql_comments_data))
new_mongo_data  = {}
for item in mongo_data:
    new_mongo_data[item["_id"]] = item["predictions"]
    
new_data = []
for item in data:
    comments_data = []
    
    if "comments" in item["fields"]:
        comments = item["fields"]["comments"]
        for comment in comments:
            # Extract only the necessary fields from each comment
            comment_details = {
                "author_name": comment["author"]["name"],
                "id": comment["id"],
                "body": comment["body"],
            }
            comments_data.append(comment_details)
    comments_predictions = {}
    if item["key"] in psql_comments_data:
        comments_predictions = psql_comments_data[item["key"]]
    new_data.append({
        "_id": item["_id"],
        "key": item["key"],
        "id": item["id"],
        "description" : item["fields"]["description"],
        "predictions": new_mongo_data["Apache-"+item["id"]],
        "comments":comments_data,
        "comments_predictions":comments_predictions
    })

with open('sample_apache_data.json', 'w') as json_file:
    json.dump(new_data, json_file, default=str, indent=4)

