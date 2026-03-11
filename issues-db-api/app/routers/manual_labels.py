import typing
import typing_extensions

from app.dependencies import issue_labels_collection
from app.exceptions import (
    issue_not_found_exception,
    manual_labels_not_found_exception,
    comment_not_found_exception,
    comment_author_exception,
)
from app.routers.authentication import validate_token
from app.routers.issues import _update_manual_label
from app.streaming import ui_updates
from bson import ObjectId
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/manual-labels", tags=["manual-labels"])


class ManualLabelsIn(BaseModel):
    issue_ids: list[str]


class Label(typing_extensions.TypedDict):
    existence: bool | None
    property: bool | None
    executive: bool | None


class ManualLabelsOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "manual_labels": {
                "issue_id": {"existence": True, "property": True, "executive": True}
            }
        }
    })

    manual_labels: dict[str, Label]


class CommentIn(BaseModel):
    comment: str


class CommentsOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "comments": {"comment_id": {"author": "username", "comment": "string"}}
        }
    })

    comments: dict[str, dict[str, str]]


class CommentIdOut(BaseModel):
    comment_id: str


def _update_comment(issue_id: str, comment_id: str, username: str, update: dict):
    result = issue_labels_collection.update_one(
        {
            "_id": issue_id,
            f"comments.{comment_id}": {"$exists": True},
            f"comments.{comment_id}.author": {"$eq": username},
        },
        update,
    )
    if result.modified_count != 1:
        issue = issue_labels_collection.find_one({"_id": issue_id})
        if issue is None:
            raise issue_not_found_exception(issue_id)
        elif "comments" not in issue or comment_id not in issue["comments"]:
            raise comment_not_found_exception(comment_id, issue_id)
        elif issue["comments"][comment_id]["author"] != username:
            raise comment_author_exception(comment_id, issue_id)


@router.get("", response_model=ManualLabelsOut)
def get_manual_labels(request: ManualLabelsIn):
    """
    Returns the manual labels of the issue ids that were
    provided in the request body.
    """
    issues = issue_labels_collection.find(
        {
            "$and": [
                {"_id": {"$in": request.issue_ids}},
                {"tags": "has-label"},
            ]
        },
        ["existence", "property", "executive"],
    )

    # Build and send response
    labels = {}
    ids = set(request.issue_ids)
    for issue in issues:
        ids.remove(issue["_id"])
        labels[issue["_id"]] = {
            "existence": issue["existence"],
            "property": issue["property"],
            "executive": issue["executive"],
        }
    if ids:
        raise manual_labels_not_found_exception(list(ids))
    return ManualLabelsOut(manual_labels=labels)


# Endpoint for retrieving the original labels
# @router.get("", response_model=ManualLabelsOut)
# def get_manual_labels(request: ManualLabelsIn):
#     """
#     Returns the manual labels of the issue ids that were
#     provided in the request body.
#     """
#     issues = issue_labels_collection.find(
#         {
#             "$and": [
#                 {"_id": {"$in": request.issue_ids}},
#                 {"tags": "has-label"},
#             ]
#         },
#         ["comments", "existence", "property", "executive"],
#     )
#
#     # Build and send response
#     labels = {}
#     ids = set(request.issue_ids)
#     for issue in issues:
#         ids.remove(issue["_id"])
#         label = None
#         for _, comment in issue["comments"].items():
#             if comment["author"] == "original label":
#                 label = {"existence": False, "property": False, "executive": False}
#                 if "existence" in comment["comment"].lower():
#                     label["existence"] = True
#                 if "property" in comment["comment"].lower():
#                     label["property"] = True
#                 if "executive" in comment["comment"].lower():
#                     label["executive"] = True
#                 labels[issue["_id"]] = label
#                 break
#         if label is not None:
#             continue
#         labels[issue["_id"]] = {
#             "existence": issue["existence"],
#             "property": issue["property"],
#             "executive": issue["executive"],
#         }
#     if ids:
#         raise manual_labels_not_found_exception(list(ids))
#     return ManualLabelsOut(manual_labels=labels)


@router.post("/{issue_id}")
def update_manual_label(issue_id: str, request: Label, token=Depends(validate_token)):
    """
    Update the manual label of the given issue.
    """
    result = issue_labels_collection.update_one(
        {"_id": issue_id},
        {
            "$set": request,
            "$addToSet": {"tags": {"$each": ["has-label", token["username"]]}},
        },
    )
    if result.matched_count == 0:
        raise issue_not_found_exception(issue_id)
    ui_updates.send_ui_update_manual_label(issue_id)
    ui_updates.send_ui_update_tags(issue_id)


@router.get("/{issue_id}/comments", response_model=CommentsOut)
def get_comments(issue_id: str):
    """
    Gets the comments for the specified issue.
    """
    issue = issue_labels_collection.find_one({"_id": issue_id}, ["comments"])
    if issue is None:
        raise issue_not_found_exception(issue_id)
    if "comments" not in issue or issue["comments"] is None:
        return CommentsOut(comments={})
    comments = {}
    for comment_id in issue["comments"]:
        comments[str(comment_id)] = {
            "author": issue["comments"][comment_id]["author"],
            "comment": issue["comments"][comment_id]["comment"],
        }
    return CommentsOut(comments=comments)


@router.post("/{issue_id}/comments", response_model=CommentIdOut)
def add_comment(issue_id: str, request: CommentIn, token=Depends(validate_token)):
    """
    Adds a comment to the manual label of the given issue.
    """
    comment_id = ObjectId()
    _update_manual_label(
        issue_id,
        {
            "$set": {
                f"comments.{comment_id}": {
                    "author": token["username"],
                    "comment": request.comment,
                }
            },
            "$addToSet": {"tags": token["username"]},
        },
    )
    ui_updates.send_ui_update_comments(issue_id)
    ui_updates.send_ui_update_tags(issue_id)
    return CommentIdOut(comment_id=str(comment_id))


@router.patch("/{issue_id}/comments/{comment_id}")
def update_comment(
    issue_id: str, comment_id: str, request: CommentIn, token=Depends(validate_token)
):
    _update_comment(
        issue_id,
        comment_id,
        token["username"],
        {"$set": {f"comments.{comment_id}.comment": request.comment}},
    )
    ui_updates.send_ui_update_comments(issue_id)


@router.delete("/{issue_id}/comments/{comment_id}")
def delete_comment(issue_id: str, comment_id: str, token=Depends(validate_token)):
    _update_comment(
        issue_id,
        comment_id,
        token["username"],
        {"$unset": {f"comments.{comment_id}": ""}},
    )
    ui_updates.send_ui_update_comments(issue_id)
