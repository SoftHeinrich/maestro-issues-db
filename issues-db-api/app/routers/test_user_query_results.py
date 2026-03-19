"""Tests for user-differentiated query results.

The system already supports per-user result differentiation via the tag system:
- When a user labels an issue or adds a comment, their username is automatically
  added as a tag on that issue (manual_labels.py:166, manual_labels.py:209).
- The UI query's `filter` dict accepts MongoDB queries, so filtering by
  `{"tags": "<username>"}` returns only issues that user has interacted with.
- Tags endpoint exposes usernames as tags with type="author" (tags.py:57-59).

These tests verify that different users see different query results based on
their interactions (labeling, commenting) and the tag-based filtering mechanism.
"""
import pytest
from bson import ObjectId

from app.dependencies import (
    issue_labels_collection,
    jira_repos_db,
    models_collection,
    repo_info_collection,
    tags_collection,
    users_collection,
)

from .test_util import restore_dbs, setup_users_db, get_auth_header, get_auth_header_other_user, client
from .manual_labels import update_manual_label, add_comment, get_comments
from .issues import get_tags
from .tags import get_tags as get_all_tags
from .ui import get_ui_data, Query


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _setup_shared_db():
    """Insert mock issues, jira data, and repo info shared across tests."""
    restore_dbs()
    setup_users_db()

    model_id = ObjectId()
    version_id = ObjectId()

    # 5 issues across 2 projects — no user tags yet
    issues = [
        {
            "_id": "Apache-100",
            "existence": None,
            "property": None,
            "executive": None,
            "tags": ["Apache-HDFS"],
            "comments": {},
            "predictions": {},
        },
        {
            "_id": "Apache-101",
            "existence": None,
            "property": None,
            "executive": None,
            "tags": ["Apache-HDFS"],
            "comments": {},
            "predictions": {},
        },
        {
            "_id": "Apache-102",
            "existence": None,
            "property": None,
            "executive": None,
            "tags": ["Apache-CASSANDRA"],
            "comments": {},
            "predictions": {},
        },
        {
            "_id": "Apache-103",
            "existence": None,
            "property": None,
            "executive": None,
            "tags": ["Apache-CASSANDRA"],
            "comments": {},
            "predictions": {},
        },
        {
            "_id": "Apache-104",
            "existence": None,
            "property": None,
            "executive": None,
            "tags": ["Apache-HDFS"],
            "comments": {},
            "predictions": {},
        },
    ]
    issue_labels_collection.insert_many(issues)

    # Corresponding Jira issue documents
    jira_docs = [
        {"id": "100", "key": "HDFS-100", "fields": {"summary": "Data replication strategy", "description": "Decide on replication factor"}},
        {"id": "101", "key": "HDFS-101", "fields": {"summary": "Block placement policy", "description": "Rack-aware placement"}},
        {"id": "102", "key": "CASSANDRA-102", "fields": {"summary": "Compaction strategy", "description": "Size-tiered vs leveled"}},
        {"id": "103", "key": "CASSANDRA-103", "fields": {"summary": "Gossip protocol tuning", "description": "Failure detection thresholds"}},
        {"id": "104", "key": "HDFS-104", "fields": {"summary": "NameNode HA", "description": "Automatic failover design"}},
    ]
    jira_repos_db["Apache"].insert_many(jira_docs)

    repo_info_collection.insert_one({
        "_id": "Apache",
        "repo_url": "https://issues.apache.org/jira",
        "download_date": None,
        "batch_size": 1000,
        "query_wait_time_minutes": 0.0,
        "issue_link_prefix": "https://issues.apache.org/jira",
    })

    # Insert model so UI queries with models work
    models_collection.insert_one({
        "_id": model_id,
        "name": "test-model",
        "config": {},
        "versions": {str(version_id): {"description": "v1"}},
        "performances": {},
    })

    return model_id, version_id


# ---------------------------------------------------------------------------
# Tests: user tag is added when labeling / commenting
# ---------------------------------------------------------------------------

