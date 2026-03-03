import pymongo
import json
from bson.objectid import ObjectId

# MongoDB connection details
mongo_client = pymongo.MongoClient("mongodb://localhost:27017/")
mongo_db = mongo_client["JiraRepos"]
source_collection = mongo_db["Apache"]

# Name of the new dummy collection
new_collection_name = "Apache_Copy"
destination_collection = mongo_db[new_collection_name]

# Path to the JSON file containing the documents
json_file_path = 'sample_data.json'

def get_ids_from_json(file_path):
    ids = []
    with open(file_path, 'r') as file:
        data = json.load(file)
        # Extracting the '_id' from the JSON content
        if isinstance(data, list):  # If the JSON contains a list of documents
            ids = [doc['_id'] for doc in data if '_id' in doc]
        elif isinstance(data, dict) and '_id' in data:  # If the JSON contains a single document
            ids = [data['_id']]
    return ids

# Get IDs from the JSON file
ids_to_copy = get_ids_from_json(json_file_path)

# Copy documents from the source collection to the new collection
for doc_id in ids_to_copy:
    try:
        # Convert string ID to ObjectId
        object_id = ObjectId(doc_id)
        
        # Find the document in the source collection
        document = source_collection.find_one({"_id": object_id})
        
        if document:
            # Insert the document into the new collection
            destination_collection.insert_one(document)
            print(f"Document with _id {doc_id} copied successfully.")
        else:
            print(f"No document found with _id {doc_id}.")
            
    except Exception as e:
        print(f"An error occurred: {e}")

print("Document copying process completed.")
