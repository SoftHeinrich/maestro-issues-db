import json
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

# Load project config — controls which ecosystems/projects are active
_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "project_config.json")
with open(_config_path) as _f:
    project_config = json.load(_f)

# Only the configured ecosystems, or all if not specified
active_ecosystems = project_config.get("ecosystems") or jira_repos_db.list_collection_names()
active_projects = project_config.get("projects") or []
active_model_id = project_config.get("model_id") or None

# Create indexes only for active ecosystems
for repo in active_ecosystems:
    if repo in jira_repos_db.list_collection_names():
        jira_repos_db[repo].create_index("id")

# Trim database to only configured projects/model on startup
if active_projects:
    _project_tags = [
        f"{eco}-{proj}"
        for eco in active_ecosystems
        for proj in active_projects
    ]
    _del = issue_labels_collection.delete_many(
        {"tags": {"$nin": _project_tags}}
    )
    if _del.deleted_count:
        print(f"[startup] Removed {_del.deleted_count} IssueLabels outside configured projects")

    _del = projects_collection.delete_many(
        {"key": {"$nin": active_projects}}
    )
    if _del.deleted_count:
        print(f"[startup] Removed {_del.deleted_count} Projects outside configured projects")

if active_model_id:
    from bson import ObjectId
    _keep_id = ObjectId(active_model_id)
    _model = models_collection.find_one({"_id": _keep_id}, {"versions": 1})
    if _model:
        _keep_file_ids = [ObjectId(vid) for vid in (_model.get("versions") or {})]
        _del = mining_add_db["fs.chunks"].delete_many(
            {"files_id": {"$nin": _keep_file_ids}}
        )
        if _del.deleted_count:
            print(f"[startup] Removed {_del.deleted_count} GridFS chunks for non-configured models")
        _del = mining_add_db["fs.files"].delete_many(
            {"_id": {"$nin": _keep_file_ids}}
        )
        if _del.deleted_count:
            print(f"[startup] Removed {_del.deleted_count} GridFS files for non-configured models")
