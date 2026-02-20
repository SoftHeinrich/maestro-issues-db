import json

from app.dependencies import jira_repos_db, statistics_collection
from app.routers.authentication import validate_token
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/statistics", tags=["statistics"])


class Filter(BaseModel):
    issue_ids: list


class Statistic(BaseModel):
    issue_type: str | None
    resolution: str | None
    created: str | None
    resolutiondate: str | None
    hierarchy: list[str] | None
    status: str | None
    labels: list[str] | None
    num_pdf_attachments: int | None
    num_attachments: int | None
    watches: int | None
    votes: int | None
    summary: str | None
    description: str | None
    comments: list[str] | None


class Statistics(BaseModel):
    data: dict[str, Statistic]


def get_value(fields, path):
    current_item = fields
    keys = path.split("/")
    for key in keys:
        if key not in current_item or current_item[key] is None:
            return None
        current_item = current_item[key]
    return current_item


def stream_statistics(issues):
    yield '{"data": {'

    first_item = True
    for issue in issues:
        issue_id = issue["_id"]
        del issue["_id"]
        if first_item:
            yield f'"{issue_id}": {json.dumps(issue)}'
            first_item = False
        else:
            yield f',"{issue_id}": {json.dumps(issue)}'

    yield "}}"


@router.get("", response_model=Statistics)
def get_statistics(request: Filter):
    issues = statistics_collection.find({"_id": {"$in": request.issue_ids}})
    return StreamingResponse(stream_statistics(issues), media_type="text/event-stream")


@router.post("/calculate")
def calculate_statistics(token=Depends(validate_token)):
    for repo in jira_repos_db.list_collection_names():
        for issue in jira_repos_db[repo].find({}):
            issue_type = get_value(issue["fields"], "issuetype/name")
            resolution = get_value(issue["fields"], "resolution/name")
            created = get_value(issue["fields"], "created")
            resolutiondate = get_value(issue["fields"], "resolutiondate")
            subtasks = get_value(issue["fields"], "subtasks")
            if subtasks is not None:
                hierarchy = [f"{repo}-{subtask['id']}" for subtask in subtasks]
            else:
                hierarchy = []
            status = get_value(issue["fields"], "status/name")
            labels = get_value(issue["fields"], "labels")
            attachments = get_value(issue["fields"], "attachment")
            if attachments is None:
                attachments = []
            num_pdf_attachments = len(
                [
                    attachment
                    for attachment in attachments
                    if ".pdf" in attachment["filename"]
                ]
            )
            num_attachments = len(attachments)
            watches = get_value(issue["fields"], "watches/watchCount")
            votes = get_value(issue["fields"], "votes/votes")
            summary = get_value(issue["fields"], "summary")
            description = get_value(issue["fields"], "description")
            comments = get_value(issue["fields"], "comment/comments")
            if comments is None:
                comments = []
            comments = [comment["body"] for comment in comments]
            statistics_collection.update_one(
                {"_id": f"{repo}-{issue['id']}"},
                {
                    "$set": {
                        "issue_type": issue_type,
                        "resolution": resolution,
                        "created": created,
                        "resolutiondate": resolutiondate,
                        "hierarchy": hierarchy,
                        "status": status,
                        "labels": labels,
                        "num_pdf_attachments": num_pdf_attachments,
                        "num_attachments": num_attachments,
                        "watches": watches,
                        "votes": votes,
                        "summary": summary,
                        "description": description,
                        "comments": comments,
                    }
                },
                upsert=True,
            )
