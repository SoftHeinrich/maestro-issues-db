from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from app.dependencies import issue_labels_collection, tags_collection, jira_repos_db
from app.routers.authentication import validate_token
from app.exceptions import (
    illegal_tags_insertion_exception,
    issues_not_found_exception,
    repo_not_found_exception,
    issue_not_found_exception,
)

router = APIRouter(prefix="/bulk", tags=["bulk"])


class IssueTags(BaseModel):
    issue_id: str
    tags: list[str]


class AddTagsIn(BaseModel):
    data: list[IssueTags]


class IssueKeysIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"issue_keys": ["repo_name-issue_key"]}})

    issue_keys: list[str]


class IssueIdsOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"issue_ids": {"repo_name-issue_key": "issue_id"}}})

    issue_ids: dict[str, str]


class TagsIn(BaseModel):
    issue_ids: list[str]


class TagsOut(BaseModel):
    data: dict[str, list[str]]


@router.post("/add-tags")
def add_tags_in_bulk(request: AddTagsIn, token=Depends(validate_token)):
    """
    Method for adding tags to issues in bulk. The tags and
    issue ids should be specified in the request body.
    """
    # Check if tags may be inserted
    tags = set()
    for issue in request.data:
        for tag in issue.tags:
            tags.add(tag)
    allowed_tags = tags_collection.find({"type": "manual-tag"}, ["_id"])
    allowed_tags = set([tag["_id"] for tag in allowed_tags])
    if not tags.issubset(allowed_tags):
        raise illegal_tags_insertion_exception(list(tags - allowed_tags))

    # Add tags
    not_found_keys = set()
    for issue in request.data:
        result = issue_labels_collection.update_one(
            {"_id": issue.issue_id}, {"$addToSet": {"tags": {"$each": issue.tags}}}
        )
        if result.matched_count == 0:
            not_found_keys.add(issue.issue_id)
    if not_found_keys:
        raise issues_not_found_exception(list(not_found_keys))


@router.get("/get-issue-ids-from-keys", response_model=IssueIdsOut)
def get_issue_ids_from_keys(request: IssueKeysIn):
    issues = dict()
    for issue_key in request.issue_keys:
        repo = issue_key.split("-")[0]
        key = "-".join(issue_key.split("-")[1:])
        if repo not in jira_repos_db.list_collection_names():
            raise repo_not_found_exception(repo)
        if repo not in issues:
            issues[repo] = []
        issues[repo].append(key)

        # Find the ids for each repo
    issue_ids = {}
    for repo, issue_keys in issues.items():
        for issue_key in issue_keys:
            issue = jira_repos_db[repo].find_one({"key": issue_key})
            if issue is None:
                raise issue_not_found_exception(f"{repo}-{issue_key}")
            issue_ids[f"{repo}-{issue_key}"] = f'{repo}-{issue["id"]}'
    return IssueIdsOut(issue_ids=issue_ids)


@router.get("/tags", response_model=TagsOut)
def get_tags(request: TagsIn):
    data = {}
    for issue_id in request.issue_ids:
        issue = issue_labels_collection.find_one({"_id": issue_id}, ["tags"])
        data[issue_id] = issue["tags"]
    return {"data": data}
