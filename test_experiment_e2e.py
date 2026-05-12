"""
Project-selection end-to-end test for the legacy experiment flow.

Flow:
1. Discover available experiment projects.
2. Fetch Lucene mock tasks from the project-specific config.
3. Run one PyLucene search and one archRag search.
4. Submit ratings back into the Lucene project config.
5. Verify the saved metadata is still scoped to the selected project.

Run:
    python3 test_experiment_e2e.py

Requires:
    - Traefik, issues-db-api, search-engine, archrag running
    - project config at issues-db-api/app/experiment_configs/Apache/LUCENE/experiment_data.json
    - matching PyLucene index and archRag store for LUCENE
"""

import json
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = "https://maestro.localhost:4269"
API = f"{BASE}/issues-db-api"
SEARCH_ENGINE = f"{BASE}/search-engine"
ARCHRAG = f"{BASE}/archrag"
VERIFY_SSL = False

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "issues-db-api" / "app"
PROJECT_CONFIG_DIR = APP_DIR / "experiment_configs" / "Apache" / "LUCENE"
PROJECT_DATA = PROJECT_CONFIG_DIR / "experiment_data.json"
PROJECT_QUERIES = PROJECT_CONFIG_DIR / "experiment_queries.json"

TEST_REPO = "Apache"
TEST_PROJECT = "LUCENE"
TEST_PROJECT_NAME = "Apache Lucene"
TEST_STUDENT = "mock_lucene_001"
TEST_TASK = "Component IndexWriter"

passed = 0
failed = 0
errors = []


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        message = f"  ✗ {name}: {detail}"
        print(message)
        errors.append(message)


