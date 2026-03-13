"""
Comprehensive E2E tests for the experiment router.

Tests both the MongoDB-based experiment system (sessions, results, export)
and the legacy file-based experiment system (tasks, ratings, logs).

Designed to reveal actual bugs in validation, data integrity, and API behavior.
"""

import json
import os
import shutil
import glob
from unittest.mock import patch

import pytest
from pymongo import MongoClient

from .test_util import client

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_experiment_db():
    return MongoClient(MONGO_URL)["MaestroExperiment"]


def _clean_experiment_db():
    db = _get_experiment_db()
    db["experiment_sessions"].drop()


def _experiment_data_path():
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "experiment_data.json",
    )


def _backup_experiment_data():
    path = _experiment_data_path()
    backup = path + ".test_backup"
    if os.path.exists(path):
        shutil.copy2(path, backup)
    return backup


def _restore_experiment_data(backup_path):
    path = _experiment_data_path()
    if os.path.exists(backup_path):
        shutil.copy2(backup_path, path)
        os.remove(backup_path)


def _write_test_experiment_data():
    """Minimal but realistic experiment_data.json for testing."""
    data = {
        "student_data": {
            "test_e2e_001": {
                "tasks": [
                    {
                        "taskName": "Component DataNode",
                        "engine": "pylucene",
                        "rerank_engine": True,
                        "gpt": False,
                        "solutions": {},
                    },
                    {
                        "taskName": "Component NameNode",
                        "engine": "archrag",
                        "rerank_engine": False,
                        "gpt": False,
                        "solutions": {},
                    },
                    {
                        "taskName": "Requirement Scalability",
                        "engine": "pylucene",
                        "rerank_engine": False,
                        "gpt": True,
                        "solutions": {},
                    },
                ]
            },
            "test_e2e_002": {
                "tasks": [
                    {
                        "taskName": "Component DataNode",
                        "engine": "archrag",
                        "rerank_engine": False,
                        "gpt": False,
                        "solutions": {},
                    }
                ]
            },
        },
        "task_details": {
            "Component DataNode": {
                "description": "Test description for DataNode",
                "questions": {
                    "question1": {
                        "type": "existence",
                        "description": "Test question 1",
                        "design_decision": {"existence": True},
                    },
                    "question2": {
                        "type": "property",
                        "description": "Test question 2",
                        "design_decision": {"property": True},
                    },
                },
                "task_details": "Instructions: execute at least two queries.",
                "Likert Scale": {
                    "5": "Very Relevant",
                    "4": "Relevant",
                    "3": "Distantly Relevant",
                    "2": "Less Relevant",
                    "1": "Not Relevant",
                },
            },
            "Component NameNode": {
                "description": "Test description for NameNode",
                "questions": {
                    "question1": {
                        "type": "existence",
                        "description": "Test question 1 for NameNode",
                        "design_decision": {"existence": True},
                    }
                },
                "task_details": "Instructions: search for NameNode info.",
                "Likert Scale": {
                    "5": "Very Relevant",
                    "4": "Relevant",
                    "3": "Distantly Relevant",
                    "2": "Less Relevant",
                    "1": "Not Relevant",
                },
            },
            "Requirement Scalability": {
                "description": "Test description for Scalability",
                "questions": {
                    "question1": {
                        "type": "existence",
                        "description": "Test question 1 for Scalability",
                        "design_decision": {"existence": True},
                    }
                },
                "task_details": "Instructions: search for Scalability info.",
                "Likert Scale": {
                    "5": "Very Relevant",
                    "4": "Relevant",
                    "3": "Distantly Relevant",
                    "2": "Less Relevant",
                    "1": "Not Relevant",
                },
            },
        },
    }
    with open(_experiment_data_path(), "w") as f:
        json.dump(data, f, indent=4)
    return data


def _cleanup_test_logs():
    """Remove log files created by POST /logs during tests."""
    log_dir = os.path.dirname(os.path.abspath(__file__))
    for log_file in glob.glob(os.path.join(log_dir, "logs_*.log")):
        os.remove(log_file)


# ===================================================================
# MongoDB-based experiment endpoints
# ===================================================================

