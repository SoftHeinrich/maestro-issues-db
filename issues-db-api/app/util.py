from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError


def read_file_in_chunks(file):
    while True:
        chunk = file.read(1024)
        if not chunk:
            break
        yield chunk


def find_one(collection, _id, name):
    item = collection.find_one({"_id": _id})
    if item is None:
        raise HTTPException(
            status_code=404, detail=f"{name} with _id {_id} does not exist"
        )
    return item


def insert_one(collection, item, name):
    try:
        collection.insert_one(item)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409, detail=f"{name} with _id {item['_id']} already exists"
        )


def update_one(collection, _id, update, name):
    result = collection.update_one({"_id": _id}, update)
    if result.matched_count == 0:
        raise HTTPException(
            status_code=404, detail=f"{name} with _id {_id} does not exist"
        )


def delete_one(collection, _id, name):
    result = collection.delete_one({"_id": _id})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404, detail=f"{name} with _id {_id} does not exist"
        )
