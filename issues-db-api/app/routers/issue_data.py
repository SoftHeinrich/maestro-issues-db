import typing
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from app.dependencies import jira_repos_db, repo_info_collection, active_ecosystems
from app.exceptions import (
    get_attr_required_exception,
    duplicate_issue_exception,
    attribute_not_found_exception,
    issues_not_found_exception,
)

router = APIRouter(prefix="/issue-data", tags=["issue-data"])

default_value = {
    "summary": "",
    "description": "",
    "labels": [],
    "components": [],
    "votes": 0,
    "watches": 0,
    "parent": None,
    "issuelinks": [],
    "attachments": [],
    "sub-tasks": [],
    "resolution": None,
    "assignee": None,
    "resolutiondate": None,
}


class IssueDataIn(BaseModel):
    issue_ids: list[str]
    attributes: list[str]


class IssueDataOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "data": {
                "issue_id": {"attribute_name": "attribute_value (can be any type)"}
            }
        }
    })

    data: dict[str, dict[str, typing.Any]]


def streaming_issue_data(request: IssueDataIn):
    yield '{"data": {'
    # Collect the ids belonging to each Jira repo
    ids = dict()
    for jira_name in active_ecosystems:
        ids[jira_name] = []
    for issue_id in request.issue_ids:
        split_id = issue_id.split("-")
        # First part is the jira repo name, second part is the id
        ids[split_id[0]].append(split_id[1])

    first_item = True
    for jira_name in active_ecosystems:
        issues = jira_repos_db[jira_name].find(
            {"id": {"$in": ids[jira_name]}},
            ["id", "key"]
            + [
                f"fields.{attr}"
                for attr in request.attributes
                if attr not in ["key", "link"]
            ],
        )

        issue_link_prefix = None
        remaining_ids = set(ids[jira_name])
        for issue in issues:
            if issue_link_prefix is None:
                issue_link_prefix = repo_info_collection.find_one({"_id": jira_name})[
                    "issue_link_prefix"
                ]
            if issue["id"] not in remaining_ids:
                raise duplicate_issue_exception(jira_name, issue["id"])
            remaining_ids.remove(issue["id"])
            attributes = {}
            for attr in request.attributes:
                if attr == "key":
                    if issue[attr] is None:
                        raise get_attr_required_exception(
                            attr, f'{jira_name}-{issue["id"]}'
                        )
                    attributes[attr] = issue[attr]
                elif attr == "link":
                    attributes[attr] = f'{issue_link_prefix}/browse/{issue["key"]}'
                elif attr not in issue["fields"]:
                    if attr == "parent":
                        attributes[attr] = None
                    else:
                        raise attribute_not_found_exception(
                            attr, jira_name, issue["id"]
                        )
                elif issue["fields"][attr] is not None:
                    # Attribute exists
                    if attr in "issuelinks":
                        issuelinks = issue["fields"][attr]
                        for idx in range(len(issuelinks)):
                            if "outwardIssue" in issuelinks[idx]:
                                issuelinks[idx][
                                    "outwardIssue"
                                ] = f'{jira_name}-{issuelinks[idx]["outwardIssue"]["id"]}'
                            if "inwardIssue" in issuelinks[idx]:
                                issuelinks[idx][
                                    "inwardIssue"
                                ] = f'{jira_name}-{issuelinks[idx]["inwardIssue"]["id"]}'
                        attributes[attr] = issuelinks
                    elif attr == "parent":
                        attributes[attr] = f'{jira_name}-{issue["fields"][attr]["id"]}'
                    elif attr == "subtasks":
                        subtasks = []
                        for subtask in issue["fields"][attr]:
                            subtasks.append(f'{jira_name}-{subtask["id"]}')
                        attributes[attr] = subtasks
                    else:
                        attributes[attr] = issue["fields"][attr]
                elif attr not in list(default_value.keys()):
                    # Attribute does not exist, but is required
                    raise get_attr_required_exception(
                        attr, f'{jira_name}-{issue["id"]}'
                    )
                else:
                    # Use default value for attribute
                    attributes[attr] = default_value[attr]
            if first_item:
                yield f'"{jira_name}-{issue["id"]}": {json.dumps(attributes)}'
                first_item = False
            else:
                yield f',"{jira_name}-{issue["id"]}": {json.dumps(attributes)}'
        if remaining_ids:
            raise issues_not_found_exception(
                [f"{jira_name}-{id_}" for id_ in remaining_ids]
            )
    yield "}}"


@router.get("", response_model=IssueDataOut)
def get_issue_data(request: IssueDataIn):
    """
    Returns issue data. The returned data is determined by the
    specified issue ids and the attributes that are requested.
    """
    return StreamingResponse(
        streaming_issue_data(request), media_type="text/event-stream"
    )
