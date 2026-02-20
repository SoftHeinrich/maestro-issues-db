from app.dependencies import issue_labels_collection, jira_repos_db
from .test_util import client, restore_dbs
from .issue_ids import get_issue_ids, IssueIdsIn


def setup_db():
    issue_labels_collection.insert_one({
        '_id': 'Apache-01',
        'existence': False,
        'property': False,
        'executive': True,
        'tags': ['Tag-01']
    })
    issue_labels_collection.insert_one({
        '_id': 'Apache-02',
        'existence': False,
        'property': False,
        'executive': True,
        'tags': ['Tag-01', 'Tag-02']
    })
    jira_repos_db['Apache'].insert_one({
        'id': '13211409',
        'key': 'YARN-9230',
        'fields': {
            'summary': 'Write a go hdfs driver for Docker Registry'
        }
    })


def test_get_issue_ids():
    restore_dbs()
    setup_db()

    # Test two matches
    assert get_issue_ids(IssueIdsIn(filter={'tags': 'Tag-01'})).model_dump() == {'issue_ids': ['Apache-01', 'Apache-02']}

    # Test one match
    assert get_issue_ids(IssueIdsIn(filter={'tags': 'Tag-02'})).model_dump() == {'issue_ids': ['Apache-02']}

    # Test no matches
    assert get_issue_ids(IssueIdsIn(filter={'tags': 'Tag-03'})).model_dump() == {'issue_ids': []}

    restore_dbs()


def test_get_issue_id_from_key():
    restore_dbs()
    setup_db()

    # Get id from key
    assert client.get('/issue-ids/Apache/YARN-9230').json() == {'issue_id': 'Apache-13211409'}

    # Repo not found
    assert client.get('/issue-ids/Jira/YARN-9230').status_code == 404

    # Issue not found
    assert client.get('/issue-ids/Apache/YARN-9231').status_code == 404

    restore_dbs()
