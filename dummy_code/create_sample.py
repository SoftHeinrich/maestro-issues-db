import pymongo
import json

# MongoDB connection details
mongo_client = pymongo.MongoClient("mongodb://localhost:27017/")
labels_db = mongo_client["JiraRepos"]
labels_collection = labels_db["SampleApache"]

# Fetch a sample of 300 documents
sample_size = 700
pipeline = [{"$sample": {"size": sample_size}}]
sample_documents = list(labels_collection.aggregate(pipeline))

# Save the sample to a JSON file
with open('sampleApache.json', 'w') as json_file:
    json.dump(sample_documents, json_file, default=str, indent=4)

print(f"A sample of {sample_size} documents has been saved to 'sample_700.json'.")