class TestCreateSession:

    def setup_method(self):
        _clean_experiment_db()

    def teardown_method(self):
        _clean_experiment_db()

    def test_single_session_structure(self):
        resp = client.post("/experiment/sessions", json={
            "participant_id": "p001",
            "experiment_type": "single",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        session = data["session"]
        assert session["participant_id"] == "p001"
        assert session["experiment_type"] == "single"
        assert session["searches"] == []
        assert len(session["tasks"]) > 0

        for assignment in session["system_assignments"].values():
            assert "assigned_system" in assignment
            assert assignment["assigned_system"] in ("pylucene_rerank", "archrag")

    def test_dual_session_column_mapping(self):
        resp = client.post("/experiment/sessions", json={
            "participant_id": "p002",
            "experiment_type": "dual",
        })
        assert resp.status_code == 200
        session = resp.json()["session"]

        for assignment in session["system_assignments"].values():
            m = assignment["column_mapping"]
            assert set(m.keys()) == {"left", "right"}
            assert set(m.values()) == {"pylucene_rerank", "archrag"}

    def test_invalid_experiment_type(self):
        resp = client.post("/experiment/sessions", json={
            "participant_id": "p003",
            "experiment_type": "invalid",
        })
        assert resp.status_code == 400

    def test_deterministic_assignment(self):
        """Same participant_id must produce identical assignments."""
        resp1 = client.post("/experiment/sessions", json={
            "participant_id": "stable_user",
            "experiment_type": "single",
        })
        _clean_experiment_db()
        resp2 = client.post("/experiment/sessions", json={
            "participant_id": "stable_user",
            "experiment_type": "single",
        })
        assert (resp1.json()["session"]["system_assignments"]
                == resp2.json()["session"]["system_assignments"])

    def test_counterbalancing(self):
        """Across many participants, both systems appear as first assignment."""
        first_systems = set()
        for i in range(20):
            _clean_experiment_db()
            resp = client.post("/experiment/sessions", json={
                "participant_id": f"cbal_{i}",
                "experiment_type": "single",
            })
            assignments = resp.json()["session"]["system_assignments"]
            first_task = list(assignments.keys())[0]
            first_systems.add(assignments[first_task]["assigned_system"])
        assert first_systems == {"pylucene_rerank", "archrag"}

    def test_tasks_match_definitions(self):
        resp = client.post("/experiment/sessions", json={
            "participant_id": "p_match",
            "experiment_type": "single",
        })
        session_task_names = {t["task_name"] for t in resp.json()["session"]["tasks"]}

        defs_resp = client.get("/experiment/task-definitions")
        def_names = set(defs_resp.json()["tasks"].keys())
        assert session_task_names == def_names

    def test_duplicate_participant_allowed(self):
        """BUG: no uniqueness constraint — duplicate sessions created silently."""
        r1 = client.post("/experiment/sessions", json={
            "participant_id": "dup",
            "experiment_type": "single",
        })
        r2 = client.post("/experiment/sessions", json={
            "participant_id": "dup",
            "experiment_type": "single",
        })
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["session_id"] != r2.json()["session_id"]


class TestGetSession:

    def setup_method(self):
        _clean_experiment_db()

    def teardown_method(self):
        _clean_experiment_db()

    def test_get_created_session(self):
        sid = client.post("/experiment/sessions", json={
            "participant_id": "get_me",
            "experiment_type": "single",
        }).json()["session_id"]

        resp = client.get(f"/experiment/sessions/{sid}")
        assert resp.status_code == 200
        assert resp.json()["participant_id"] == "get_me"
        assert resp.json()["_id"] == sid

    def test_not_found(self):
        resp = client.get("/experiment/sessions/000000000000000000000000")
        assert resp.status_code == 404

    def test_invalid_object_id(self):
        resp = client.get("/experiment/sessions/not-an-objectid")
        assert resp.status_code == 404


class TestSubmitResults:

    def setup_method(self):
        _clean_experiment_db()

    def teardown_method(self):
        _clean_experiment_db()

    def _create_session(self, pid="rater", etype="single"):
        r = client.post("/experiment/sessions", json={
            "participant_id": pid,
            "experiment_type": etype,
        })
        s = r.json()
        return s["session_id"], s["session"]

    def test_single_submit(self):
        sid, session = self._create_session()
        task_name = session["tasks"][0]["task_name"]

        resp = client.post(f"/experiment/sessions/{sid}/results", json={
            "task_name": task_name,
            "question_key": "question1",
            "query": "test query",
            "system": "pylucene_rerank",
            "results": [
                {"issue_id": "A-1", "rating": 5},
                {"issue_id": "A-2", "rating": 3},
            ],
        })
        assert resp.status_code == 200

        searches = client.get(f"/experiment/sessions/{sid}").json()["searches"]
        assert len(searches) == 1
        assert searches[0]["query"] == "test query"
        assert searches[0]["system"] == "pylucene_rerank"
        assert len(searches[0]["results"]) == 2

    def test_dual_submit(self):
        sid, session = self._create_session(etype="dual")
        task_name = session["tasks"][0]["task_name"]

        resp = client.post(f"/experiment/sessions/{sid}/results", json={
            "task_name": task_name,
            "question_key": "question1",
            "query": "dual query",
            "results_left": [{"issue_id": "L-1", "rating": 4}],
            "results_right": [{"issue_id": "R-1", "rating": 2}],
        })
        assert resp.status_code == 200
        search = client.get(f"/experiment/sessions/{sid}").json()["searches"][0]
        assert len(search["results_left"]) == 1
        assert len(search["results_right"]) == 1

    def test_multiple_submissions_append(self):
        sid, session = self._create_session()
        task_name = session["tasks"][0]["task_name"]

        for i in range(3):
            client.post(f"/experiment/sessions/{sid}/results", json={
                "task_name": task_name,
                "question_key": "question1",
                "query": f"q{i}",
                "system": "archrag",
                "results": [{"issue_id": f"X-{i}", "rating": 5}],
            })

        searches = client.get(f"/experiment/sessions/{sid}").json()["searches"]
        assert len(searches) == 3

    def test_invalid_session(self):
        resp = client.post(
            "/experiment/sessions/000000000000000000000000/results",
            json={
                "task_name": "T",
                "question_key": "q1",
                "query": "x",
                "results": [],
            },
        )
        assert resp.status_code == 404

    def test_no_task_name_validation(self):
        """BUG: server accepts results for non-existent task names."""
        sid, _ = self._create_session()
        resp = client.post(f"/experiment/sessions/{sid}/results", json={
            "task_name": "FAKE TASK THAT DOES NOT EXIST",
            "question_key": "question99",
            "query": "garbage",
            "system": "pylucene_rerank",
            "results": [{"issue_id": "FAKE-1", "rating": 999}],
        })
        # Accepted with no validation — garbage data gets stored
        assert resp.status_code == 200

    def test_no_rating_range_validation(self):
        """BUG: server accepts arbitrary rating values (not limited to 1-5)."""
        sid, session = self._create_session()
        task_name = session["tasks"][0]["task_name"]
        resp = client.post(f"/experiment/sessions/{sid}/results", json={
            "task_name": task_name,
            "question_key": "question1",
            "query": "bad ratings",
            "system": "pylucene_rerank",
            "results": [
                {"issue_id": "A-1", "rating": -100},
                {"issue_id": "A-2", "rating": 99999},
            ],
        })
        assert resp.status_code == 200

    def test_empty_results(self):
        sid, session = self._create_session()
        resp = client.post(f"/experiment/sessions/{sid}/results", json={
            "task_name": session["tasks"][0]["task_name"],
            "question_key": "question1",
            "query": "empty",
            "system": "pylucene_rerank",
            "results": [],
        })
        assert resp.status_code == 200

    def test_gpt_keywords_flag_stored(self):
        sid, session = self._create_session()
        client.post(f"/experiment/sessions/{sid}/results", json={
            "task_name": session["tasks"][0]["task_name"],
            "question_key": "question1",
            "query": "gpt enhanced",
            "system": "pylucene_rerank",
            "use_gpt_keywords": True,
            "results": [{"issue_id": "G-1", "rating": 5}],
        })
        search = client.get(f"/experiment/sessions/{sid}").json()["searches"][0]
        assert search["use_gpt_keywords"] is True

    def test_timestamp_stored(self):
        sid, session = self._create_session()
        ts = "2026-03-12T10:00:00.000Z"
        client.post(f"/experiment/sessions/{sid}/results", json={
            "task_name": session["tasks"][0]["task_name"],
            "question_key": "question1",
            "query": "ts test",
            "system": "pylucene_rerank",
            "timestamp": ts,
            "results": [],
        })
        search = client.get(f"/experiment/sessions/{sid}").json()["searches"][0]
        assert search["timestamp"] == ts


class TestTaskDefinitions:

    def test_returns_tasks(self):
        resp = client.get("/experiment/task-definitions")
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        assert "likert_scale" in data
        assert "instructions" in data
        assert len(data["tasks"]) >= 6

    def test_excludes_metadata_keys(self):
        tasks = client.get("/experiment/task-definitions").json()["tasks"]
        assert "task_details" not in tasks
        assert "Likert Scale" not in tasks

    def test_each_task_has_questions(self):
        tasks = client.get("/experiment/task-definitions").json()["tasks"]
        for name, task in tasks.items():
            assert "description" in task, f"'{name}' missing description"
            assert "questions" in task, f"'{name}' missing questions"
            assert len(task["questions"]) > 0, f"'{name}' has 0 questions"


class TestExport:

    def setup_method(self):
        _clean_experiment_db()

    def teardown_method(self):
        _clean_experiment_db()

    def test_export_empty(self):
        resp = client.get("/experiment/export")
        assert resp.status_code == 200
        assert resp.json()["sessions"] == []
        assert "exported_at" in resp.json()

    def test_export_includes_searches(self):
        r = client.post("/experiment/sessions", json={
            "participant_id": "exp_user",
            "experiment_type": "single",
        })
        sid = r.json()["session_id"]
        task_name = r.json()["session"]["tasks"][0]["task_name"]

        client.post(f"/experiment/sessions/{sid}/results", json={
            "task_name": task_name,
            "question_key": "question1",
            "query": "export q",
            "system": "pylucene_rerank",
            "results": [{"issue_id": "E-1", "rating": 5}],
        })

        export = client.get("/experiment/export").json()
        assert len(export["sessions"]) == 1
        assert len(export["sessions"][0]["searches"]) == 1

    def test_export_no_auth(self):
        """BUG: export endpoint requires no authentication — all data is public."""
        client.cookies.clear()
        resp = client.get("/experiment/export")
        assert resp.status_code == 200


# ===================================================================
# Legacy file-based experiment endpoints
# ===================================================================

class TestLegacyGetTasks:

    _backup = None

    def setup_method(self):
        self._backup = _backup_experiment_data()
        _write_test_experiment_data()

    def teardown_method(self):
        _restore_experiment_data(self._backup)

    def test_valid_user(self):
        resp = client.post("/experiment/tasks", json={"MtrNo": "test_e2e_001"})
        assert resp.status_code == 200
        tasks = resp.json()
        assert len(tasks) == 3
        names = [t["taskName"] for t in tasks]
        assert "Component DataNode" in names
        assert "Component NameNode" in names
        assert "Requirement Scalability" in names

    def test_unknown_user(self):
        resp = client.post("/experiment/tasks", json={"MtrNo": "nonexistent"})
        assert resp.status_code == 404

    def test_engine_field_returned(self):
        tasks = client.post(
            "/experiment/tasks", json={"MtrNo": "test_e2e_001"}
        ).json()
        engines = {t["taskName"]: t["engine"] for t in tasks}
        assert engines["Component DataNode"] == "pylucene"
        assert engines["Component NameNode"] == "archrag"
        assert engines["Requirement Scalability"] == "pylucene"

    def test_rerank_and_gpt_flags(self):
        tasks = client.post(
            "/experiment/tasks", json={"MtrNo": "test_e2e_001"}
        ).json()
        dn = next(t for t in tasks if t["taskName"] == "Component DataNode")
        assert dn["rerank_engine"] is True
        assert dn["gpt"] is False

        sc = next(t for t in tasks if t["taskName"] == "Requirement Scalability")
        assert sc["rerank_engine"] is False
        assert sc["gpt"] is True

    def test_description_populated(self):
        tasks = client.post(
            "/experiment/tasks", json={"MtrNo": "test_e2e_001"}
        ).json()
        for t in tasks:
            assert t.get("description") is not None, \
                f"'{t['taskName']}' has null description"

    def test_questions_populated(self):
        tasks = client.post(
            "/experiment/tasks", json={"MtrNo": "test_e2e_001"}
        ).json()
        dn = next(t for t in tasks if t["taskName"] == "Component DataNode")
        assert "question1" in dn["questions"]
        assert dn["questions"]["question1"]["type"] == "existence"

    def test_task_details_field(self):
        """BUG: task_details in response is always None.

        Root cause: experiment.py line 361 reads
            data.get("task_details", {}).get("task_details")
        which looks for a key called 'task_details' inside the top-level
        task_details dict (whose keys are task names like 'Component DataNode').
        The key 'task_details' doesn't exist at that level, so it returns None.

        Should be:
            task_details.get("task_details")
        to read from the per-task definition.
        """
        tasks = client.post(
            "/experiment/tasks", json={"MtrNo": "test_e2e_001"}
        ).json()
        for t in tasks:
            # This assertion will FAIL, exposing the bug:
            # task_details is None instead of the instructions string
            assert t.get("task_details") is not None, (
                f"BUG: task_details is None for '{t['taskName']}'. "
                f"Expected instructions string. "
                f"Fix: experiment.py line 361 should read from "
                f"per-task dict, not top-level dict."
            )

    def test_likert_scale_populated(self):
        tasks = client.post(
            "/experiment/tasks", json={"MtrNo": "test_e2e_001"}
        ).json()
        for t in tasks:
            assert t.get("lekert_scale") is not None, \
                f"'{t['taskName']}' has null lekert_scale"
            assert "5" in t["lekert_scale"]
            assert "1" in t["lekert_scale"]

    def test_empty_solutions_for_new_user(self):
        tasks = client.post(
            "/experiment/tasks", json={"MtrNo": "test_e2e_001"}
        ).json()
        for t in tasks:
            assert t["solutions"] == {}

    def test_second_user_gets_own_tasks(self):
        tasks = client.post(
            "/experiment/tasks", json={"MtrNo": "test_e2e_002"}
        ).json()
        assert len(tasks) == 1
        assert tasks[0]["taskName"] == "Component DataNode"
        assert tasks[0]["engine"] == "archrag"


class TestLegacySubmitRatings:
    """Legacy submit-ratings tests.

    Note: _create_backup is patched because the .bak file may be owned by
    root (created by Docker), causing PermissionError in local tests.
    """

    _backup = None
    _patcher = None

    def setup_method(self):
        self._backup = _backup_experiment_data()
        _write_test_experiment_data()
        # Patch backup to avoid PermissionError on root-owned .bak file
        self._patcher = patch(
            "app.routers.experiment._create_backup", lambda path: None
        )
        self._patcher.start()

    def teardown_method(self):
        self._patcher.stop()
        _restore_experiment_data(self._backup)

    def _submit(self, **overrides):
        payload = {
            "matriculationNumber": "test_e2e_001",
            "taskId": "Component DataNode",
            "questionKey": "question1",
            "searchQuery": "default query",
            "ratings": [{"issue_id": "Apache-100", "rating": 5}],
        }
        payload.update(overrides)
        return client.post("/experiment/submit-ratings", json=payload)

    def test_valid_submission(self):
        resp = self._submit()
        assert resp.status_code == 200
        assert resp.json()["success"] == "Result saved successfully"

    def test_solution_persisted(self):
        self._submit(searchQuery="persist check")
        tasks = client.post(
            "/experiment/tasks", json={"MtrNo": "test_e2e_001"}
        ).json()
        dn = next(t for t in tasks if t["taskName"] == "Component DataNode")
        sols = dn["solutions"]["question1"]
        assert len(sols) == 1
        assert sols[0]["searchQuery"] == "persist check"

    def test_engine_recorded(self):
        self._submit()
        tasks = client.post(
            "/experiment/tasks", json={"MtrNo": "test_e2e_001"}
        ).json()
        dn = next(t for t in tasks if t["taskName"] == "Component DataNode")
        assert dn["solutions"]["question1"][0]["engine"] == "pylucene"

    def test_archrag_engine_recorded(self):
        self._submit(taskId="Component NameNode")
        tasks = client.post(
            "/experiment/tasks", json={"MtrNo": "test_e2e_001"}
        ).json()
        nn = next(t for t in tasks if t["taskName"] == "Component NameNode")
        assert nn["solutions"]["question1"][0]["engine"] == "archrag"

    def test_int_rating_stored_as_string(self):
        self._submit(ratings=[{"issue_id": "A-1", "rating": 4}])
        tasks = client.post(
            "/experiment/tasks", json={"MtrNo": "test_e2e_001"}
        ).json()
        dn = next(t for t in tasks if t["taskName"] == "Component DataNode")
        assert dn["solutions"]["question1"][0]["ratings"][0]["rating"] == "4"

    def test_string_rating_accepted(self):
        resp = self._submit(ratings=[{"issue_id": "A-1", "rating": "5"}])
        assert resp.status_code == 200

    def test_invalid_user(self):
        resp = self._submit(matriculationNumber="nobody")
        assert resp.status_code == 400

    def test_invalid_task(self):
        resp = self._submit(taskId="NONEXISTENT")
        assert resp.status_code == 400

    def test_no_question_key_validation(self):
        """BUG: accepts any questionKey — no validation against task questions."""
        resp = self._submit(questionKey="question_does_not_exist")
        assert resp.status_code == 200  # accepted despite invalid key

    def test_no_rating_range_validation(self):
        """BUG: accepts ratings outside 1-5 range."""
        resp = self._submit(ratings=[{"issue_id": "A-1", "rating": 999}])
        assert resp.status_code == 200

    def test_negative_rating_accepted(self):
        """BUG: negative ratings are accepted."""
        resp = self._submit(ratings=[{"issue_id": "A-1", "rating": -1}])
        assert resp.status_code == 200

    def test_multiple_submissions_append(self):
        for i in range(3):
            self._submit(searchQuery=f"query_{i}")

        tasks = client.post(
            "/experiment/tasks", json={"MtrNo": "test_e2e_001"}
        ).json()
        dn = next(t for t in tasks if t["taskName"] == "Component DataNode")
        assert len(dn["solutions"]["question1"]) == 3

    def test_cross_user_isolation(self):
        self._submit(matriculationNumber="test_e2e_001")
        tasks = client.post(
            "/experiment/tasks", json={"MtrNo": "test_e2e_002"}
        ).json()
        dn = next(t for t in tasks if t["taskName"] == "Component DataNode")
        assert dn["solutions"] == {}

    def test_empty_ratings_list(self):
        resp = self._submit(ratings=[])
        assert resp.status_code == 200

    def test_multiple_ratings_per_search(self):
        resp = self._submit(ratings=[
            {"issue_id": "A-1", "rating": 5},
            {"issue_id": "A-2", "rating": 4},
            {"issue_id": "A-3", "rating": 3},
            {"issue_id": "A-4", "rating": 2},
            {"issue_id": "A-5", "rating": 1},
        ])
        assert resp.status_code == 200
        tasks = client.post(
            "/experiment/tasks", json={"MtrNo": "test_e2e_001"}
        ).json()
        dn = next(t for t in tasks if t["taskName"] == "Component DataNode")
        assert len(dn["solutions"]["question1"][0]["ratings"]) == 5


class TestLegacyLogs:

    def setup_method(self):
        _cleanup_test_logs()

    def teardown_method(self):
        _cleanup_test_logs()

    def test_save_log(self):
        resp = client.post("/experiment/logs", json={
            "level": "info",
            "message": "test log message",
            "timestamp": "2026-03-12T10:00:00.000Z",
        })
        assert resp.status_code == 200
        assert resp.json()["success"] == "Log saved successfully"

    def test_error_level(self):
        resp = client.post("/experiment/logs", json={
            "level": "error",
            "message": "test error",
            "timestamp": "2026-03-12T10:00:01.000Z",
        })
        assert resp.status_code == 200


# ===================================================================
# Tests with real experiment data from maestro-toolkit
# ===================================================================

_TOOLKIT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..", "maestro-toolkit",
)

REAL_DATA_FILES = []
for _experiment_dir in ("data_experiment", "data_experiment_2"):
    for _subdir in ("data12", "data13"):
        _path = os.path.join(_TOOLKIT_DIR, _experiment_dir, _subdir, "experiment_data.json")
        if os.path.exists(_path):
            REAL_DATA_FILES.append(_path)


def _real_data_id(path):
    """Generate readable test ID from path like 'data_experiment/data13'."""
    parts = path.split(os.sep)
    return f"{parts[-3]}/{parts[-2]}"


@pytest.mark.skipif(
    not REAL_DATA_FILES,
    reason="maestro-toolkit/data_experiment not available",
)
class TestRealExperimentData:
    """Tests using real experiment JSON configs from Ajay's maestro-toolkit."""

    _backup = None

    def setup_method(self):
        self._backup = _backup_experiment_data()

    def teardown_method(self):
        _restore_experiment_data(self._backup)

    def _load_real_data(self, path):
        shutil.copy2(path, _experiment_data_path())
        with open(path) as f:
            return json.load(f)

    @pytest.mark.parametrize("data_file", REAL_DATA_FILES,
                             ids=[_real_data_id(p) for p in REAL_DATA_FILES])
    def test_all_students_loadable(self, data_file):
        """Every student ID in the config should return tasks successfully."""
        data = self._load_real_data(data_file)
        for student_id in data["student_data"]:
            resp = client.post("/experiment/tasks", json={"MtrNo": student_id})
            assert resp.status_code == 200, \
                f"Failed to load tasks for {student_id} in {data_file}"
            tasks = resp.json()
            assert len(tasks) >= 1, f"{student_id} has no tasks"

    @pytest.mark.parametrize("data_file", REAL_DATA_FILES,
                             ids=[_real_data_id(p) for p in REAL_DATA_FILES])
    def test_task_names_match_definitions(self, data_file):
        """Every taskName in student data must exist in task_details."""
        data = self._load_real_data(data_file)
        task_defs = {k for k in data["task_details"]
                     if k not in ("task_details", "Likert Scale")}

        for student_id, sdata in data["student_data"].items():
            for task in sdata["tasks"]:
                assert task["taskName"] in task_defs, (
                    f"Student {student_id} has task '{task['taskName']}' "
                    f"which is not in task_details"
                )

    @pytest.mark.parametrize("data_file", REAL_DATA_FILES,
                             ids=[_real_data_id(p) for p in REAL_DATA_FILES])
    def test_engine_defaults_to_pylucene(self, data_file):
        """Real data has no 'engine' field — API should default to 'pylucene'."""
        data = self._load_real_data(data_file)
        first_student = list(data["student_data"].keys())[0]

        resp = client.post("/experiment/tasks", json={"MtrNo": first_student})
        tasks = resp.json()
        for t in tasks:
            assert t["engine"] == "pylucene", (
                f"Task '{t['taskName']}' engine should default to 'pylucene', "
                f"got '{t['engine']}'"
            )

    @pytest.mark.parametrize("data_file", REAL_DATA_FILES,
                             ids=[_real_data_id(p) for p in REAL_DATA_FILES])
    def test_descriptions_populated(self, data_file):
        """Every task should have a non-null description from task_details."""
        data = self._load_real_data(data_file)
        first_student = list(data["student_data"].keys())[0]

        resp = client.post("/experiment/tasks", json={"MtrNo": first_student})
        for t in resp.json():
            assert t.get("description") is not None, \
                f"Task '{t['taskName']}' has null description"
            assert len(t["description"]) > 10, \
                f"Task '{t['taskName']}' description too short"

    @pytest.mark.parametrize("data_file", REAL_DATA_FILES,
                             ids=[_real_data_id(p) for p in REAL_DATA_FILES])
    def test_questions_populated(self, data_file):
        """Every task should have questions with type and design_decision."""
        data = self._load_real_data(data_file)
        first_student = list(data["student_data"].keys())[0]

        resp = client.post("/experiment/tasks", json={"MtrNo": first_student})
        for t in resp.json():
            assert t.get("questions"), \
                f"Task '{t['taskName']}' has no questions"
            for qkey, qval in t["questions"].items():
                assert "type" in qval, \
                    f"'{t['taskName']}'.{qkey} missing type"
                assert "design_decision" in qval, \
                    f"'{t['taskName']}'.{qkey} missing design_decision"

    @pytest.mark.parametrize("data_file", REAL_DATA_FILES,
                             ids=[_real_data_id(p) for p in REAL_DATA_FILES])
    def test_likert_scale_consistency(self, data_file):
        """BUG DETECTOR: Some tasks (e.g. DataNode in data12) lack per-task
        Likert Scale. The API should still return a valid scale for every task,
        falling back to the top-level Likert Scale if needed."""
        data = self._load_real_data(data_file)
        first_student = list(data["student_data"].keys())[0]

        resp = client.post("/experiment/tasks", json={"MtrNo": first_student})
        for t in resp.json():
            scale = t.get("lekert_scale")
            if scale is None:
                pytest.fail(
                    f"BUG: lekert_scale is None for '{t['taskName']}'. "
                    f"The per-task definition is missing 'Likert Scale' — "
                    f"the API should fall back to the top-level scale."
                )

    @pytest.mark.parametrize("data_file", REAL_DATA_FILES,
                             ids=[_real_data_id(p) for p in REAL_DATA_FILES])
    def test_task_details_instructions(self, data_file):
        """BUG DETECTOR: task_details instructions should be populated.
        Some tasks (e.g. DataNode in data12) lack per-task 'task_details' key."""
        data = self._load_real_data(data_file)
        first_student = list(data["student_data"].keys())[0]

        resp = client.post("/experiment/tasks", json={"MtrNo": first_student})
        for t in resp.json():
            if t.get("task_details") is None:
                # Check if the per-task definition actually has task_details
                td = data["task_details"].get(t["taskName"], {})
                if "task_details" not in td:
                    pytest.fail(
                        f"BUG: task_details is None for '{t['taskName']}' and "
                        f"the per-task definition also lacks it. "
                        f"Should fall back to top-level task_details string."
                    )

    @pytest.mark.parametrize("data_file", REAL_DATA_FILES,
                             ids=[_real_data_id(p) for p in REAL_DATA_FILES])
    def test_existing_solutions_preserved(self, data_file):
        """Students with existing solutions should see them in the response."""
        data = self._load_real_data(data_file)

        for student_id, sdata in data["student_data"].items():
            has_solutions = any(
                t["solutions"] for t in sdata["tasks"]
            )
            if not has_solutions:
                continue

            resp = client.post("/experiment/tasks", json={"MtrNo": student_id})
            tasks = resp.json()

            for orig_task in sdata["tasks"]:
                if not orig_task["solutions"]:
                    continue
                api_task = next(
                    t for t in tasks if t["taskName"] == orig_task["taskName"]
                )
                for qkey, solutions in orig_task["solutions"].items():
                    assert qkey in api_task["solutions"], (
                        f"{student_id}/{orig_task['taskName']}/{qkey}: "
                        f"solutions missing in API response"
                    )
                    assert len(api_task["solutions"][qkey]) == len(solutions), (
                        f"{student_id}/{orig_task['taskName']}/{qkey}: "
                        f"expected {len(solutions)} solutions, "
                        f"got {len(api_task['solutions'][qkey])}"
                    )
            break  # Only check first student with solutions to keep test fast

    @pytest.mark.parametrize("data_file", REAL_DATA_FILES,
                             ids=[_real_data_id(p) for p in REAL_DATA_FILES])
    @patch("app.routers.experiment._create_backup", lambda path: None)
    def test_submit_and_retrieve_with_real_data(self, data_file):
        """Submit new ratings against real data and verify they persist."""
        data = self._load_real_data(data_file)
        student_id = list(data["student_data"].keys())[0]
        task_name = data["student_data"][student_id]["tasks"][0]["taskName"]

        resp = client.post("/experiment/submit-ratings", json={
            "matriculationNumber": student_id,
            "taskId": task_name,
            "questionKey": "question1",
            "searchQuery": "e2e real data test",
            "ratings": [
                {"issue_id": "Apache-99999", "rating": 5},
                {"issue_id": "Apache-99998", "rating": 3},
            ],
        })
        assert resp.status_code == 200

        # Verify persisted
        tasks = client.post(
            "/experiment/tasks", json={"MtrNo": student_id}
        ).json()
        task = next(t for t in tasks if t["taskName"] == task_name)
        q1_solutions = task["solutions"].get("question1", [])
        # Find our submission
        our = [s for s in q1_solutions if s["searchQuery"] == "e2e real data test"]
        assert len(our) == 1
        assert our[0]["ratings"][0]["issue_id"] == "Apache-99999"


# ===================================================================
# Full workflow integration tests
# ===================================================================

class TestFullWorkflow:

    def setup_method(self):
        _clean_experiment_db()

    def teardown_method(self):
        _clean_experiment_db()

    def test_single_experiment_e2e(self):
        """Create → get → submit × 2 → verify → export."""
        # create
        r = client.post("/experiment/sessions", json={
            "participant_id": "wf_single",
            "experiment_type": "single",
        })
        sid = r.json()["session_id"]
        session = r.json()["session"]
        task = session["tasks"][0]
        system = session["system_assignments"][task["task_name"]]["assigned_system"]

        # get
        assert client.get(f"/experiment/sessions/{sid}").status_code == 200

        # submit query 1
        client.post(f"/experiment/sessions/{sid}/results", json={
            "task_name": task["task_name"],
            "question_key": "question1",
            "query": "first query",
            "system": system,
            "results": [
                {"issue_id": "W-1", "rating": 5},
                {"issue_id": "W-2", "rating": 4},
            ],
        })

        # submit query 2
        client.post(f"/experiment/sessions/{sid}/results", json={
            "task_name": task["task_name"],
            "question_key": "question1",
            "query": "second query",
            "system": system,
            "results": [
                {"issue_id": "W-3", "rating": 3},
            ],
        })

        # verify
        s = client.get(f"/experiment/sessions/{sid}").json()
        assert len(s["searches"]) == 2
        assert s["searches"][0]["query"] == "first query"
        assert s["searches"][1]["query"] == "second query"

        # export
        export = client.get("/experiment/export").json()
        assert len(export["sessions"]) == 1
        assert export["sessions"][0]["_id"] == sid

    def test_dual_experiment_e2e(self):
        """Dual: create → submit with left/right → verify mapping."""
        r = client.post("/experiment/sessions", json={
            "participant_id": "wf_dual",
            "experiment_type": "dual",
        })
        sid = r.json()["session_id"]
        session = r.json()["session"]
        task = session["tasks"][0]
        mapping = session["system_assignments"][task["task_name"]]["column_mapping"]

        client.post(f"/experiment/sessions/{sid}/results", json={
            "task_name": task["task_name"],
            "question_key": "question1",
            "query": "dual q",
            "results_left": [
                {"issue_id": "DL-1", "rating": 5},
                {"issue_id": "DL-2", "rating": 3},
            ],
            "results_right": [
                {"issue_id": "DR-1", "rating": 4},
                {"issue_id": "DR-2", "rating": 2},
            ],
        })

        s = client.get(f"/experiment/sessions/{sid}").json()
        assert len(s["searches"]) == 1
        assert mapping["left"] != mapping["right"]

    @patch("app.routers.experiment._create_backup", lambda path: None)
    def test_legacy_full_flow(self):
        """Legacy: get tasks → submit ratings → verify persisted."""
        backup = _backup_experiment_data()
        try:
            _write_test_experiment_data()

            # get tasks
            tasks = client.post(
                "/experiment/tasks", json={"MtrNo": "test_e2e_001"}
            ).json()
            assert len(tasks) == 3

            # submit ratings for first task
            resp = client.post("/experiment/submit-ratings", json={
                "matriculationNumber": "test_e2e_001",
                "taskId": "Component DataNode",
                "questionKey": "question1",
                "searchQuery": "full flow query 1",
                "ratings": [
                    {"issue_id": "FF-1", "rating": 5},
                    {"issue_id": "FF-2", "rating": 4},
                ],
            })
            assert resp.status_code == 200

            # submit second search for same question
            client.post("/experiment/submit-ratings", json={
                "matriculationNumber": "test_e2e_001",
                "taskId": "Component DataNode",
                "questionKey": "question1",
                "searchQuery": "full flow query 2",
                "ratings": [{"issue_id": "FF-3", "rating": 3}],
            })

            # verify
            tasks = client.post(
                "/experiment/tasks", json={"MtrNo": "test_e2e_001"}
            ).json()
            dn = next(t for t in tasks if t["taskName"] == "Component DataNode")
            assert len(dn["solutions"]["question1"]) == 2
            assert dn["solutions"]["question1"][0]["searchQuery"] == "full flow query 1"
            assert dn["solutions"]["question1"][1]["searchQuery"] == "full flow query 2"
        finally:
            _restore_experiment_data(backup)
