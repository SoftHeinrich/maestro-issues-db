"""
Tests for the experiment router.

These tests isolate the experiment router from the rest of the application so
they can run without a live MongoDB instance or full app import side effects.
The active browser flow still uses the legacy `/tasks` and
`/submit-ratings` endpoints, so this suite focuses on that path while keeping
basic coverage for the newer session API as well.
"""

from __future__ import annotations

import copy
import importlib
import json
import sys
import threading
import types
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient


for module_name in ("app.routers.experiment", "app.routers.authentication"):
    sys.modules.pop(module_name, None)

fake_authentication = types.ModuleType("app.routers.authentication")


def validate_token():
    return {"username": "test-admin"}


fake_authentication.validate_token = validate_token
sys.modules["app.routers.authentication"] = fake_authentication

experiment = importlib.import_module("app.routers.experiment")

experiment_test_app = FastAPI()
experiment_test_app.include_router(experiment.router)
client = TestClient(experiment_test_app)


class FakeCursor:
    def __init__(self, docs: list[dict]):
        self._docs = docs

    def sort(self, key: str, direction: int):
        reverse = direction < 0
        self._docs.sort(key=lambda doc: doc.get(key), reverse=reverse)
        return self

    def limit(self, count: int):
        self._docs = self._docs[:count]
        return self

    def __iter__(self):
        return iter(self._docs)


class FakeCollection:
    def __init__(self):
        self._docs: list[dict] = []
        self._lock = threading.Lock()

    def drop(self):
        with self._lock:
            self._docs = []

    def create_index(self, *args, **kwargs):
        return kwargs.get("name", "fake_index")

    def insert_one(self, document: dict):
        item = copy.deepcopy(document)
        item.setdefault("_id", ObjectId())
        with self._lock:
            self._docs.append(item)
        return SimpleNamespace(inserted_id=item["_id"])

    def find_one(self, query: dict, projection: dict | None = None):
        with self._lock:
            for doc in self._docs:
                if _matches(doc, query):
                    return _apply_projection(copy.deepcopy(doc), projection)
        return None

    def update_one(self, query: dict, update: dict):
        with self._lock:
            for doc in self._docs:
                if _matches(doc, query):
                    _apply_update(doc, update)
                    return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    def find(self, query: dict | None = None):
        with self._lock:
            docs = [copy.deepcopy(doc) for doc in self._docs if _matches(doc, query or {})]
        return FakeCursor(docs)

    def count_documents(self, query: dict | None = None):
        with self._lock:
            return sum(1 for doc in self._docs if _matches(doc, query or {}))


class FakeDatabase:
    def __init__(self):
        self._collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str):
        if name not in self._collections:
            self._collections[name] = FakeCollection()
        return self._collections[name]


def _matches(doc: dict, query: dict):
    for key, expected in query.items():
        if doc.get(key) != expected:
            return False
    return True


def _apply_projection(doc: dict, projection: dict | None):
    if projection is None:
        return doc
    included = {key for key, value in projection.items() if value}
    if not included:
        return doc
    result = {}
    for key in included:
        if key in doc:
            result[key] = doc[key]
    return result


def _apply_update(doc: dict, update: dict):
    for operator, payload in update.items():
        if operator == "$push":
            for key, value in payload.items():
                doc.setdefault(key, []).append(copy.deepcopy(value))
            continue
        raise NotImplementedError(f"Unsupported update operator: {operator}")


def _task_definitions():
    return {
        "Component DataNode": {
            "description": "Investigate DataNode architecture decisions.",
            "questions": {
                "question1": {
                    "type": "existence",
                    "description": "What DataNode design decision was made?",
                    "design_decision": {"existence": True},
                }
            },
            "task_details": "Use at least two queries before finalizing ratings.",
            "Likert Scale": {
                "5": "Very Relevant",
                "4": "Relevant",
                "3": "Distantly Relevant",
                "2": "Less Relevant",
                "1": "Not Relevant",
            },
        },
        "Component NameNode": {
            "description": "Investigate NameNode architecture decisions.",
            "questions": {
                "question1": {
                    "type": "property",
                    "description": "Which NameNode property matters here?",
                    "design_decision": {"property": True},
                }
            },
            "task_details": "Review both direct and related issues.",
            "Likert Scale": {
                "5": "Very Relevant",
                "4": "Relevant",
                "3": "Distantly Relevant",
                "2": "Less Relevant",
                "1": "Not Relevant",
            },
        },
        "Likert Scale": {
            "5": "Very Relevant",
            "4": "Relevant",
            "3": "Distantly Relevant",
            "2": "Less Relevant",
            "1": "Not Relevant",
        },
        "task_details": "Top-level fallback instructions.",
    }


