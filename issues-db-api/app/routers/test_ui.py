import pytest
from app.dependencies import (
    issue_labels_collection,
    jira_repos_db,
    models_collection,
    repo_info_collection,
)
from bson import ObjectId
from fastapi import HTTPException

from .test_util import restore_dbs
from .ui import get_ui_data, Query


def setup_db():
    model_id = ObjectId()
    version_id = ObjectId()
    comment_id1 = ObjectId()
    comment_id2 = ObjectId()
    issue_labels_collection.insert_one(
        {
            "_id": "Apache-1",
            "existence": True,
            "property": False,
            "executive": True,
            "tags": ["HADOOP", "has-label"],
            "comments": {
                str(comment_id1): {"author": "test", "comment": "Comment on HADOOP-01"}
            },
            "predictions": {
                f"{model_id}-{version_id}": {
                    "existence": {"prediction": False, "confidence": 0.42}
                }
            },
        }
    )
    issue_labels_collection.insert_one(
        {
            "_id": "Apache-2",
            "existence": None,
            "property": None,
            "executive": None,
            "tags": ["CASSANDRA", "has-label"],
            "comments": {
                str(comment_id2): {
                    "author": "test",
                    "comment": "Comment on CASSANDRA-01",
                }
            },
            "predictions": {
                f"{model_id}-{version_id}": {
                    "existence": {"prediction": False, "confidence": 0.43}
                }
            },
        }
    )
    issue_labels_collection.create_index(
        f"predictions.{model_id}-{version_id}.existence.confidence"
    )

    jira_repos_db["Apache"].insert_one(
        {
            "id": "1",
            "key": "HADOOP-1",
            "fields": {
                "summary": "Summary of HADOOP-1",
                "description": "Description of HADOOP-1",
            },
        }
    )
    jira_repos_db["Apache"].insert_one(
        {
            "id": "2",
            "key": "CASSANDRA-1",
            "fields": {
                "summary": "Summary of CASSANDRA-1",
                "description": "Description of CASSANDRA-1",
            },
        }
    )

    repo_info_collection.insert_one(
        {
            "_id": "Apache",
            "repo_url": "url_of_repo",
            "download_date": None,
            "batch_size": 1000,
            "query_wait_time_minutes": 0.0,
            "issue_link_prefix": "https://issues.apache.org/jira",
        }
    )

    return model_id, version_id, comment_id1, comment_id2


