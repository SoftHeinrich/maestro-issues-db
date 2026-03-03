from fastapi import HTTPException


def tag_exists_exception(tag: str):
    return HTTPException(status_code=409, detail=f"Tag {tag} already exists")


def tag_not_found_exception(tag: str):
    return HTTPException(status_code=404, detail=f"Tag {tag} not found")


def tag_exists_for_issue_exception(tag: str, issue_id: str):
    return HTTPException(
        status_code=409, detail=f"Tag {tag} already exists for issue {issue_id}"
    )


def non_existing_tag_for_issue_exception(tag: str, issue_id: str):
    return HTTPException(
        status_code=404, detail=f"Tag {tag} does not exist for issue {issue_id}"
    )


def illegal_tag_insertion_exception(tag: str):
    return HTTPException(
        status_code=404,
        detail=f"The following tag may not be inserted: {tag}, because it does not exist",
    )


def illegal_tags_insertion_exception(tags: list[str]):
    return HTTPException(
        status_code=404,
        detail=f"The following tags may not be inserted: {tags}, because they do not exist",
    )


def issues_not_found_exception(issue_ids: list[str]):
    return HTTPException(
        status_code=404, detail=f"The following issues were not found: {issue_ids}"
    )


def issue_not_found_exception(issue_id: str):
    return HTTPException(status_code=404, detail=f"Issue {issue_id} was not found")


def model_not_found_exception(model_id: str):
    return HTTPException(status_code=404, detail=f"Model {model_id} was not found")


def version_not_found_exception(version_id: str, model_id: str):
    return HTTPException(
        status_code=404,
        detail=f'Version "{version_id}" was not found for model "{model_id}"',
    )


def performance_not_found_exception(performance_time: str, model_id: str):
    return HTTPException(
        status_code=404,
        detail=f'Performance {performance_time.replace("_", ".")} for model {model_id} was not found',
    )


def embedding_not_found_exception(embedding_id: str):
    return HTTPException(
        status_code=404, detail=f'Embedding "{embedding_id}" was not found'
    )


def embedding_file_not_found_exception(embedding_id: str):
    return HTTPException(
        status_code=404, detail=f'File for embedding "{embedding_id}" was not found'
    )


def bson_exception(e: str):
    return HTTPException(status_code=422, detail=f"BSON exception: {e}")


def attribute_not_found_exception(attr: str, jira_name: str, issue_id: int):
    return HTTPException(
        status_code=404,
        detail=f'Attribute "{attr}" is not found for issue: {jira_name}-{issue_id}',
    )


def get_attr_required_exception(attribute: str, issue_id: str):
    return HTTPException(
        status_code=409,
        detail=f'Attribute "{attribute}" is required for issue "{issue_id}"',
    )


def duplicate_issue_exception(jira_name: str, issue_id: int):
    return HTTPException(
        status_code=409,
        detail=f"Duplicate issue in the database: {jira_name}-{issue_id}",
    )


def manual_labels_not_found_exception(issue_ids: list[str]):
    return HTTPException(
        status_code=404,
        detail=f"The following issues do not have a manual label: {issue_ids}",
    )


def comment_not_found_exception(comment_id: str, issue_id: str):
    return HTTPException(
        status_code=404, detail=f"Comment {comment_id} not found for issue {issue_id}"
    )


def repo_not_found_exception(repo_name: str):
    return HTTPException(
        status_code=404, detail=f"Jira repository {repo_name} not found"
    )


def comment_author_exception(comment_id: str, issue_id: str):
    return HTTPException(
        status_code=403,
        detail=f"You are not the author of comment {comment_id} of issue {issue_id}",
    )


def ui_sort_exception(syntax_error: str):
    return HTTPException(status_code=422, detail=f"Cannot sort on: {syntax_error}")


def version_not_specified_exception(model: str):
    return HTTPException(
        status_code=422, detail=f"Version not specified for model: {model}"
    )


def file_not_found_exception(file_id: str):
    return HTTPException(status_code=404, detail=f"File {file_id} not found")


def repo_exists_exception(repo_name: str):
    return HTTPException(status_code=409, detail=f"The repo {repo_name} already exists")


def repo_not_exists_exception(repo_name: str):
    return HTTPException(status_code=404, detail=f"The repo {repo_name} does not exist")


def url_not_working_exception(url: str):
    return HTTPException(status_code=502, detail=f"The url does not work: {url}")


def wrong_date_format(date: str):
    return HTTPException(
        status_code=422,
        detail=f"Date {date} should have the following format: YYYY-mm-dd",
    )


def wrong_batch_size(batch_size: int):
    return HTTPException(
        status_code=422,
        detail=f"batch_size {batch_size} should be greater than 0",
    )


def wrong_wait_time(query_wait_time_minutes: float):
    return HTTPException(
        status_code=422,
        detail=f"query_wait_time_minutes {query_wait_time_minutes} should be greater "
        f"than or equal to 0.0",
    )
