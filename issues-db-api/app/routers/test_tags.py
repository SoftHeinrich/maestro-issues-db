from .test_util import client
from .test_util import (
    setup_users_db,
    restore_dbs,
    get_auth_header,
    auth_test_post,
    auth_test_delete,
)
from app.dependencies import (
    tags_collection,
    projects_collection,
    issue_labels_collection,
)


def setup_db():
    tags_collection.insert_one(
        {"_id": "tag", "description": "text", "type": "manual-tag"}
    )
    projects_collection.insert_one(
        {"_id": "Apache-HADOOP", "ecosystem": "Apache", "key": "HADOOP", "additional_properties": {}}
    )


def test_get_tags():
    restore_dbs()
    setup_db()
    setup_users_db()

    # Get tags
    assert client.get("/tags").json() == {
        "tags": [
            {"name": "tag", "description": "text", "type": "manual-tag"},
            {"name": "Apache-HADOOP", "description": "", "type": "project"},
            {"name": "test", "description": "", "type": "author"},
            {"name": "other-user", "description": "", "type": "author"},
        ]
    }

    restore_dbs()


def test_create_tag():
    restore_dbs()
    setup_users_db()

    auth_test_post("/tags")
    headers = get_auth_header()

    # Create new tag
    payload = {"tag": "tag", "description": "text"}
    assert client.post("/tags", headers=headers, json=payload).status_code == 200
    assert tags_collection.find_one({"_id": "tag"}) == {
        "_id": "tag",
        "description": "text",
        "type": "manual-tag",
    }

    # Duplicate tag
    assert client.post("/tags", headers=headers, json=payload).status_code == 409
    assert tags_collection.find_one({"_id": "tag"}) == {
        "_id": "tag",
        "description": "text",
        "type": "manual-tag",
    }

    # Tag in projects collection
    projects_collection.insert_one(
        {"_id": "Apache-YARN", "ecosystem": "Apache", "key": "YARN", "additional_properties": {}}
    )
    payload = {"tag": "Apache-YARN", "description": "text"}
    assert client.post("/tags", headers=headers, json=payload).status_code == 409

    restore_dbs()


def test_get_tag():
    restore_dbs()
    setup_db()

    # Get tags
    assert client.get("/tags/tag").json() == {
        "tag": {"name": "tag", "description": "text", "type": "manual-tag"}
    }
    assert client.get("/tags/non-existent-tag").status_code == 404

    restore_dbs()


def test_update_tag():
    restore_dbs()
    setup_users_db()
    setup_db()

    auth_test_post("/tags/add-tags")
    headers = get_auth_header()

    # Get tags
    assert (
        client.post(
            "/tags/tag", headers=headers, json={"description": "new-text"}
        ).status_code
        == 200
    )
    assert tags_collection.find_one({"_id": "tag"})["description"] == "new-text"
    assert (
        client.post(
            "/tags/non-existent-tag", headers=headers, json={"description": "new-text"}
        ).status_code
        == 404
    )

    restore_dbs()


def test_delete_tag():
    restore_dbs()
    setup_users_db()
    setup_db()

    auth_test_delete("/tags/tag")
    headers = get_auth_header()

    # Insert issue with the tag
    issue_labels_collection.insert_one({"_id": "Apache-01", "tags": ["tag"]})

    # Delete tag
    assert client.delete("/tags/tag", headers=headers).status_code == 200
    assert tags_collection.find_one({"_id": "tag"}) is None
    assert issue_labels_collection.find_one({"_id": "Apache-01"})["tags"] == []

    # Non-existing tag
    assert client.delete("/tags/tag", headers=headers).status_code == 404

    restore_dbs()
