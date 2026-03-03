from app.dependencies import jira_repos_db, projects_collection, issue_labels_collection
from app.routers.authentication import validate_token
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.util import insert_one, find_one, update_one, delete_one

router = APIRouter(prefix="/projects", tags=["projects"])


class Project(BaseModel):
    ecosystem: str
    key: str
    additional_properties: dict[str, str | list[str]]


class AdditionalProperties(BaseModel):
    additional_properties: dict[str, str | list[str]]


def fix_tags():
    tags_per_project = {}
    tags_to_remove = set()

    # Get current projects
    for project in projects_collection.find({}):
        tags = get_tags(project)
        tags_per_project[f"{project['ecosystem']}-{project['key']}"] = tags
        tags_to_remove = tags_to_remove.union(set(tags))

    # Find tags to add and remove
    for ecosystem in jira_repos_db.list_collection_names():
        for issue in jira_repos_db[ecosystem].find({}):
            key = issue["key"].split("-")[0]
            if f"{ecosystem}-{key}" not in tags_per_project:
                project = {
                    "_id": f"{ecosystem}-{key}",
                    "ecosystem": ecosystem,
                    "key": key,
                    "additional_properties": {},
                }
                projects_collection.insert_one(project)
                tags_per_project[f"{ecosystem}-{key}"] = get_tags(project)
                tags_to_remove = tags_to_remove.union(set(get_tags(project)))

    # Remove old tags first
    issue_labels_collection.update_many(
        {}, {"$pull": {"tags": {"$in": list(tags_to_remove)}}}
    )

    # Add new tags
    for ecosystem in jira_repos_db.list_collection_names():
        for issue in jira_repos_db[ecosystem].find({}):
            key = issue["key"].split("-")[0]
            issue_labels_collection.update_one(
                {"_id": f"{ecosystem}-{issue['id']}"},
                {
                    "$addToSet": {
                        "tags": {"$each": tags_per_project[f"{ecosystem}-{key}"]}
                    }
                },
            )


def get_tags(project):
    tags = [
        f"project-ecosystem={project['ecosystem']}",
        f"project-key={project['key']}",
    ]
    for property_, value in project["additional_properties"].items():
        if type(value) == list:
            for item in value:
                tags.append(f"project-{property_}={item}")
        else:
            tags.append(f"project-{property_}={value}")
    return tags


def delete_tags(project):
    tags = get_tags(project)
    issue_labels_collection.update_many(
        {"tags": f"{project['ecosystem']}-{project['key']}"},
        {"$pull": {"tags": {"$in": tags}}},
    )


def add_tags(project):
    if project["ecosystem"] not in jira_repos_db.list_collection_names():
        raise HTTPException(
            status_code=404, detail=f"ecosystem {project['ecosystem']} does not exist"
        )
    tags = get_tags(project)
    issue_labels_collection.update_many(
        {"tags": f"{project['ecosystem']}-{project['key']}"},
        {"$addToSet": {"tags": {"$each": tags}}},
    )


@router.get("", response_model=list[Project])
def get_projects():
    projects = projects_collection.find({})
    response = []
    for project in projects:
        response.append(
            Project(
                ecosystem=project["ecosystem"],
                key=project["key"],
                additional_properties=project["additional_properties"],
            )
        )
    return response


@router.post("")
def create_project(request: Project, token=Depends(validate_token)):
    project = {
        "_id": f"{request.ecosystem}-{request.key}",
        "ecosystem": request.ecosystem,
        "key": request.key,
        "additional_properties": request.additional_properties,
    }
    insert_one(projects_collection, project, "project")
    add_tags(project)


@router.get("/{ecosystem}/{project_key}", response_model=Project)
def get_project(ecosystem: str, project_key: str):
    project = find_one(projects_collection, f"{ecosystem}-{project_key}", "project")
    return Project(
        ecosystem=project["ecosystem"],
        key=project["key"],
        additional_properties=project["additional_properties"],
    )


@router.put("/{ecosystem}/{project_key}")
def update_project(
    ecosystem: str,
    project_key: str,
    request: AdditionalProperties,
    token=Depends(validate_token),
):
    project = find_one(projects_collection, f"{ecosystem}-{project_key}", "project")
    delete_tags(project)

    update_one(
        projects_collection,
        f"{ecosystem}-{project_key}",
        {"$set": {"additional_properties": request.additional_properties}},
        "project",
    )
    add_tags(
        {
            "ecosystem": ecosystem,
            "key": project_key,
            "additional_properties": request.additional_properties,
        }
    )


@router.delete("/{ecosystem}/{project_key}")
def delete_project(ecosystem: str, project_key: str, token=Depends(validate_token)):
    project = find_one(projects_collection, f"{ecosystem}-{project_key}", "project")
    delete_tags(project)
    delete_one(projects_collection, project["_id"], "project")
