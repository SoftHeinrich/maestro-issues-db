from .test_util import client
from .test_util import setup_users_db, restore_dbs, get_auth_header, auth_test_post
from .bulk import get_issue_ids_from_keys, IssueKeysIn
from app.dependencies import issue_labels_collection, tags_collection, jira_repos_db
import pytest
from fastapi import HTTPException


def setup_db():
    issue_labels_collection.insert_one({
        '_id': 'Apache-01',
        'existence': False,
        'property': False,
        'executive': True,
        'tags': []
    })
    tags_collection.insert_one({
        '_id': 'tag',
        'description': 'text',
        'type': 'manual-tag'
    })


def test_add_tags_in_bulk():
    restore_dbs()
    setup_users_db()
    setup_db()

    auth_test_post('/bulk/add-tags')
    headers = get_auth_header()

    # Add tags
    payload = {
        'data': [{
            'issue_id': 'Apache-01',
            'tags': ['tag']
        }]
    }
    assert client.post('/bulk/add-tags', headers=headers, json=payload).status_code == 200
    assert issue_labels_collection.find_one({'_id': 'Apache-01'}, ['tags'])['tags'] == ['tag']

    # Insert existing tag
    assert client.post('/bulk/add-tags', headers=headers, json=payload).status_code == 200
    assert issue_labels_collection.find_one({'_id': 'Apache-01'}, ['tags'])['tags'] == ['tag']

    # Insert illegal tag
    payload = {
        'data': [{
            'issue_id': 'Apache-01',
            'tags': ['illegal-tag']
        }]
    }
    assert client.post('/bulk/add-tags', headers=headers, json=payload).status_code == 404
    assert issue_labels_collection.find_one({'_id': 'Apache-01'}, ['tags'])['tags'] == ['tag']

    # Test non-existing issue
    payload = {
        'data': [{
            'issue_id': 'Apache-02',
            'tags': ['tag']
        }]
    }
    assert client.post('/bulk/add-tags', headers=headers, json=payload).status_code == 404
    assert issue_labels_collection.find_one({'_id': 'Apache-01'}, ['tags'])['tags'] == ['tag']

    restore_dbs()


def test_get_issue_ids_from_keys():
    restore_dbs()
    jira_repos_db['Apache'].insert_one({
        'id': '13211409',
        'key': 'YARN-9230',
        'fields': {
            'summary': 'Write a go hdfs driver for Docker Registry'
        }
    })

    # Get issue_ids from issue_keys
    payload = IssueKeysIn(issue_keys=['Apache-YARN-9230'])
    assert get_issue_ids_from_keys(payload).model_dump() == {'issue_ids': {'Apache-YARN-9230': 'Apache-13211409'}}

    # Unknown repo
    with pytest.raises(HTTPException):
        payload = IssueKeysIn(issue_keys=['Repo-YARN-9230'])
        get_issue_ids_from_keys(payload)

    # Unknown issue
    with pytest.raises(HTTPException):
        payload = IssueKeysIn(issue_keys=['Apache-PROJECT-9230'])
        get_issue_ids_from_keys(payload)

    restore_dbs()