def section(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def request_json(method, url, **kwargs):
    response = requests.request(method, url, verify=VERIFY_SSL, timeout=120, **kwargs)
    try:
        payload = response.json()
    except Exception:
        payload = None
    return response, payload


def find_question(task, engine):
    for qkey, question in task["questions"].items():
        if question["engine"] == engine:
            return qkey, question
    raise RuntimeError(f"No {engine} question found in task {task['taskName']}")


def pylucene_request_for(question, query_spec):
    if question.get("rerank_engine"):
        return query_spec["pylucene_rerank_request"]
    return query_spec["pylucene_request"]


def submit_ratings(task_name, question_key, query, results):
    ratings = [
        {"issue_id": str(item["issue_id"]), "rating": 4}
        for item in results[: min(5, len(results))]
    ]
    response, payload = request_json(
        "POST",
        f"{API}/experiment/submit-ratings",
        json={
            "matriculationNumber": TEST_STUDENT,
            "taskId": task_name,
            "questionKey": question_key,
            "searchQuery": query,
            "repo": TEST_REPO,
            "project": TEST_PROJECT,
            "ratings": ratings,
        },
    )
    check(f"submit ratings for {task_name}/{question_key}", response.status_code == 200, payload)


def main():
    if not PROJECT_DATA.exists() or not PROJECT_QUERIES.exists():
        raise SystemExit(
            "Generate project configs first with issues-db-api/app/generate_mock_experiment_configs.py"
        )

    with open(PROJECT_QUERIES, "r") as handle:
        project_queries = json.load(handle)["tasks"]

    section("1. Service Health Checks")
    response, payload = request_json("GET", f"{API}/models")
    check("issues-db-api reachable", response.status_code == 200, response.status_code)

    response, payload = request_json("GET", f"{SEARCH_ENGINE}/index-status")
    check("search-engine reachable", response.status_code == 200, response.status_code)

    response, payload = request_json("GET", f"{ARCHRAG}/health")
    check("archrag reachable", response.status_code == 200, response.status_code)
    check("archrag has a loaded or cached store", bool(payload and payload.get("store_loaded")), payload)

    section("2. Discover Projects")
    response, payload = request_json("GET", f"{API}/experiment/projects")
    check("project list endpoint works", response.status_code == 200, payload)
    check("project list shape", isinstance(payload, dict) and "projects" in payload, payload)
    lucene_project = next(
        (item for item in payload["projects"] if item["repo"] == TEST_REPO and item["project"] == TEST_PROJECT),
        None,
    )
    check("Lucene project is selectable", lucene_project is not None, payload)

    section("3. Fetch Project Tasks")
    response, payload = request_json(
        "POST",
        f"{API}/experiment/tasks",
        json={
            "MtrNo": TEST_STUDENT,
            "password": TEST_STUDENT,
            "repo": TEST_REPO,
            "project": TEST_PROJECT,
        },
    )
    check("project-scoped login works", response.status_code == 200, payload)
    check("tasks response shape", isinstance(payload, dict) and "tasks" in payload, payload)
    check("response repo matches selection", payload.get("repo") == TEST_REPO, payload)
    check("response project matches selection", payload.get("project") == TEST_PROJECT, payload)
    check("response project_name matches selection", payload.get("project_name") == TEST_PROJECT_NAME, payload)

    tasks = payload["tasks"]
    lucene_task = next(task for task in tasks if task["taskName"] == TEST_TASK)
    check("task has repo metadata", lucene_task.get("repo") == TEST_REPO, lucene_task)
    check("task has project metadata", lucene_task.get("project") == TEST_PROJECT, lucene_task)

    pylucene_qkey, pylucene_question = find_question(lucene_task, "pylucene")
    archrag_qkey, archrag_question = find_question(lucene_task, "archrag")
    pylucene_query_spec = project_queries[lucene_task["taskName"]]["questions"][pylucene_qkey]
    archrag_query_spec = project_queries[lucene_task["taskName"]]["questions"][archrag_qkey]

    section("4. PyLucene Search")
    response, payload = request_json(
        "POST",
        f"{SEARCH_ENGINE}/search",
        json=pylucene_request_for(pylucene_question, pylucene_query_spec),
    )
    check("pylucene search status", response.status_code == 200, payload)
    check("pylucene search result", payload and payload.get("result") == "done", payload)
    pylucene_results = (payload or {}).get("payload", [])
    check("pylucene returns results", len(pylucene_results) > 0, len(pylucene_results))

    section("5. archRag Search")
    response, payload = request_json(
        "POST",
        f"{ARCHRAG}/search",
        json=archrag_query_spec["archrag_request"],
    )
    check("archrag search status", response.status_code == 200, payload)
    check("archrag search result", payload and payload.get("result") == "done", payload)
    archrag_results = (payload or {}).get("payload", [])
    check("archrag returns results", len(archrag_results) > 0, len(archrag_results))

    section("6. Submit Ratings")
    submit_ratings(
        lucene_task["taskName"],
        pylucene_qkey,
        pylucene_query_spec["query"],
        pylucene_results,
    )
    submit_ratings(
        lucene_task["taskName"],
        archrag_qkey,
        archrag_query_spec["query"],
        archrag_results,
    )

    response, payload = request_json(
        "POST",
        f"{API}/experiment/tasks",
        json={
            "MtrNo": TEST_STUDENT,
            "password": TEST_STUDENT,
            "repo": TEST_REPO,
            "project": TEST_PROJECT,
        },
    )
    refreshed_task = next(task for task in payload["tasks"] if task["taskName"] == lucene_task["taskName"])
    matching = [
        item for item in refreshed_task["solutions"][pylucene_qkey]
        if item.get("searchQuery") == pylucene_query_spec["query"]
    ]
    check("saved solution is returned", len(matching) > 0, refreshed_task["solutions"][pylucene_qkey])
    saved = matching[-1]
    check("saved solution keeps repo", saved.get("repo") == TEST_REPO, saved)
    check("saved solution keeps project", saved.get("project") == TEST_PROJECT, saved)
    check("saved solution keeps project_name", saved.get("project_name") == TEST_PROJECT_NAME, saved)
    check("saved solution keeps engine", saved.get("engine") == pylucene_question["engine"], saved)

    section("Summary")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    if errors:
        print("\nErrors:")
        for error in errors:
            print(error)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
