from .test_util import (
    client,
    setup_dbs,
    get_auth_header,
    auth_test_post,
    auth_test_put,
    auth_test_delete,
)
from app.dependencies import projects_collection, issue_labels_collection


def test_get_projects():
    setup_dbs()
    url = "/projects"

    assert client.get(url).json() == [
        {
            "ecosystem": "Apache",
            "key": "CASSANDRA",
            "additional_properties": {
                "property1": "value",
                "property2": ["value1", "value2"],
            },
        }
    ]


def test_create_project():
    setup_dbs()
    url = "/projects"
    auth_test_post(url)
    headers = get_auth_header()

    payload = {
        "ecosystem": "Apache",
        "key": "HADOOP",
        "additional_properties": {
            "property1": "value",
            "property2": ["value1", "value2"],
        },
    }
    assert client.post(url, headers=headers, json=payload).status_code == 200
    assert projects_collection.find_one({"_id": "Apache-HADOOP"}) == {
        "_id": "Apache-HADOOP",
        "ecosystem": "Apache",
        "key": "HADOOP",
        "additional_properties": {
            "property1": "value",
            "property2": ["value1", "value2"],
        },
    }


def test_get_project():
    setup_dbs()
    url = "/projects/Apache/CASSANDRA"

    assert client.get(url).json() == {
        "ecosystem": "Apache",
        "key": "CASSANDRA",
        "additional_properties": {
            "property1": "value",
            "property2": ["value1", "value2"],
        },
    }


def test_update_project():
    setup_dbs()
    url = "/projects/Apache/CASSANDRA"
    auth_test_put(url)
    headers = get_auth_header()

    payload = {
        "ecosystem": "Apache",
        "key": "CASSANDRA",
        "additional_properties": {
            "property1": "42",
            "property2": ["42", "43"],
        },
    }
    client.put(url, headers=headers, json=payload)
    assert projects_collection.find_one({"_id": "Apache-CASSANDRA"}) == {
        "_id": "Apache-CASSANDRA",
        "ecosystem": "Apache",
        "key": "CASSANDRA",
        "additional_properties": {
            "property1": "42",
            "property2": ["42", "43"],
        },
    }
    assert issue_labels_collection.find_one({"_id": "Apache-0"})["tags"] == [
        "Apache-CASSANDRA",
        "project-ecosystem=Apache",
        "project-key=CASSANDRA",
        "project-property1=42",
        "project-property2=42",
        "project-property2=43",
    ]


def test_delete_project():
    setup_dbs()
    url = "/projects/Apache/CASSANDRA"
    auth_test_delete(url)
    headers = get_auth_header()

    assert client.delete(url, headers=headers).status_code == 200
    assert projects_collection.find_one({"_id": "Apache-CASSANDRA"}) is None