def _project_payload(project: str, project_name: str, password: str):
    return {
        "repo": "Apache",
        "project": project,
        "project_name": project_name,
        "debug": True,
        "passwords": {
            "student1": password,
            "student2": password,
        },
        "student_data": {
            "student1": {
                "tasks": [
                    {
                        "taskName": "Component DataNode",
                        "questions": {
                            "question1": {
                                "engine": "pylucene",
                                "rerank_engine": True,
                                "gpt": False,
                            }
                        },
                        "solutions": {
                            "question1": [
                                {
                                    "taskId": "Component DataNode",
                                    "questionKey": "question1",
                                    "searchQuery": "seed query",
                                    "ratings": [{"issue_id": "SEED-1", "rating": "4"}],
                                }
                            ]
                        },
                    },
                    {
                        "taskName": "Component NameNode",
                        "questions": {
                            "question1": {
                                "engine": "archrag",
                                "rerank_engine": False,
                                "gpt": True,
                            }
                        },
                        "solutions": {},
                    },
                ]
            },
            "student2": {
                "tasks": [
                    {
                        "taskName": "Component DataNode",
                        "questions": {
                            "question1": {
                                "engine": "archrag",
                                "rerank_engine": False,
                                "gpt": False,
                            }
                        },
                        "solutions": {},
                    }
                ]
            },
        },
        "task_details": _task_definitions(),
    }


def _write_project_config(config_root: Path, repo: str, project: str, payload: dict):
    project_dir = config_root / repo / project
    project_dir.mkdir(parents=True, exist_ok=True)
    with (project_dir / "experiment_data.json").open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


@pytest.fixture(autouse=True)
def experiment_env(monkeypatch, tmp_path):
    db = FakeDatabase()
    legacy_results: list[dict] = []
    legacy_results_lock = threading.Lock()
    config_root = tmp_path / "experiment_configs"

    _write_project_config(
        config_root,
        "Apache",
        "HDFS",
        _project_payload("HDFS", "Hadoop HDFS", "pw-hdfs"),
    )
    _write_project_config(
        config_root,
        "Apache",
        "LUCENE",
        _project_payload("LUCENE", "Apache Lucene", "pw-lucene"),
    )

    monkeypatch.setattr(experiment, "_get_db", lambda: db)
    monkeypatch.setattr(experiment, "_experiment_configs_dir", lambda: str(config_root))
    monkeypatch.setattr(experiment, "_load_task_definitions", _task_definitions)
    monkeypatch.setattr(experiment, "PROXY_STATE_PATH", str(tmp_path / "proxy_settings.json"))

    def fake_insert_legacy_result(result: dict):
        with legacy_results_lock:
            stored = copy.deepcopy(result)
            stored["_id"] = str(len(legacy_results) + 1)
            legacy_results.append(stored)
            return copy.deepcopy(stored)

    def fake_find_legacy_results(filters: dict, *, limit=None):
        with legacy_results_lock:
            rows = [
                copy.deepcopy(item)
                for item in legacy_results
                if all(item.get(key) == value for key, value in filters.items())
            ]
        rows.sort(
            key=lambda item: (
                item.get("created_at", datetime.min.replace(tzinfo=timezone.utc)),
                item.get("_id", ""),
            )
        )
        if limit is not None:
            rows = rows[:limit]
        return rows

    def fake_count_legacy_results(filters: dict):
        return len(fake_find_legacy_results(filters))

    monkeypatch.setattr(experiment, "_insert_legacy_result", fake_insert_legacy_result)
    monkeypatch.setattr(experiment, "_find_legacy_results", fake_find_legacy_results)
    monkeypatch.setattr(experiment, "_count_legacy_results", fake_count_legacy_results)

    yield SimpleNamespace(db=db, config_root=config_root, legacy_results=legacy_results)


def _post_legacy_rating(**overrides):
    payload = {
        "matriculationNumber": "student1",
        "taskId": "Component DataNode",
        "questionKey": "question1",
        "searchQuery": "query-1",
        "repo": "Apache",
        "project": "HDFS",
        "ratings": [{"issue_id": "HDFS-1", "rating": 5}],
    }
    payload.update(overrides)
    return client.post("/experiment/submit-ratings", json=payload)


