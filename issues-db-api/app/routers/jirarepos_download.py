from app.dependencies import repo_info_collection
from app.exceptions import (
    repo_exists_exception,
    repo_not_exists_exception,
    wrong_date_format,
    wrong_batch_size,
    wrong_wait_time,
)
from app.jirarepos_download import download_multiprocessed
from app.routers.authentication import validate_token
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from datetime import date
import re

router = APIRouter(prefix="/jira-repos", tags=["jira-repos"])


class RequestIn(BaseModel):
    repos: list[str] | None
    enable_auth: bool
    username: str | None
    password: str | None


class Repo(BaseModel):
    repo_name: str
    repo_url: str
    download_date: str | None
    batch_size: int
    query_wait_time_minutes: float


class RepoUpdate(BaseModel):
    repo_url: str
    download_date: str | None
    batch_size: int
    query_wait_time_minutes: float


def download_repo(repo_info, request):
    download_date = date.today()
    download_multiprocessed(
        repo_info["_id"],
        repo_info["repo_url"],
        repo_info["download_date"],
        repo_info["batch_size"],
        repo_info["query_wait_time_minutes"],
        enable_auth=request.enable_auth,
        username=request.username,
        password=request.password,
    )
    repo_info_collection.update_one(
        {"_id": repo_info["_id"]},
        {"$set": {"download_date": str(download_date)}},
    )


def validate_repo_info(request):
    if request.download_date is not None:
        if re.search("[0-9]{4}-[0-1][1-9]-[0-3][1-9]", request.download_date) is None:
            raise wrong_date_format(request.download_date)

    if request.batch_size <= 0:
        raise wrong_batch_size(request.batch_size)

    if request.query_wait_time_minutes < 0.0:
        raise wrong_wait_time(request.query_wait_time_minutes)


@router.post("-download")
def jira_repos_download(request: RequestIn, token=Depends(validate_token)):
    """
    Endpoint for downloading or updating the issue data from JiraRepos. When setting
    repos to null, the endpoint updates the issue data from all the repos that are
    currently in the database. Repos can also be a list of strings, where each string
    is a repo name. In this case, the endpoint only updates the issue data from the
    specified repos. Optionally, authentication can be used for updating certain repos.
    In this case, only specify the repos for which the authentication credentials are
    valid.
    :param token:
    :param request:
    :return:
    """
    if request.repos is None:
        for repo_info in repo_info_collection.find({}):
            download_repo(repo_info, request)
    else:
        for repo in request.repos:
            repo_info = repo_info_collection.find_one({"_id": repo})
            if repo_info is None:
                raise repo_not_exists_exception(repo)
            download_repo(repo_info, request)


@router.get("", response_model=list[Repo])
def get_repo_info():
    """
    Get the information about all the repos that are currently in the database.
    :return:
    """
    repos = repo_info_collection.find({})
    response = []
    for repo in repos:
        response.append(
            Repo(
                repo_name=repo["_id"],
                repo_url=repo["repo_url"],
                download_date=repo["download_date"],
                batch_size=repo["batch_size"],
                query_wait_time_minutes=repo["query_wait_time_minutes"],
            )
        )
    return response


@router.post("")
def add_repo(request: Repo, token=Depends(validate_token)):
    """
    Add the information about a repo, so the jira-repos-download endpoint can download
    issue data from the repo.
    :param request:
    :param token:
    :return:
    """
    if repo_info_collection.find_one({"_id": request.repo_name}) is not None:
        raise repo_exists_exception(request.repo_name)
    validate_repo_info(request)
    repo_info_collection.insert_one(
        {
            "_id": request.repo_name,
            "repo_url": request.repo_url,
            "download_date": request.download_date,
            "batch_size": request.batch_size,
            "query_wait_time_minutes": request.query_wait_time_minutes,
        }
    )


@router.put("/{repo_name}")
def update_repo(repo_name: str, request: RepoUpdate, token=Depends(validate_token)):
    """
    Update the information about a repo.
    :param repo_name:
    :param request:
    :param token:
    :return:
    """
    validate_repo_info(request)
    result = repo_info_collection.update_one(
        {"_id": repo_name},
        {
            "$set": {
                "repo_url": request.repo_url,
                "download_date": request.download_date,
                "batch_size": request.batch_size,
                "query_wait_time_minutes": request.query_wait_time_minutes,
            }
        },
    )
    if result.matched_count == 0:
        raise repo_not_exists_exception(repo_name)


@router.delete("/{repo_name}")
def delete_repo(repo_name: str, token=Depends(validate_token)):
    """
    Delete the information about a repo.
    :param repo_name:
    :param token:
    :return:
    """
    result = repo_info_collection.delete_one({"_id": repo_name})
    if result.deleted_count == 0:
        raise repo_not_exists_exception(repo_name)
