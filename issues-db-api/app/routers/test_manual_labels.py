from .test_util import client
from app.dependencies import issue_labels_collection
from .test_util import setup_users_db, restore_dbs, get_auth_header, auth_test_post, auth_test_patch, auth_test_delete,\
    get_auth_header_other_user
from .manual_labels import get_manual_labels, ManualLabelsIn
from bson import ObjectId
import pytest
from fastapi import HTTPException


def setup_db():
    issue_labels_collection.insert_one({
        '_id': 'Apache-01',
        'existence': False,
        'property': False,
        'executive': True,
        'tags': ['has-label']
    })


def test_get_manual_labels():
    restore_dbs()
    setup_db()

    # Get label
    assert get_manual_labels(ManualLabelsIn(issue_ids=['Apache-01'])).model_dump() == {
        'manual_labels': {
            'Apache-01': {
                'existence': False,
                'property': False,
                'executive': True
            }
        }
    }

    # Get label of non-existing issue
    with pytest.raises(HTTPException):
        get_manual_labels(ManualLabelsIn(issue_ids=['Apache-02']))

    restore_dbs()


def test_update_manual_label():
    restore_dbs()
    setup_users_db()
    setup_db()

    auth_test_post('/manual-labels/Apache-01')
    headers = get_auth_header()

    # Update manual label
    payload = {'existence': True, 'property': True, 'executive': False}
    assert client.post('/manual-labels/Apache-01', headers=headers, json=payload).status_code == 200
    assert issue_labels_collection.find_one({'_id': 'Apache-01'}) == {
        '_id': 'Apache-01',
        'existence': True,
        'property': True,
        'executive': False,
        'tags': ['has-label', 'test']
    }

    # Non-existing issue
    assert client.post('/manual-labels/Apache-02', headers=headers, json=payload).status_code == 404

    restore_dbs()


def test_get_comments():
    restore_dbs()
    comment_id = ObjectId()
    issue_labels_collection.insert_one({
        '_id': 'Apache-01',
        'comments': {
            str(comment_id): {
                'author': 'test',
                'comment': 'text'
            }
        }
    })

    # Get comments
    assert client.get('/manual-labels/Apache-01/comments').json() == {
        'comments': {
            str(comment_id): {
                'author': 'test',
                'comment': 'text'
            }
        }
    }

    # Non-existing issue
    assert client.get('/manual-labels/Apache-02/comments').status_code == 404

    # No comments
    issue_labels_collection.insert_one({'_id': 'Apache-02'})
    assert client.get('/manual-labels/Apache-02/comments').json() == {'comments': {}}

    restore_dbs()


def test_add_comment():
    restore_dbs()
    setup_users_db()
    setup_db()

    auth_test_post('/manual-labels/Apache-01/comments')
    headers = get_auth_header()

    # Add comment
    payload = {'comment': 'text'}
    comment_id = client.post('/manual-labels/Apache-01/comments', headers=headers, json=payload).json()['comment_id']
    assert issue_labels_collection.find_one({'_id': 'Apache-01'}, ['comments', 'tags']) == {
        '_id': 'Apache-01',
        'comments': {
            comment_id: {
                'author': 'test',
                'comment': 'text'
            }
        },
        'tags': ['has-label', 'test']
    }

    # Non-existing issue
    assert client.post('/manual-labels/Apache-02/comments', headers=headers, json=payload).status_code == 404

    restore_dbs()


def test_update_comment():
    restore_dbs()
    setup_users_db()
    comment_id = ObjectId()
    issue_labels_collection.insert_one({
        '_id': 'Apache-01',
        'comments': {
            str(comment_id): {
                'author': 'test',
                'comment': 'text'
            }
        }
    })

    auth_test_patch(f'/manual-labels/Apache-01/comments/{comment_id}')
    headers = get_auth_header()

    # Update comment
    payload = {'comment': 'new-text'}
    response = client.patch(f'/manual-labels/Apache-01/comments/{comment_id}', headers=headers, json=payload)
    assert response.status_code == 200
    assert issue_labels_collection.find_one({'_id': 'Apache-01'}, ['comments', 'tags']) == {
        '_id': 'Apache-01',
        'comments': {
            str(comment_id): {
                'author': 'test',
                'comment': 'new-text'
            }
        }
    }

    # Non-existing issue
    response = client.patch(f'/manual-labels/Apache-02/comments/{comment_id}', headers=headers, json=payload)
    assert response.status_code == 404

    # Non-existing comment
    response = client.patch(f'/manual-labels/Apache-01/comments/{ObjectId()}', headers=headers, json=payload)
    assert response.status_code == 404

    # Edit comment of other user
    other_headers = get_auth_header_other_user()
    response = client.patch(f'/manual-labels/Apache-01/comments/{comment_id}', headers=other_headers, json=payload)
    assert response.status_code == 403

    restore_dbs()


def test_delete_comment():
    restore_dbs()
    setup_users_db()
    comment_id = ObjectId()
    issue_labels_collection.insert_one({
        '_id': 'Apache-01',
        'comments': {
            str(comment_id): {
                'author': 'test',
                'comment': 'text'
            }
        }
    })

    auth_test_delete(f'/manual-labels/Apache-01/comments/{comment_id}')
    headers = get_auth_header()

    # Delete comment of other user
    other_headers = get_auth_header_other_user()
    assert client.delete(f'/manual-labels/Apache-01/comments/{comment_id}', headers=other_headers).status_code == 403
    assert issue_labels_collection.find_one({f'comments.{str(comment_id)}': {'$exists': True}}) is not None

    # Delete comment
    assert client.delete(f'/manual-labels/Apache-01/comments/{comment_id}', headers=headers).status_code == 200
    assert issue_labels_collection.find_one({f'comments.{str(comment_id)}': {'$exists': True}}) is None

    # Delete non-existing comment
    assert client.delete(f'/manual-labels/Apache-01/comments/{comment_id}', headers=headers).status_code == 404

    restore_dbs()