class TestSessionApi:
    def test_create_and_append_session_results(self):
        created = client.post(
            "/experiment/sessions",
            json={"participant_id": "p1", "experiment_type": "single"},
        )
        assert created.status_code == 200

        session = created.json()["session"]
        session_id = created.json()["session_id"]
        task_name = session["tasks"][0]["task_name"]

        saved = client.post(
            f"/experiment/sessions/{session_id}/results",
            json={
                "task_name": task_name,
                "question_key": "question1",
                "query": "session query",
                "system": "pylucene_rerank",
                "results": [{"issue_id": "A-1", "rating": 5}],
            },
        )
        assert saved.status_code == 200

        fetched = client.get(f"/experiment/sessions/{session_id}")
        assert fetched.status_code == 200
        searches = fetched.json()["searches"]
        assert len(searches) == 1
        assert searches[0]["query"] == "session query"
        assert searches[0]["results"][0]["rating"] == 5


class TestLegacyTasks:
    def test_projects_endpoint_lists_available_configs(self):
        response = client.get("/experiment/projects")
        assert response.status_code == 200

        projects = {(item["repo"], item["project"]) for item in response.json()["projects"]}
        assert ("Apache", "HDFS") in projects
        assert ("Apache", "LUCENE") in projects

    def test_tasks_response_uses_selected_project_and_merges_seed_solutions(self):
        response = client.post(
            "/experiment/tasks",
            json={
                "MtrNo": "student1",
                "password": "pw-hdfs",
                "repo": "Apache",
                "project": "HDFS",
            },
        )
        assert response.status_code == 200

        payload = response.json()
        assert payload["repo"] == "Apache"
        assert payload["project"] == "HDFS"
        assert payload["project_name"] == "Hadoop HDFS"
        assert payload["debug"] is True

        tasks = payload["tasks"]
        datanode = next(task for task in tasks if task["taskName"] == "Component DataNode")
        namenode = next(task for task in tasks if task["taskName"] == "Component NameNode")

        assert datanode["questions"]["question1"]["engine"] == "pylucene"
        assert datanode["questions"]["question1"]["rerank_engine"] is True
        assert datanode["questions"]["question1"]["gpt"] is False
        assert datanode["task_details"] == "Use at least two queries before finalizing ratings."
        assert datanode["lekert_scale"]["5"] == "Very Relevant"
        assert datanode["solutions"]["question1"][0]["searchQuery"] == "seed query"

        assert namenode["questions"]["question1"]["engine"] == "archrag"
        assert namenode["questions"]["question1"]["gpt"] is True

    def test_invalid_password_is_rejected(self):
        response = client.post(
            "/experiment/tasks",
            json={"MtrNo": "student1", "password": "wrong", "repo": "Apache", "project": "HDFS"},
        )
        assert response.status_code == 401

    def test_invalid_question_key_is_rejected(self):
        response = _post_legacy_rating(questionKey="question-does-not-exist")
        assert response.status_code == 400


