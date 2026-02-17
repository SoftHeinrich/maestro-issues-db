from app import app
from app.dependencies import (
    users_collection,
    issue_labels_collection,
    models_collection,
    jira_repos_db,
    projects_collection,
    tags_collection,
    mining_add_db,
    embeddings_collection,
    mongo_client,
    files_collection,
    repo_info_collection,
)
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
from fastapi.testclient import TestClient

from .authentication import get_password_hash

client = TestClient(app.app)


def setup_users_db():
    users_collection.insert_one(
        {"_id": "test", "hashed_password": get_password_hash("test")}
    )
    users_collection.insert_one(
        {"_id": "other-user", "hashed_password": get_password_hash("other-user")}
    )


def restore_dbs():
    users_collection.drop()
    issue_labels_collection.drop()
    models_collection.drop()
    jira_repos_db["Apache"].drop()
    repo_info_collection.drop()
    projects_collection.drop()
    tags_collection.drop()
    mining_add_db["fs_file"].drop()
    mining_add_db["fs_chunks"].drop()
    embeddings_collection.drop()
    files_collection.drop()

    mining_add_db.create_collection(
        "IssueLabels", validator=issue_labels_collection_schema
    )
    mining_add_db.create_collection("RepoInfo", validator=repo_info_collection_schema)
    mining_add_db.create_collection("Tags", validator=tags_collection_schema)
    mining_add_db.create_collection("Projects", validator=projects_collection_schema)
    mining_add_db.create_collection("DLModels", validator=dl_models_collection_schema)
    mining_add_db.create_collection(
        "DLEmbeddings", validator=embeddings_collection_schema
    )
    mining_add_db.create_collection("Files", validator=files_collection_schema)
    mongo_client["Users"].create_collection("Users", validator=users_collection_schema)


def setup_dbs():
    restore_dbs()
    setup_users_db()

    jira_repos_db["Apache"].insert_one({"_id": 0, "key": "CASSANDRA-0"})

    issue_labels_collection.insert_one(
        {
            "_id": "Apache-0",
            "existence": None,
            "property": None,
            "executive": None,
            "tags": ["Apache-CASSANDRA"],
        }
    )

    projects_collection.insert_one(
        {
            "_id": "Apache-CASSANDRA",
            "ecosystem": "Apache",
            "key": "CASSANDRA",
            "additional_properties": {
                "property1": "value",
                "property2": ["value1", "value2"],
            },
        }
    )


def get_auth_header():
    response = client.post(
        "/token", files={"username": (None, "test"), "password": (None, "test")}
    )
    return {"Authorization": f'bearer {response.json()["access_token"]}'}


def get_auth_header_other_user():
    response = client.post(
        "/token",
        files={"username": (None, "other-user"), "password": (None, "other-user")},
    )
    return {"Authorization": f'bearer {response.json()["access_token"]}'}


def auth_test_post(endpoint: str, payload=None):
    client.cookies.clear()
    response = client.post(endpoint, json=payload)
    assert response.status_code in (401, 422)


def auth_test_patch(endpoint: str, payload=None):
    client.cookies.clear()
    response = client.patch(endpoint, json=payload)
    assert response.status_code in (401, 422)


def auth_test_put(endpoint: str, payload=None):
    client.cookies.clear()
    response = client.put(endpoint, json=payload)
    assert response.status_code in (401, 422)


def auth_test_delete(endpoint: str):
    client.cookies.clear()
    response = client.delete(endpoint)
    assert response.status_code in (401, 422)
