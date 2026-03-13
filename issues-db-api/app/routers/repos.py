from fastapi import APIRouter
from pydantic import BaseModel
from app.dependencies import jira_repos_db, projects_collection, active_ecosystems

router = APIRouter(prefix="/repos", tags=["repos"])


class Repos(BaseModel):
    repos: list[str]


class Projects(BaseModel):
    projects: list[str]


@router.get("")
def get_jira_repos() -> Repos:
    return Repos(repos=list(active_ecosystems))


@router.get("/{repo_name}/projects")
def get_repo_projects(repo_name: str) -> Projects:
    projects = projects_collection.find({"ecosystem": repo_name}, ["key"])
    return Projects(projects=[project["key"] for project in projects])
