from .test_util import client
from app.dependencies import jira_repos_db, projects_collection
from .test_util import restore_dbs


def setup_db():
    jira_repos_db['Apache'].insert_one({
        'id': '13211409',
        'key': 'YARN-9230',
        'fields': {
            'summary': 'Write a go hdfs driver for Docker Registry'
        }
    })
    projects_collection.insert_one({
        '_id': 'Apache-YARN',
        'ecosystem': 'Apache',
        'key': 'YARN',
        'additional_properties': {}
    })


def test_repos():
    restore_dbs()
    setup_db()

    response = client.get('/repos')
    assert response.status_code == 200
    assert response.json() == {
        'repos': ['Apache']
    }

    response = client.get('/repos/Apache/projects')
    assert response.status_code == 200
    assert response.json() == {
        'projects': ['YARN']
    }

    restore_dbs()
