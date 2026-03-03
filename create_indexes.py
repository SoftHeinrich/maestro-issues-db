from pymongo import MongoClient

mongo_client = MongoClient('mongodb://localhost:27017')
for repo in mongo_client['JiraRepos'].list_collection_names():
    mongo_client['JiraRepos'][repo].create_index('id')