class TestLegacyPersistence:
    def test_submit_ratings_persists_postgres_row_and_reloads_into_tasks(self, experiment_env):
        response = _post_legacy_rating(searchQuery="persisted query")
        assert response.status_code == 200

        stored = list(experiment_env.legacy_results)
        assert len(stored) == 1
        assert stored[0]["repo"] == "Apache"
        assert stored[0]["project"] == "HDFS"
        assert stored[0]["project_name"] == "Hadoop HDFS"
        assert stored[0]["engine"] == "pylucene"
        assert stored[0]["rerank_engine"] is True
        assert stored[0]["gpt"] is False
        assert stored[0]["ratings"][0]["rating"] == "5"

        tasks = client.post(
            "/experiment/tasks",
            json={"MtrNo": "student1", "password": "pw-hdfs", "repo": "Apache", "project": "HDFS"},
        ).json()["tasks"]
        datanode = next(task for task in tasks if task["taskName"] == "Component DataNode")

        solutions = datanode["solutions"]["question1"]
        assert [item["searchQuery"] for item in solutions] == ["seed query", "persisted query"]

    def test_duplicate_submissions_are_stored_as_distinct_rows(self, experiment_env):
        first = _post_legacy_rating(searchQuery="same-query", ratings=[{"issue_id": "HDFS-1", "rating": 2}])
        second = _post_legacy_rating(searchQuery="same-query", ratings=[{"issue_id": "HDFS-1", "rating": 5}])

        assert first.status_code == 200
        assert second.status_code == 200

        exported = client.get(
            "/experiment/legacy-results",
            params={"repo": "Apache", "project": "HDFS", "matriculation_number": "student1"},
        )
        assert exported.status_code == 200
        results = exported.json()["results"]
        same_query = [row for row in results if row["searchQuery"] == "same-query"]
        assert len(same_query) == 2
        assert [row["ratings"][0]["rating"] for row in same_query] == ["2", "5"]

    def test_reload_then_change_rating_keeps_both_versions(self):
        first_load = client.post(
            "/experiment/tasks",
            json={"MtrNo": "student1", "password": "pw-hdfs", "repo": "Apache", "project": "HDFS"},
        )
        assert first_load.status_code == 200

        first_save = _post_legacy_rating(searchQuery="change-me", ratings=[{"issue_id": "HDFS-9", "rating": 2}])
        assert first_save.status_code == 200

        second_load = client.post(
            "/experiment/tasks",
            json={"MtrNo": "student1", "password": "pw-hdfs", "repo": "Apache", "project": "HDFS"},
        )
        assert second_load.status_code == 200

        second_save = _post_legacy_rating(searchQuery="change-me", ratings=[{"issue_id": "HDFS-9", "rating": 5}])
        assert second_save.status_code == 200

        final_tasks = client.post(
            "/experiment/tasks",
            json={"MtrNo": "student1", "password": "pw-hdfs", "repo": "Apache", "project": "HDFS"},
        ).json()["tasks"]

        datanode = next(task for task in final_tasks if task["taskName"] == "Component DataNode")
        changed_rows = [
            row for row in datanode["solutions"]["question1"]
            if row["searchQuery"] == "change-me"
        ]
        assert len(changed_rows) == 2
        assert [row["ratings"][0]["rating"] for row in changed_rows] == ["2", "5"]

    def test_concurrent_submits_do_not_lose_updates(self):
        def submit(index: int):
            with TestClient(experiment_test_app) as threaded_client:
                response = threaded_client.post(
                    "/experiment/submit-ratings",
                    json={
                        "matriculationNumber": "student1",
                        "taskId": "Component DataNode",
                        "questionKey": "question1",
                        "searchQuery": f"concurrent-{index}",
                        "repo": "Apache",
                        "project": "HDFS",
                        "ratings": [{"issue_id": f"HDFS-{index}", "rating": 5}],
                    },
                )
                return response.status_code

        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(submit, range(12)))

        assert statuses == [200] * 12

        results = client.get(
            "/experiment/legacy-results",
            params={"repo": "Apache", "project": "HDFS", "matriculation_number": "student1", "limit": 50},
        ).json()["results"]
        concurrent_rows = [row for row in results if row["searchQuery"].startswith("concurrent-")]
        assert len(concurrent_rows) == 12

    def test_concurrent_loads_and_submits_remain_consistent(self):
        failures: list[str] = []

        def submit(index: int):
            with TestClient(experiment_test_app) as threaded_client:
                response = threaded_client.post(
                    "/experiment/submit-ratings",
                    json={
                        "matriculationNumber": "student1",
                        "taskId": "Component DataNode",
                        "questionKey": "question1",
                        "searchQuery": f"mixed-{index}",
                        "repo": "Apache",
                        "project": "HDFS",
                        "ratings": [{"issue_id": f"HDFS-{index}", "rating": 4}],
                    },
                )
                if response.status_code != 200:
                    failures.append(f"submit-{index}:{response.status_code}")

        def load_tasks():
            with TestClient(experiment_test_app) as threaded_client:
                response = threaded_client.post(
                    "/experiment/tasks",
                    json={"MtrNo": "student1", "password": "pw-hdfs", "repo": "Apache", "project": "HDFS"},
                )
                if response.status_code != 200:
                    failures.append(f"load:{response.status_code}")
                    return
                payload = response.json()
                if "tasks" not in payload:
                    failures.append("load:missing-tasks")

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = []
            for index in range(10):
                futures.append(pool.submit(submit, index))
                futures.append(pool.submit(load_tasks))
            for future in futures:
                future.result()

        assert failures == []

        tasks = client.post(
            "/experiment/tasks",
            json={"MtrNo": "student1", "password": "pw-hdfs", "repo": "Apache", "project": "HDFS"},
        ).json()["tasks"]
        datanode = next(task for task in tasks if task["taskName"] == "Component DataNode")
        mixed_rows = [
            row for row in datanode["solutions"]["question1"]
            if row["searchQuery"].startswith("mixed-")
        ]
        assert len(mixed_rows) == 10