class TestUserTagOnLabel:
    """Verify that labeling an issue adds the user's username as a tag."""

    def test_label_adds_username_tag(self):
        _setup_shared_db()
        auth = get_auth_header()  # user "test"

        # Label issue Apache-100 as user "test"
        client.post(
            "/manual-labels/Apache-100",
            json={"existence": True, "property": False, "executive": None},
            headers=auth,
        )

        # The issue should now have "test" in its tags
        resp = get_tags("Apache-100")
        assert "test" in resp.tags
        assert "has-label" in resp.tags

    def test_different_users_tag_different_issues(self):
        _setup_shared_db()
        auth_test = get_auth_header()          # user "test"
        auth_other = get_auth_header_other_user()  # user "other-user"

        # "test" labels Apache-100 and Apache-101
        client.post(
            "/manual-labels/Apache-100",
            json={"existence": True, "property": False, "executive": None},
            headers=auth_test,
        )
        client.post(
            "/manual-labels/Apache-101",
            json={"existence": False, "property": True, "executive": None},
            headers=auth_test,
        )

        # "other-user" labels Apache-102 and Apache-103
        client.post(
            "/manual-labels/Apache-102",
            json={"existence": None, "property": None, "executive": True},
            headers=auth_other,
        )
        client.post(
            "/manual-labels/Apache-103",
            json={"existence": True, "property": True, "executive": True},
            headers=auth_other,
        )

        # Verify tags
        assert "test" in get_tags("Apache-100").tags
        assert "test" in get_tags("Apache-101").tags
        assert "test" not in get_tags("Apache-102").tags
        assert "test" not in get_tags("Apache-103").tags

        assert "other-user" in get_tags("Apache-102").tags
        assert "other-user" in get_tags("Apache-103").tags
        assert "other-user" not in get_tags("Apache-100").tags
        assert "other-user" not in get_tags("Apache-101").tags


class TestUserTagOnComment:
    """Verify that commenting on an issue adds the user's username as a tag."""

    def test_comment_adds_username_tag(self):
        _setup_shared_db()
        auth = get_auth_header()

        client.post(
            "/manual-labels/Apache-104/comments",
            json={"comment": "This looks like an executive decision"},
            headers=auth,
        )

        assert "test" in get_tags("Apache-104").tags

    def test_comment_by_different_user(self):
        _setup_shared_db()
        auth_other = get_auth_header_other_user()

        client.post(
            "/manual-labels/Apache-104/comments",
            json={"comment": "Needs further review"},
            headers=auth_other,
        )

        assert "other-user" in get_tags("Apache-104").tags
        assert "test" not in get_tags("Apache-104").tags


# ---------------------------------------------------------------------------
# Tests: UI query returns different results per user via tag filter
# ---------------------------------------------------------------------------

