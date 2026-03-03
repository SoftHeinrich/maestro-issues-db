import io

from app.dependencies import files_collection, fs
from bson import ObjectId

from .files import get_files, Category
from .test_util import (
    restore_dbs,
    client,
    setup_users_db,
    get_auth_header,
    auth_test_post,
    auth_test_delete,
)


def setup_db():
    file = io.BytesIO(bytes("mock data", "utf-8"))
    file_id = fs.put(file, filename="filename.txt")
    files_collection.insert_one(
        {"_id": file_id, "description": "Description of file", "category": "cat1"}
    )
    return file_id


def test_get_files():
    restore_dbs()
    file_id = setup_db()

    assert [f.model_dump() for f in get_files(Category(category=None))] == [
        {
            "file_id": str(file_id),
            "description": "Description of file",
            "category": "cat1",
        }
    ]
    assert [f.model_dump() for f in get_files(Category(category="cat1"))] == [
        {
            "file_id": str(file_id),
            "description": "Description of file",
            "category": "cat1",
        }
    ]
    assert get_files(Category(category="cat2")) == []

    restore_dbs()


def test_create_file():
    restore_dbs()
    setup_users_db()

    auth_test_post("/files")
    headers = get_auth_header()

    file = io.BytesIO(bytes("mock data", "utf-8"))
    response = client.post(
        "/files",
        headers=headers,
        files={
            "file": ("filename", file),
            "description": (None, "Description of file"),
            "category": (None, "cat42"),
        },
    )
    assert response.status_code == 200
    file_id = ObjectId(response.json()["file_id"])
    assert files_collection.find_one({"_id": file_id}) == {
        "_id": file_id,
        "description": "Description of file",
        "category": "cat42",
    }
    assert fs.get(file_id).read() == bytes("mock data", "utf-8")

    restore_dbs()


def test_get_file():
    restore_dbs()
    file_id = setup_db()

    assert client.get(f"/files/{ObjectId()}").status_code == 404
    assert client.get(f"/files/{file_id}").json() == {
        "file_id": str(file_id),
        "description": "Description of file",
        "category": "cat1",
    }

    restore_dbs()


def test_delete_file():
    restore_dbs()
    file_id = setup_db()
    setup_users_db()

    auth_test_delete(f"/files/{file_id}")
    headers = get_auth_header()

    assert client.delete(f"/files/{ObjectId()}", headers=headers).status_code == 404
    assert client.delete(f"/files/{file_id}", headers=headers).status_code == 200
    assert files_collection.find_one({"_id": file_id}) is None
    assert fs.exists(file_id) is False

    restore_dbs()


def test_get_file_file():
    restore_dbs()
    file_id = setup_db()

    assert client.get(f"/files/{ObjectId()}/file").status_code == 404
    assert client.get(f"/files/{file_id}/file").content == bytes("mock data", "utf-8")

    restore_dbs()
