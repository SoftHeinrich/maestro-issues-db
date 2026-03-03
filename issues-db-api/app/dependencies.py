import os
from pymongo import MongoClient
import gridfs
from app.schemas import (
    issue_labels_collection_schema,
    tags_collection_schema,
    projects_collection_schema,
    dl_models_collection_schema,
    embeddings_collection_schema,
    users_collection_schema,
    files_collection_schema,
    repo_info_collection_schema,
)

if os.environ.get("DOCKER", False):
    mongo_client = MongoClient(os.environ["MONGO_URL"])
else:
    mongo_client = MongoClient("mongodb://localhost:27017")

jira_repos_db = mongo_client["JiraRepos"]
mining_add_db = mongo_client["MiningDesignDecisions"]
fs = gridfs.GridFS(mongo_client["MiningDesignDecisions"])

issue_labels_collection = mongo_client["MiningDesignDecisions"]["IssueLabels"]
repo_info_collection = mongo_client["MiningDesignDecisions"]["RepoInfo"]
tags_collection = mongo_client["MiningDesignDecisions"]["Tags"]
projects_collection = mongo_client["MiningDesignDecisions"]["Projects"]
models_collection = mongo_client["MiningDesignDecisions"]["DLModels"]
embeddings_collection = mongo_client["MiningDesignDecisions"]["DLEmbeddings"]
files_collection = mongo_client["MiningDesignDecisions"]["Files"]
statistics_collection = mongo_client["Statistics"]["Statistics"]
users_collection = mongo_client["Users"]["Users"]

# Create non-existing collections with schema validation
existing_collections = mining_add_db.list_collection_names()
if "IssueLabels" not in existing_collections:
    mining_add_db.create_collection(
        "IssueLabels", validator=issue_labels_collection_schema
    )
if "RepoInfo" not in existing_collections:
    mining_add_db.create_collection("RepoInfo", validator=repo_info_collection_schema)
if "Tags" not in existing_collections:
    mining_add_db.create_collection("Tags", validator=tags_collection_schema)
if "Projects" not in existing_collections:
    mining_add_db.create_collection("Projects", validator=projects_collection_schema)
if "DLModels" not in existing_collections:
    mining_add_db.create_collection("DLModels", validator=dl_models_collection_schema)
if "DLEmbeddings" not in existing_collections:
    mining_add_db.create_collection(
        "DLEmbeddings", validator=embeddings_collection_schema
    )
if "Files" not in existing_collections:
    mining_add_db.create_collection("Files", validator=files_collection_schema)

if "Users" not in mongo_client["Users"].list_collection_names():
    mongo_client["Users"].create_collection("Users", validator=users_collection_schema)

# Create indexes
for repo in jira_repos_db.list_collection_names():
    jira_repos_db[repo].create_index("id")
