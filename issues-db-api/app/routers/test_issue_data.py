import json

from fastapi import HTTPException
import pytest

from app.dependencies import jira_repos_db, repo_info_collection
from .issue_data import streaming_issue_data, get_issue_data, IssueDataIn
from .test_util import restore_dbs


def _get_streaming_json(request):
    """Consume streaming_issue_data generator and parse as JSON."""
    body = "".join(streaming_issue_data(request))
    return json.loads(body)


def setup_db():
    jira_repos_db["Apache"].insert_one(
        {
            "id": "13211409",
            "key": "YARN-9230",
            "fields": {"summary": "Write a go hdfs driver for Docker Registry"},
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


def test_issue_data_endpoint():
    restore_dbs()
    setup_db()

    assert _get_streaming_json(
        IssueDataIn(
            issue_ids=["Apache-13211409"], attributes=["key", "link", "summary"]
        )
    ) == {
        "data": {
            "Apache-13211409": {
                "key": "YARN-9230",
                "link": "https://issues.apache.org/jira/browse/YARN-9230",
                "summary": "Write a go hdfs driver for Docker Registry",
            }
        }
    }

    # Test attribute not found
    with pytest.raises(HTTPException):
        _get_streaming_json(
            IssueDataIn(
                issue_ids=["Apache-13211409"], attributes=["non-existing-attribute"]
            )
        )

    # Test parent attribute
    assert _get_streaming_json(
        IssueDataIn(issue_ids=["Apache-13211409"], attributes=["parent"])
    ) == {
        "data": {
            "Apache-13211409": {
                "parent": None,
            }
        }
    }

    # Test non-existing issue
    with pytest.raises(HTTPException):
        _get_streaming_json(IssueDataIn(issue_ids=["Apache-0"], attributes=["key"]))

    # Test key is None
    jira_repos_db["Apache"].insert_one(
        {
            "id": "13211410",
            "key": None,
            "fields": {"summary": None, "required_attr": None},
        }
    )
    with pytest.raises(HTTPException):
        _get_streaming_json(IssueDataIn(issue_ids=["Apache-13211410"], attributes=["key"]))

    # Test default value
    assert _get_streaming_json(
        IssueDataIn(issue_ids=["Apache-13211410"], attributes=["summary"])
    ) == {"data": {"Apache-13211410": {"summary": ""}}}

    # Test required attribute
    with pytest.raises(HTTPException):
        _get_streaming_json(
            IssueDataIn(issue_ids=["Apache-13211410"], attributes=["required_attr"])
        )

    # Test duplicate issue exception
    jira_repos_db["Apache"].insert_one(
        {
            "id": "13211409",
            "key": "YARN-9230",
            "fields": {"summary": "Write a go hdfs driver for Docker Registry"},
        }
    )
    jira_repos_db["Apache"].insert_one(
        {
            "id": "13211409",
            "key": "YARN-9230",
            "fields": {"summary": "Write a go hdfs driver for Docker Registry"},
        }
    )
    with pytest.raises(HTTPException):
        _get_streaming_json(
            IssueDataIn(issue_ids=["Apache-13211409"], attributes=["summary"])
        )

    restore_dbs()
