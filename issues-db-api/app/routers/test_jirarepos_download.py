from fastapi.testclient import TestClient

from app import app
from app.dependencies import repo_info_collection
from .test_util import (
    setup_users_db,
    restore_dbs,
    get_auth_header,
    auth_test_post,
    auth_test_put,
    auth_test_delete,
)

client = TestClient(app.app)


def setup_db():
    repo_info_collection.insert_one(
        {
            "_id": "name_of_repo",
            "repo_url": "url_of_repo",
            "download_date": None,
            "batch_size": 1000,
            "query_wait_time_minutes": 0.0,
        }
    )


def test_get_repo_info():
    restore_dbs()
    setup_db()

    # Get repo info
    assert client.get("/jira-repos").json() == [
        {
            "repo_name": "name_of_repo",
            "repo_url": "url_of_repo",
            "download_date": None,
            "batch_size": 1000,
            "query_wait_time_minutes": 0.0,
        }
    ]

    restore_dbs()


def test_add_repo():
    restore_dbs()
    setup_users_db()

    auth_test_post("/jira-repos")
    headers = get_auth_header()

    # Insert repo
    payload = {
        "repo_name": "name_of_repo",
        "repo_url": "url_of_repo",
        "download_date": None,
        "batch_size": 1000,
        "query_wait_time_minutes": 0.0,
    }
    assert client.post("/jira-repos", headers=headers, json=payload).status_code == 200
    assert repo_info_collection.find_one({"_id": "name_of_repo"}) == {
        "_id": "name_of_repo",
        "repo_url": "url_of_repo",
        "download_date": None,
        "batch_size": 1000,
        "query_wait_time_minutes": 0.0,
    }

    restore_dbs()


def test_update_repo():
    restore_dbs()
    setup_db()
    setup_users_db()

    auth_test_put("/jira-repos/name_of_repo")
    headers = get_auth_header()

    # Update repo
    payload = {
        "repo_url": "new_url_of_repo",
        "download_date": "2023-01-01",
        "batch_size": 42,
        "query_wait_time_minutes": 0.42,
    }
    assert (
        client.put(
            "/jira-repos/name_of_repo", headers=headers, json=payload
        ).status_code
        == 200
    )
    assert repo_info_collection.find_one({"_id": "name_of_repo"}) == {
        "_id": "name_of_repo",
        "repo_url": "new_url_of_repo",
        "download_date": "2023-01-01",
        "batch_size": 42,
        "query_wait_time_minutes": 0.42,
    }

    # Invalid updates
    payload = {
        "repo_url": "new_url_of_repo",
        "download_date": "2023-1-01",
        "batch_size": 42,
        "query_wait_time_minutes": 0.42,
    }
    assert (
        client.put(
            "/jira-repos/name_of_repo", headers=headers, json=payload
        ).status_code
        == 422
    )
    payload = {
        "repo_url": "new_url_of_repo",
        "download_date": "2023-01-01",
        "batch_size": 0,
        "query_wait_time_minutes": 0.42,
    }
    assert (
        client.put(
            "/jira-repos/name_of_repo", headers=headers, json=payload
        ).status_code
        == 422
    )
    payload = {
        "repo_url": "new_url_of_repo",
        "download_date": "2023-01-01",
        "batch_size": 42,
        "query_wait_time_minutes": -0.42,
    }
    assert (
        client.put(
            "/jira-repos/name_of_repo", headers=headers, json=payload
        ).status_code
        == 422
    )

    restore_dbs()


def test_delete_repo():
    restore_dbs()
    setup_db()
    setup_users_db()

    auth_test_delete("/jira-repos/name_of_repo")
    headers = get_auth_header()

    # Delete repo
    assert client.delete("/jira-repos/name_of_repo", headers=headers).status_code == 200
    assert repo_info_collection.find_one({"_id": "name_of_repo"}) is None

    # Invalid delete
    assert client.delete("/jira-repos/name_of_repo", headers=headers).status_code == 404

    restore_dbs()
