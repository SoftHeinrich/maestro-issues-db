from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from app.dependencies import (
    issue_labels_collection,
    jira_repos_db,
    models_collection,
    repo_info_collection,
)
from app.exceptions import (
    ui_sort_exception,
    version_not_specified_exception,
    model_not_found_exception,
    version_not_found_exception,
)
from app.sanitize import sanitize_mongo_filter
from bson import ObjectId
import math

router = APIRouter(prefix="/ui", tags=["ui"])


class Query(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "filter": "object",
            "sort": "predictions.model_id-version_id.existence",
            "sort_ascending": True,
            "models": ["model_id-version_id"],
            "page": 42,
            "limit": 42,
        }
    })

    filter: dict
    sort: str | None
    sort_ascending: bool
    models: list[str]
    page: int
    limit: int


class ManualLabel(BaseModel):
    existence: bool | None
    property: bool | None
    executive: bool | None


class UIData(BaseModel):
    issue_id: str
    issue_link: str
    issue_key: str
    summary: str | None
    description: str | None
    manual_label: ManualLabel
    predictions: dict[str, dict | None]
    tags: list[str]
    comments: dict[str, dict[str, str]]


class UIDataOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "data": [
                {
                    "issue_id": "string",
                    "issue_link": "string",
                    "issue_key": "string",
                    "summary": "string",
                    "description": "string",
                    "manual_label": {
                        "existence": True,
                        "property": False,
                        "executive": True,
                    },
                    "predictions": {
                        "model_id-version_id": {
                            "existence": {"prediction": False, "confidence": 0.42}
                        }
                    },
                    "tags": ["example-tag"],
                    "comments": {
                        "comment_id": {
                            "author": "username",
                            "comment": "sample comment",
                        }
                    },
                }
            ],
            "total_pages": 42,
        }
    })

    data: list[UIData]
    total_pages: int


@router.post("", response_model=UIDataOut)
def get_ui_data(request: Query):
    page = request.page - 1
    limit = request.limit
    safe_filter = sanitize_mongo_filter(request.filter)
    total_pages = math.ceil(
        issue_labels_collection.count_documents(safe_filter) / limit
    )

    for model in request.models:
        if len(model.split("-")) != 2:
            raise version_not_specified_exception(model)
        model_id = model.split("-")[0]
        version_id = model.split("-")[1]
        db_model = models_collection.find_one({"_id": ObjectId(model_id)})
        if db_model is None:
            raise model_not_found_exception(model_id)
        if version_id not in db_model["versions"]:
            raise version_not_found_exception(version_id, model_id)

    if request.sort is not None and request.sort.startswith("predictions."):
        sort_parts = request.sort.split(".")
        if len(sort_parts) >= 2:
            sort_model = sort_parts[1]
            if len(sort_model.split("-")) == 2:
                sort_model_id = sort_model.split("-")[0]
                sort_version_id = sort_model.split("-")[1]
                db_model = models_collection.find_one({"_id": ObjectId(sort_model_id)})
                if db_model is None:
                    raise model_not_found_exception(sort_model_id)
                if sort_version_id not in db_model["versions"]:
                    raise version_not_found_exception(sort_version_id, sort_model_id)

    if request.sort is not None:
        sort_direction = 1 if request.sort_ascending else -1
        issues = (
            issue_labels_collection.find(safe_filter)
            .sort(request.sort, sort_direction)
            .skip(page * limit)
            .limit(limit)
        )
    else:
        issues = (
            issue_labels_collection.find(safe_filter).skip(page * limit).limit(limit)
        )

    response = []
    for issue in issues:
        issue_data = jira_repos_db[issue["_id"].split("-")[0]].find_one(
            {"id": issue["_id"].split("-")[1]},
            ["key", "fields.summary", "fields.description"],
        )
        issue_link_prefix = repo_info_collection.find_one(
            {"_id": issue["_id"].split("-")[0]}
        )["issue_link_prefix"]
        predictions = {}
        for model in request.models:
            if "predictions" in issue and model in issue["predictions"]:
                predictions[model] = issue["predictions"][model]
        response.append(
            UIData(
                issue_id=issue["_id"],
                issue_link=f'{issue_link_prefix}/browse/{issue_data["key"]}',
                issue_key=issue_data["key"],
                summary=issue_data["fields"]["summary"],
                description=issue_data["fields"]["description"],
                manual_label=ManualLabel(
                    existence=issue["existence"],
                    property=issue["property"],
                    executive=issue["executive"],
                ),
                predictions=predictions,
                tags=issue["tags"],
                comments=issue["comments"],
            )
        )
    return UIDataOut(data=response, total_pages=total_pages)
