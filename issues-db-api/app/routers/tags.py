from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.dependencies import (
    tags_collection,
    projects_collection,
    issue_labels_collection,
    users_collection,
)
from app.routers.authentication import validate_token
from pymongo.errors import DuplicateKeyError
from app.exceptions import tag_exists_exception, tag_not_found_exception

router = APIRouter(prefix="/tags", tags=["tags"])


class NewTag(BaseModel):
    tag: str
    description: str


class UpdateTag(BaseModel):
    description: str


class Tag(BaseModel):
    tag: str


class DbTag(BaseModel):
    name: str
    description: str
    type: str


class TagsOut(BaseModel):
    tags: list[DbTag]


class TagOut(BaseModel):
    tag: DbTag


@router.get("", response_model=TagsOut)
def get_tags():
    """
    Retrieve all unique tags in the database.
    """
    tags = tags_collection.find({})
    response = []
    for tag in tags:
        response.append(
            DbTag(name=tag["_id"], description=tag["description"], type=tag["type"])
        )
    projects = projects_collection.find({})
    for project in projects:
        response.append(DbTag(name=project["_id"], description="", type="project"))
    users = users_collection.find({})
    for user in users:
        response.append(DbTag(name=user["_id"], description="", type="author"))
    return TagsOut(tags=response)


@router.post("")
def create_tag(tag: NewTag, token=Depends(validate_token)):
    """
    Create a new manual tag with the given description.
    """
    if projects_collection.find_one({"_id": tag.tag}) is not None:
        raise tag_exists_exception(tag.tag)
    if users_collection.find_one({"_id": tag.tag}) is not None:
        raise tag_exists_exception(tag.tag)
    try:
        tags_collection.insert_one(
            {"_id": tag.tag, "description": tag.description, "type": "manual-tag"}
        )
    except DuplicateKeyError:
        raise tag_exists_exception(tag.tag)


@router.get("/{tag}", response_model=TagOut)
def get_tag(tag: str):
    """
    Retrieve info for the given tag.
    """
    tag_ = tags_collection.find_one({"_id": tag})
    if tag_ is not None:
        return TagOut(
            tag=DbTag(
                name=tag_["_id"], description=tag_["description"], type=tag_["type"]
            )
        )
    tag_ = projects_collection.find_one({"_id": tag})
    if tag_ is not None:
        return TagOut(tag=DbTag(name=tag_["_id"], description="", type="project"))
    tag_ = users_collection.find_one({"_id": tag})
    if tag_ is not None:
        return TagOut(tag=DbTag(name=tag_["_id"], description="", type="author"))
    raise tag_not_found_exception(tag)


@router.post("/{tag}")
def update_tag(tag: str, request: UpdateTag, token=Depends(validate_token)):
    """
    Retrieve info for the given tag.
    """
    result = tags_collection.update_one(
        {"_id": tag}, {"$set": {"description": request.description}}
    )
    if result.matched_count != 1:
        raise tag_not_found_exception(tag)


@router.delete("/{tag}")
def delete_tag(tag: str, token=Depends(validate_token)):
    result = tags_collection.delete_one({"_id": tag})
    if result.deleted_count != 1:
        raise tag_not_found_exception(tag)
    issue_labels_collection.update_many({"tags": tag}, {"$pull": {"tags": tag}})