def test_ui():
    restore_dbs()
    model_id, version_id, comment_id1, comment_id2 = setup_db()

    # Version not specified
    payload = Query(
        filter={},
        sort=f"predictions.{model_id}-{version_id}.existence.confidence",
        sort_ascending=True,
        models=[f"{model_id}"],
        page=1,
        limit=2,
    )
    with pytest.raises(HTTPException):
        get_ui_data(payload)

    # Model not existing
    payload = Query(
        filter={},
        sort=f"predictions.{model_id}-{version_id}.existence.confidence",
        sort_ascending=True,
        models=[f"{model_id}-{version_id}"],
        page=1,
        limit=2,
    )
    with pytest.raises(HTTPException):
        get_ui_data(payload)

    # Insert model
    models_collection.insert_one(
        {
            "_id": model_id,
            "name": "model_name",
            "config": {"key": "value"},
            "versions": {},
            "performances": {},
        }
    )

    # Version not existing
    payload = Query(
        filter={},
        sort=f"predictions.{model_id}-{version_id}.existence.confidence",
        sort_ascending=True,
        models=[f"{model_id}-{version_id}"],
        page=1,
        limit=2,
    )
    with pytest.raises(HTTPException):
        get_ui_data(payload)

    # Insert version
    models_collection.update_one(
        {"_id": model_id},
        {
            "$set": {
                "versions": {str(version_id): {"description": "version description"}}
            }
        },
    )

    response_issue1 = {
        "issue_id": "Apache-1",
        "issue_link": "https://issues.apache.org/jira/browse/HADOOP-1",
        "issue_key": "HADOOP-1",
        "summary": "Summary of HADOOP-1",
        "description": "Description of HADOOP-1",
        "manual_label": {"existence": True, "property": False, "executive": True},
        "predictions": {
            f"{model_id}-{version_id}": {
                "existence": {"prediction": False, "confidence": 0.42}
            }
        },
        "tags": ["HADOOP", "has-label"],
        "comments": {
            str(comment_id1): {"author": "test", "comment": "Comment on HADOOP-01"}
        },
    }
    response_issue2 = {
        "issue_id": "Apache-2",
        "issue_link": "https://issues.apache.org/jira/browse/CASSANDRA-1",
        "issue_key": "CASSANDRA-1",
        "summary": "Summary of CASSANDRA-1",
        "description": "Description of CASSANDRA-1",
        "manual_label": {"existence": None, "property": None, "executive": None},
        "predictions": {
            f"{model_id}-{version_id}": {
                "existence": {"prediction": False, "confidence": 0.43}
            }
        },
        "tags": ["CASSANDRA", "has-label"],
        "comments": {
            str(comment_id2): {"author": "test", "comment": "Comment on CASSANDRA-01"}
        },
    }

    # Test sort ascending
    expected_response = {"data": [response_issue1, response_issue2], "total_pages": 1}
    payload = Query(
        filter={},
        sort=f"predictions.{model_id}-{version_id}.existence.confidence",
        sort_ascending=True,
        models=[f"{model_id}-{version_id}"],
        page=1,
        limit=2,
    )
    assert get_ui_data(payload).model_dump() == expected_response

    # Test sort descending
    expected_response = {"data": [response_issue2, response_issue1], "total_pages": 1}
    payload = Query(
        filter={},
        sort=f"predictions.{model_id}-{version_id}.existence.confidence",
        sort_ascending=False,
        models=[f"{model_id}-{version_id}"],
        page=1,
        limit=2,
    )
    assert get_ui_data(payload).model_dump() == expected_response

    # Test no sort
    expected_response = {"data": [response_issue1, response_issue2], "total_pages": 1}
    payload = Query(
        filter={},
        sort=None,
        sort_ascending=True,
        models=[f"{model_id}-{version_id}"],
        page=1,
        limit=2,
    )
    assert get_ui_data(payload).model_dump() == expected_response

    # Test filter
    expected_response = {"data": [response_issue1], "total_pages": 1}
    payload = Query(
        filter={"tags": "HADOOP"},
        sort=f"predictions.{model_id}-{version_id}.existence.confidence",
        sort_ascending=True,
        models=[f"{model_id}-{version_id}"],
        page=1,
        limit=2,
    )
    assert get_ui_data(payload).model_dump() == expected_response

    # Test page and limit
    expected_response = {"data": [response_issue1], "total_pages": 2}
    payload = Query(
        filter={},
        sort=f"predictions.{model_id}-{version_id}.existence.confidence",
        sort_ascending=True,
        models=[f"{model_id}-{version_id}"],
        page=1,
        limit=1,
    )
    assert get_ui_data(payload).model_dump() == expected_response

    # Test second page
    expected_response = {"data": [response_issue2], "total_pages": 2}
    payload = Query(
        filter={},
        sort=f"predictions.{model_id}-{version_id}.existence.confidence",
        sort_ascending=True,
        models=[f"{model_id}-{version_id}"],
        page=2,
        limit=1,
    )
    assert get_ui_data(payload).model_dump() == expected_response

    # Test non-existing model on sorting (MongoDB silently sorts on non-existent field)
    payload = Query(
        filter={},
        sort=f"predictions.{ObjectId()}-{version_id}.existence.confidence",
        sort_ascending=True,
        models=[f"{model_id}-{version_id}"],
        page=1,
        limit=2,
    )
    result = get_ui_data(payload)
    assert len(result.data) == 2

    # Test non-existing version on sorting
    payload = Query(
        filter={},
        sort=f"predictions.{model_id}-{ObjectId()}.existence.confidence",
        sort_ascending=True,
        models=[f"{model_id}-{version_id}"],
        page=1,
        limit=2,
    )
    result = get_ui_data(payload)
    assert len(result.data) == 2

    restore_dbs()
