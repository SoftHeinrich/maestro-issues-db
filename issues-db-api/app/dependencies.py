import json
import logging
import os
import threading
from collections.abc import Sequence

import gridfs
from bson import ObjectId
from pymongo import MongoClient
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

log = logging.getLogger(__name__)


def _build_mongo_client() -> MongoClient:
    server_selection_timeout_ms = int(
        os.environ.get("MONGO_SERVER_SELECTION_TIMEOUT_MS", "5000")
    )
    mongo_url = (
        os.environ["MONGO_URL"]
        if os.environ.get("DOCKER", False)
        else "mongodb://localhost:27017"
    )
    return MongoClient(
        mongo_url,
        connect=False,
        serverSelectionTimeoutMS=server_selection_timeout_ms,
    )


def _load_project_config() -> dict:
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "project_config.json",
    )
    with open(config_path) as handle:
        return json.load(handle)


class ActiveEcosystemsView(Sequence[str]):
    def __init__(self, configured_ecosystems: list[str] | None):
        self._configured_ecosystems = list(configured_ecosystems or [])

    def _resolve(self) -> list[str]:
        if self._configured_ecosystems:
            return list(self._configured_ecosystems)
        return jira_repos_db.list_collection_names()

    def __iter__(self):
        return iter(self._resolve())

    def __len__(self) -> int:
        return len(self._resolve())

    def __getitem__(self, index):
        return self._resolve()[index]

    def __contains__(self, item) -> bool:
        return item in self._resolve()

    def __repr__(self) -> str:
        return repr(self._resolve())


mongo_client = _build_mongo_client()

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

project_config = _load_project_config()
active_ecosystems = ActiveEcosystemsView(project_config.get("ecosystems"))
active_projects = project_config.get("projects") or []
active_model_id = project_config.get("model_id") or None
_init_lock = threading.Lock()
_initialized = False


def _ensure_collection(db, name: str, validator: dict) -> None:
    if name not in db.list_collection_names():
        db.create_collection(name, validator=validator)


def _ensure_schema_collections() -> None:
    _ensure_collection(mining_add_db, "IssueLabels", issue_labels_collection_schema)
    _ensure_collection(mining_add_db, "RepoInfo", repo_info_collection_schema)
    _ensure_collection(mining_add_db, "Tags", tags_collection_schema)
    _ensure_collection(mining_add_db, "Projects", projects_collection_schema)
    _ensure_collection(mining_add_db, "DLModels", dl_models_collection_schema)
    _ensure_collection(mining_add_db, "DLEmbeddings", embeddings_collection_schema)
    _ensure_collection(mining_add_db, "Files", files_collection_schema)
    _ensure_collection(mongo_client["Users"], "Users", users_collection_schema)


def _ensure_repo_indexes() -> None:
    available_collections = set(jira_repos_db.list_collection_names())
    for repo in active_ecosystems:
        if repo in available_collections:
            jira_repos_db[repo].create_index("id")


def _prune_database_to_project_config() -> None:
    if active_projects:
        project_tags = [
            f"{eco}-{proj}"
            for eco in active_ecosystems
            for proj in active_projects
        ]
        deleted = issue_labels_collection.delete_many({"tags": {"$nin": project_tags}})
        if deleted.deleted_count:
            log.warning(
                "[startup] Removed %s IssueLabels outside configured projects",
                deleted.deleted_count,
            )

        deleted = projects_collection.delete_many({"key": {"$nin": active_projects}})
        if deleted.deleted_count:
            log.warning(
                "[startup] Removed %s Projects outside configured projects",
                deleted.deleted_count,
            )

    if active_model_id:
        keep_id = ObjectId(active_model_id)
        model = models_collection.find_one({"_id": keep_id}, {"versions": 1})
        if model:
            keep_file_ids = [ObjectId(version_id) for version_id in (model.get("versions") or {})]
            deleted = mining_add_db["fs.chunks"].delete_many(
                {"files_id": {"$nin": keep_file_ids}}
            )
            if deleted.deleted_count:
                log.warning(
                    "[startup] Removed %s GridFS chunks for non-configured models",
                    deleted.deleted_count,
                )
            deleted = mining_add_db["fs.files"].delete_many(
                {"_id": {"$nin": keep_file_ids}}
            )
            if deleted.deleted_count:
                log.warning(
                    "[startup] Removed %s GridFS files for non-configured models",
                    deleted.deleted_count,
                )


def initialize_database_state() -> None:
    global _initialized
    if _initialized:
        return

    with _init_lock:
        if _initialized:
            return

        _ensure_schema_collections()
        _ensure_repo_indexes()

        if os.environ.get("ISSUES_DB_APPLY_PROJECT_CONFIG_PRUNING", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            _prune_database_to_project_config()
        elif active_projects or active_model_id:
            log.info(
                "Project-config pruning is disabled by default; set "
                "ISSUES_DB_APPLY_PROJECT_CONFIG_PRUNING=true to enable it explicitly."
            )

        _initialized = True
