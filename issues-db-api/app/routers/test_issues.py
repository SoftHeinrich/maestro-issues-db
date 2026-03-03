from fastapi.testclient import TestClient

from app import app
from app.dependencies import issue_labels_collection, tags_collection
from .test_util import setup_users_db, restore_dbs, get_auth_header, auth_test_post, auth_test_delete

client = TestClient(app.app)


def setup_db():
    issue_labels_collection.insert_one({
        '_id': 'Apache-01',
        'existence': False,
        'property': False,
        'executive': True,
        'tags': ['has-label']
    })
    tags_collection.insert_one({
        '_id': 'tag',
        'description': 'text',
        'type': 'manual-tag'
    })


def test_mark_and_finish_review():
    restore_dbs()
    setup_users_db()
    setup_db()

    auth_test_post('/issues/Apache-01/mark-review')
    auth_test_post('/issues/Apache-01/finish-review')
    headers = get_auth_header()

    # Test mark review
    assert client.post('/issues/Apache-01/mark-review', headers=headers).status_code == 200
    assert issue_labels_collection.find_one({'_id': 'Apache-01'})['tags'] == ['has-label', 'needs-review']
    assert client.post('/issues/Apache-01/mark-review', headers=headers).status_code == 200
    assert issue_labels_collection.find_one({'_id': 'Apache-01'})['tags'] == ['has-label', 'needs-review']
    assert client.post('/issues/Apache-02/mark-review', headers=headers).status_code == 404

    # Test finish review
    assert client.post('/issues/Apache-01/finish-review', headers=headers).status_code == 200
    assert issue_labels_collection.find_one({'_id': 'Apache-01'})['tags'] == ['has-label']
    assert client.post('/issues/Apache-01/finish-review', headers=headers).status_code == 200
    assert issue_labels_collection.find_one({'_id': 'Apache-01'})['tags'] == ['has-label']
    assert client.post('/issues/Apache-02/finish-review', headers=headers).status_code == 404

    restore_dbs()


def test_get_tags():
    restore_dbs()
    setup_db()

    # Get tags for issue
    assert client.get('/issues/Apache-01/tags').json() == {'tags': ['has-label']}
    assert client.get('/issues/Apache-02/tags').status_code == 404

    restore_dbs()


def test_add_tag():
    restore_dbs()
    setup_users_db()
    setup_db()

    auth_test_post('/issues/Apache-01/tags')
    headers = get_auth_header()

    # Add tag
    payload = {'tag': 'tag'}
    assert client.post('/issues/Apache-01/tags', headers=headers, json=payload).status_code == 200
    assert issue_labels_collection.find_one({'_id': 'Apache-01'}, ['tags'])['tags'] == ['has-label', 'tag']

    # Insert existing tag
    assert client.post('/issues/Apache-01/tags', headers=headers, json=payload).status_code == 409
    assert issue_labels_collection.find_one({'_id': 'Apache-01'}, ['tags'])['tags'] == ['has-label', 'tag']

    # Insert illegal tag
    payload = {'tag': 'illegal-tag'}
    assert client.post('/issues/Apache-01/tags', headers=headers, json=payload).status_code == 404
    assert issue_labels_collection.find_one({'_id': 'Apache-01'}, ['tags'])['tags'] == ['has-label', 'tag']

    # Test non-existing issue
    payload = {'tag': 'tag'}
    assert client.post('/issues/Apache-02/tags', headers=headers, json=payload).status_code == 404
    assert issue_labels_collection.find_one({'_id': 'Apache-01'}, ['tags'])['tags'] == ['has-label', 'tag']

    restore_dbs()


def test_delete_tag():
    restore_dbs()
    setup_users_db()
    setup_db()

    auth_test_delete('/issues/Apache-01/tags/has-label')
    headers = get_auth_header()

    # Delete tag
    assert client.delete('/issues/Apache-01/tags/has-label', headers=headers).status_code == 200
    assert issue_labels_collection.find_one({'_id': 'Apache-01'}, ['tags'])['tags'] == []

    # Delete non existing tag
    assert client.delete('/issues/Apache-01/tags/has-label', headers=headers).status_code == 404
    assert issue_labels_collection.find_one({'_id': 'Apache-01'}, ['tags'])['tags'] == []

    # Non-existing issue
    assert client.delete('/issues/Apache-02/tags/has-label', headers=headers).status_code == 404
    assert issue_labels_collection.find_one({'_id': 'Apache-01'}, ['tags'])['tags'] == []

    restore_dbs()