class TestUserFilteredUIQuery:
    """Verify that filtering by username tag gives each user only their issues."""

    def _label_issues_as_users(self):
        """Helper: 'test' labels 100,101; 'other-user' labels 102,103; 104 unlabeled."""
        auth_test = get_auth_header()
        auth_other = get_auth_header_other_user()

        for issue_id in ["Apache-100", "Apache-101"]:
            client.post(
                f"/manual-labels/{issue_id}",
                json={"existence": True, "property": False, "executive": None},
                headers=auth_test,
            )

        for issue_id in ["Apache-102", "Apache-103"]:
            client.post(
                f"/manual-labels/{issue_id}",
                json={"existence": None, "property": True, "executive": True},
                headers=auth_other,
            )

    def test_filter_by_user_test(self):
        model_id, version_id = _setup_shared_db()
        self._label_issues_as_users()

        result = get_ui_data(Query(
            filter={"tags": "test"},
            sort=None,
            sort_ascending=True,
            models=[f"{model_id}-{version_id}"],
            page=1,
            limit=10,
        ))

        issue_ids = {d.issue_id for d in result.data}
        assert issue_ids == {"Apache-100", "Apache-101"}

    def test_filter_by_user_other(self):
        model_id, version_id = _setup_shared_db()
        self._label_issues_as_users()

        result = get_ui_data(Query(
            filter={"tags": "other-user"},
            sort=None,
            sort_ascending=True,
            models=[f"{model_id}-{version_id}"],
            page=1,
            limit=10,
        ))

        issue_ids = {d.issue_id for d in result.data}
        assert issue_ids == {"Apache-102", "Apache-103"}

    def test_no_user_filter_returns_all(self):
        model_id, version_id = _setup_shared_db()
        self._label_issues_as_users()

        result = get_ui_data(Query(
            filter={},
            sort=None,
            sort_ascending=True,
            models=[f"{model_id}-{version_id}"],
            page=1,
            limit=10,
        ))

        issue_ids = {d.issue_id for d in result.data}
        assert len(issue_ids) == 5

    def test_user_filter_pagination(self):
        model_id, version_id = _setup_shared_db()
        self._label_issues_as_users()

        # Page 1 with limit=1
        result = get_ui_data(Query(
            filter={"tags": "test"},
            sort=None,
            sort_ascending=True,
            models=[f"{model_id}-{version_id}"],
            page=1,
            limit=1,
        ))
        assert len(result.data) == 1
        assert result.total_pages == 2

        # Page 2 with limit=1
        result2 = get_ui_data(Query(
            filter={"tags": "test"},
            sort=None,
            sort_ascending=True,
            models=[f"{model_id}-{version_id}"],
            page=2,
            limit=1,
        ))
        assert len(result2.data) == 1
        assert result2.data[0].issue_id != result.data[0].issue_id

    def test_combined_user_and_project_filter(self):
        """Filter by both username and project tag simultaneously."""
        model_id, version_id = _setup_shared_db()

        auth_test = get_auth_header()
        # "test" labels issues in both HDFS and CASSANDRA
        for issue_id in ["Apache-100", "Apache-101", "Apache-102"]:
            client.post(
                f"/manual-labels/{issue_id}",
                json={"existence": True, "property": None, "executive": None},
                headers=auth_test,
            )

        # Filter: issues tagged by "test" AND in CASSANDRA project
        result = get_ui_data(Query(
            filter={"tags": {"$all": ["test", "Apache-CASSANDRA"]}},
            sort=None,
            sort_ascending=True,
            models=[f"{model_id}-{version_id}"],
            page=1,
            limit=10,
        ))

        issue_ids = {d.issue_id for d in result.data}
        assert issue_ids == {"Apache-102"}

    def test_shared_issue_visible_to_both_users(self):
        """When two users both interact with the same issue, both can see it."""
        model_id, version_id = _setup_shared_db()

        auth_test = get_auth_header()
        auth_other = get_auth_header_other_user()

        # Both users label the same issue
        client.post(
            "/manual-labels/Apache-100",
            json={"existence": True, "property": False, "executive": None},
            headers=auth_test,
        )
        client.post(
            "/manual-labels/Apache-100",
            json={"existence": True, "property": True, "executive": None},
            headers=auth_other,
        )

        # Both users should see it
        for username in ["test", "other-user"]:
            result = get_ui_data(Query(
                filter={"tags": username},
                sort=None,
                sort_ascending=True,
                models=[f"{model_id}-{version_id}"],
                page=1,
                limit=10,
            ))
            issue_ids = {d.issue_id for d in result.data}
            assert "Apache-100" in issue_ids


# ---------------------------------------------------------------------------
# Tests: tags endpoint exposes usernames as "author" type
# ---------------------------------------------------------------------------

class TestUserTagsExposed:
    """Verify that the /tags endpoint includes usernames with type='author'."""

    def test_users_appear_as_author_tags(self):
        _setup_shared_db()

        result = get_all_tags()
        author_tags = [t for t in result.tags if t.type == "author"]
        author_names = {t.name for t in author_tags}

        assert "test" in author_names
        assert "other-user" in author_names

    def test_author_tags_separate_from_manual_tags(self):
        _setup_shared_db()
        tags_collection.insert_one({
            "_id": "needs-review",
            "description": "Issues flagged for review",
            "type": "manual-tag",
        })

        result = get_all_tags()
        manual_tags = {t.name for t in result.tags if t.type == "manual-tag"}
        author_tags = {t.name for t in result.tags if t.type == "author"}

        assert "needs-review" in manual_tags
        assert "needs-review" not in author_tags
        assert "test" in author_tags
        assert "test" not in manual_tags


# ---------------------------------------------------------------------------
# Tests: labels-batch respects what each user labeled
# ---------------------------------------------------------------------------

class TestLabelsBatchPerUser:
    """Verify that labels reflect each user's labeling, not a global view."""

    def test_last_labeler_wins(self):
        """When two users label the same issue, the last label overwrites."""
        _setup_shared_db()
        auth_test = get_auth_header()
        auth_other = get_auth_header_other_user()

        # "test" labels existence=True
        client.post(
            "/manual-labels/Apache-100",
            json={"existence": True, "property": False, "executive": None},
            headers=auth_test,
        )

        # "other-user" overwrites existence=False
        client.post(
            "/manual-labels/Apache-100",
            json={"existence": False, "property": True, "executive": None},
            headers=auth_other,
        )

        # The stored label should be the last one written
        issue = issue_labels_collection.find_one({"_id": "Apache-100"})
        assert issue["existence"] is False
        assert issue["property"] is True
        # But both users should be in the tags
        assert "test" in issue["tags"]
        assert "other-user" in issue["tags"]
