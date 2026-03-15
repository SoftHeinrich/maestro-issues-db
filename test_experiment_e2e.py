"""
End-to-end test for the experiment system.

Tests the full flow: fetch tasks → search (PyLucene + archRag) → submit ratings.
Uses the cleaned experiment_data.json generated from toolkit data13 results.

Run: python3 test_experiment_e2e.py
Requires: All Maestro services running (issues-db-api, pylucene, archrag)
"""

import json
import sys
import time
import requests

BASE = "https://maestro.localhost:4269"
API = f"{BASE}/issues-db-api"
SEARCH_ENGINE = f"{BASE}/search-engine"
ARCHRAG = f"{BASE}/archrag"
VERIFY_SSL = False

# Suppress InsecureRequestWarning
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
        msg = f"  ✗ {name}: {detail}"
        print(msg)
        errors.append(msg)


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ---------------------------------------------------------------
# 1. Service health checks
# ---------------------------------------------------------------
section("1. Service Health Checks")

r = requests.get(f"{API}/models", verify=VERIFY_SSL)
check("Issues DB API reachable", r.status_code == 200, f"status={r.status_code}")

r = requests.get(f"{SEARCH_ENGINE}/index-status", verify=VERIFY_SSL)
check("PyLucene reachable via Traefik", r.status_code == 200, f"status={r.status_code}")

r = requests.get(f"{ARCHRAG}/health", verify=VERIFY_SSL)
check("archRag reachable via Traefik", r.status_code == 200, f"status={r.status_code}")
data = r.json()
check("archRag store loaded", data.get("store_loaded") is True, str(data))

r = requests.get(f"{API}/models/648ee4526b3fde4b1b33e099/versions", verify=VERIFY_SSL)
check("BERT model exists", r.status_code == 200, f"status={r.status_code}")

# ---------------------------------------------------------------
# 2. Load experiment data and validate structure
# ---------------------------------------------------------------
section("2. Experiment Data Validation")

with open("issues-db-api/app/experiment_data.json") as f:
    exp_data = json.load(f)

students = exp_data.get("student_data", {})
task_defs = exp_data.get("task_details", {})
check("experiment_data.json has student_data", len(students) > 0, f"count={len(students)}")
check("experiment_data.json has task_details", len(task_defs) > 0, f"count={len(task_defs)}")

# Validate all task names referenced by students exist in task_details
all_task_names = set()
for sid, student in students.items():
    for task in student["tasks"]:
        all_task_names.add(task["taskName"])

missing_tasks = all_task_names - set(task_defs.keys())
check("All student tasks have definitions", len(missing_tasks) == 0,
      f"missing: {missing_tasks}")

# Validate all tasks have empty solutions (clean state)
all_clean = all(
    all(len(t.get("solutions", {})) == 0 for t in s["tasks"])
    for s in students.values()
)
check("All solutions are empty (clean experiment)", all_clean)

# Validate each task_detail has questions
for tname, tdef in task_defs.items():
    qs = tdef.get("questions", {})
    check(f"Task '{tname}' has questions", len(qs) > 0, f"count={len(qs)}")

# ---------------------------------------------------------------
# 3. Fetch tasks for a student (legacy endpoint)
# ---------------------------------------------------------------
section("3. Fetch Tasks for Student")

test_student = list(students.keys())[0]
r = requests.post(f"{API}/experiment/tasks",
                   json={"MtrNo": test_student}, verify=VERIFY_SSL)
check(f"GET tasks for '{test_student}'", r.status_code == 200, f"status={r.status_code}")

tasks = r.json()
check("Response is a list of tasks", isinstance(tasks, list) and len(tasks) > 0,
      f"type={type(tasks)}, len={len(tasks) if isinstance(tasks, list) else 'N/A'}")

# Validate task structure
task = tasks[0]
check("Task has 'taskName'", "taskName" in task)
check("Task has 'engine'", "engine" in task)
check("Task has 'description'", "description" in task and task["description"])
check("Task has 'questions'", "questions" in task and len(task["questions"]) > 0)
check("Task has 'lekert_scale'", "lekert_scale" in task and task["lekert_scale"])
check("Task has 'solutions' (empty)", "solutions" in task and len(task["solutions"]) == 0)

# Validate engine values
engines_used = set(t["engine"] for t in tasks if "engine" in t)
check("Engines are valid", engines_used <= {"pylucene", "archrag"},
      f"engines={engines_used}")

# Test non-existent student
r = requests.post(f"{API}/experiment/tasks",
                   json={"MtrNo": "nonexistent999"}, verify=VERIFY_SSL)
check("404 for unknown student", r.status_code == 404)

# ---------------------------------------------------------------
# 4. PyLucene search (as experiment would)
# ---------------------------------------------------------------
section("4. PyLucene Search")

# Find a pylucene task
pylucene_task = None
pylucene_student = None
for sid, student in students.items():
    for t in student["tasks"]:
        if t.get("engine") == "pylucene" or "engine" not in t:
            pylucene_student = sid
            pylucene_task = t
            break
    if pylucene_task:
        break

if pylucene_task:
    task_name = pylucene_task["taskName"]
    task_def = task_defs[task_name]
    first_q = list(task_def["questions"].keys())[0]
    question = task_def["questions"][first_q]

    # Build predictions from design_decision
    dd = question.get("design_decision", {})
    rerank = pylucene_task.get("rerank_engine", False)
    predictions = {
        "existence": dd.get("existence") if rerank else None,
        "executive": dd.get("executive") if rerank else None,
        "property": dd.get("property") if rerank else None,
    }

    search_body = {
        "database_url": "http://issues-db-api:8000",
        "model_id": "648ee4526b3fde4b1b33e099",
        "version_id": "648f1f6f6b3fde4b1b3429cf",
        "repos_and_projects": {"Apache": ["HDFS"]},
        "query": "DataNode components architecture",
        "num_results": 10,
        "predictions": predictions,
    }

    r = requests.post(f"{SEARCH_ENGINE}/search", json=search_body, verify=VERIFY_SSL)
    check("PyLucene search succeeds", r.status_code == 200, f"status={r.status_code}")

    data = r.json()
    check("PyLucene result is 'done'", data.get("result") == "done", data.get("result"))

    results = data.get("payload", [])
    check("PyLucene returns results", len(results) > 0, f"count={len(results)}")

    if results:
        r0 = results[0]
        check("Result has issue_key", "issue_key" in r0, str(r0.keys()))
        check("Result has issue_id", "issue_id" in r0)
        check("Result has summary", "summary" in r0)
        check("Result has description", "description" in r0)
        check("Result has comments (list)", isinstance(r0.get("comments"), list))

        # Check comments format if present
        has_comments = any(len(r.get("comments", [])) > 0 for r in results)
        if has_comments:
            for r in results:
                if r.get("comments"):
                    c = r["comments"][0]
                    check("Comment is a tuple/list of 5+ fields",
                          isinstance(c, list) and len(c) >= 5,
                          f"type={type(c)}, len={len(c) if isinstance(c, list) else 'N/A'}")
                    break
    pylucene_results = results
else:
    print("  (!) No pylucene task found, skipping")
    pylucene_results = []

# ---------------------------------------------------------------
# 5. archRag search (as experiment would)
# ---------------------------------------------------------------
section("5. archRag Search")

archrag_task = None
archrag_student = None
for sid, student in students.items():
    for t in student["tasks"]:
        if t.get("engine") == "archrag":
            archrag_student = sid
            archrag_task = t
            break
    if archrag_task:
        break

if archrag_task:
    search_body = {
        "query": "NameNode components architecture",
        "num_results": 10,
    }

    r = requests.post(f"{ARCHRAG}/search", json=search_body, verify=VERIFY_SSL)
    check("archRag search succeeds", r.status_code == 200, f"status={r.status_code}")

    data = r.json()
    check("archRag result is 'done'", data.get("result") == "done", data.get("result"))

    results = data.get("payload", [])
    check("archRag returns results", len(results) > 0, f"count={len(results)}")

    if results:
        r0 = results[0]
        check("Result has issue_key", "issue_key" in r0)
        check("Result has summary", "summary" in r0)
        check("Result has description", "description" in r0)
        check("Result has comments (list)", isinstance(r0.get("comments"), list))
        check("Result has snippets", isinstance(r0.get("snippets"), list))

        # Check comments format matches PyLucene
        has_comments = any(len(r.get("comments", [])) > 0 for r in results)
        if has_comments:
            for r in results:
                if r.get("comments"):
                    c = r["comments"][0]
                    check("archRag comment format matches PyLucene (list of 5+ fields)",
                          isinstance(c, list) and len(c) >= 5,
                          f"type={type(c)}, len={len(c) if isinstance(c, list) else 'N/A'}")
                    break
        else:
            print("  (i) No comments in top results (some issues have none)")

    archrag_results = results
else:
    print("  (!) No archrag task found, skipping")
    archrag_results = []

# ---------------------------------------------------------------
# 6. GPT-4 keyword extraction
# ---------------------------------------------------------------
section("6. GPT-4 Keyword Extraction")

# Find a GPT task
gpt_task = None
for sid, student in students.items():
    for t in student["tasks"]:
        if t.get("gpt"):
            gpt_task = t
            break
    if gpt_task:
        break

if gpt_task:
    r = requests.post(f"{API}/experiment/gpt4-response",
                      json={"prompt": "What components handle data replication in HDFS?"},
                      verify=VERIFY_SSL)
    check("GPT-4 endpoint responds", r.status_code == 200, f"status={r.status_code}")

    data = r.json()
    has_answer = "answer" in data
    check("GPT-4 returns keywords", has_answer, str(data)[:200])

    if has_answer:
        keywords = data["answer"].split()
        check("GPT-4 returns 5-10 keywords", 5 <= len(keywords) <= 10,
              f"got {len(keywords)}: {data['answer']}")
else:
    print("  (i) No GPT task found in experiment data")

# ---------------------------------------------------------------
# 7. Submit ratings (PyLucene task)
# ---------------------------------------------------------------
section("7. Submit Ratings - PyLucene")

if pylucene_results and pylucene_student and pylucene_task:
    task_name = pylucene_task["taskName"]
    task_def = task_defs[task_name]
    first_q = list(task_def["questions"].keys())[0]

    # Create ratings for all results
    ratings = [
        {"issue_id": r["issue_id"], "rating": str(3)}
        for r in pylucene_results[:10]
        if r.get("issue_id")
    ]

    submit_body = {
        "matriculationNumber": pylucene_student,
        "taskId": task_name,
        "questionKey": first_q,
        "searchQuery": "DataNode components architecture",
        "ratings": ratings,
    }

    r = requests.post(f"{API}/experiment/submit-ratings",
                      json=submit_body, verify=VERIFY_SSL)
    check("Submit PyLucene ratings succeeds", r.status_code == 200,
          f"status={r.status_code}, body={r.text[:200]}")

    data = r.json()
    check("Response confirms success", "success" in data or data.get("success"),
          str(data))

    # Verify ratings were saved
    r = requests.post(f"{API}/experiment/tasks",
                      json={"MtrNo": pylucene_student}, verify=VERIFY_SSL)
    tasks_after = r.json()
    saved_task = next((t for t in tasks_after if t["taskName"] == task_name), None)
    check("Task found after submission", saved_task is not None)

    if saved_task:
        solutions = saved_task.get("solutions", {})
        check("Solutions populated for question",
              first_q in solutions and len(solutions[first_q]) > 0,
              f"solutions keys: {list(solutions.keys())}")

        if first_q in solutions and solutions[first_q]:
            sol = solutions[first_q][0]
            check("Solution has searchQuery", sol.get("searchQuery") == "DataNode components architecture")
            check("Solution has ratings", len(sol.get("ratings", [])) > 0)
            check("Solution has engine", "engine" in sol)
else:
    print("  (!) Skipped - no pylucene results available")

# ---------------------------------------------------------------
# 8. Submit ratings - archRag task
# ---------------------------------------------------------------
section("8. Submit Ratings - archRag")

if archrag_results and archrag_student and archrag_task:
    task_name = archrag_task["taskName"]
    task_def = task_defs[task_name]
    first_q = list(task_def["questions"].keys())[0]

    ratings = [
        {"issue_id": r["issue_id"], "rating": str(4)}
        for r in archrag_results[:10]
        if r.get("issue_id")
    ]

    submit_body = {
        "matriculationNumber": archrag_student,
        "taskId": task_name,
        "questionKey": first_q,
        "searchQuery": "NameNode components architecture",
        "ratings": ratings,
    }

    r = requests.post(f"{API}/experiment/submit-ratings",
                      json=submit_body, verify=VERIFY_SSL)
    check("Submit archRag ratings succeeds", r.status_code == 200,
          f"status={r.status_code}, body={r.text[:200]}")

    # Verify
    r = requests.post(f"{API}/experiment/tasks",
                      json={"MtrNo": archrag_student}, verify=VERIFY_SSL)
    tasks_after = r.json()
    saved_task = next((t for t in tasks_after if t["taskName"] == task_name), None)
    if saved_task:
        solutions = saved_task.get("solutions", {})
        check("archRag ratings saved",
              first_q in solutions and len(solutions[first_q]) > 0)
else:
    print("  (!) Skipped - no archrag results available")

# ---------------------------------------------------------------
# 9. Submit second attempt (experiment requires ≥2 queries)
# ---------------------------------------------------------------
section("9. Second Search Attempt")

if pylucene_results and pylucene_student and pylucene_task:
    task_name = pylucene_task["taskName"]
    task_def = task_defs[task_name]
    first_q = list(task_def["questions"].keys())[0]

    # Search with different query
    dd = task_def["questions"][first_q].get("design_decision", {})
    rerank = pylucene_task.get("rerank_engine", False)
    search_body = {
        "database_url": "http://issues-db-api:8000",
        "model_id": "648ee4526b3fde4b1b33e099",
        "version_id": "648f1f6f6b3fde4b1b3429cf",
        "repos_and_projects": {"Apache": ["HDFS"]},
        "query": "DataNode design decisions rationale",
        "num_results": 10,
        "predictions": {
            "existence": dd.get("existence") if rerank else None,
            "executive": dd.get("executive") if rerank else None,
            "property": dd.get("property") if rerank else None,
        },
    }

    r = requests.post(f"{SEARCH_ENGINE}/search", json=search_body, verify=VERIFY_SSL)
    check("Second search succeeds", r.status_code == 200)

    results2 = r.json().get("payload", [])
    ratings2 = [
        {"issue_id": r["issue_id"], "rating": str(2)}
        for r in results2[:10]
        if r.get("issue_id")
    ]

    submit_body = {
        "matriculationNumber": pylucene_student,
        "taskId": task_name,
        "questionKey": first_q,
        "searchQuery": "DataNode design decisions rationale",
        "ratings": ratings2,
    }

    r = requests.post(f"{API}/experiment/submit-ratings",
                      json=submit_body, verify=VERIFY_SSL)
    check("Submit second attempt ratings", r.status_code == 200)

    # Verify 2 solutions now
    r = requests.post(f"{API}/experiment/tasks",
                      json={"MtrNo": pylucene_student}, verify=VERIFY_SSL)
    tasks_after = r.json()
    saved_task = next((t for t in tasks_after if t["taskName"] == task_name), None)
    if saved_task:
        solutions = saved_task.get("solutions", {}).get(first_q, [])
        check("Two attempts saved for question", len(solutions) == 2,
              f"count={len(solutions)}")

# ---------------------------------------------------------------
# 10. Logging endpoint
# ---------------------------------------------------------------
section("10. Logging")

r = requests.post(f"{API}/experiment/logs",
                  json={
                      "level": "info",
                      "message": "E2E test log entry",
                      "timestamp": "2026-03-14T12:00:00Z",
                  }, verify=VERIFY_SSL)
check("Log endpoint works", r.status_code == 200, f"status={r.status_code}")

# ---------------------------------------------------------------
# 11. Cross-student isolation
# ---------------------------------------------------------------
section("11. Cross-Student Isolation")

student2 = list(students.keys())[1]
r = requests.post(f"{API}/experiment/tasks",
                  json={"MtrNo": student2}, verify=VERIFY_SSL)
check(f"Fetch tasks for different student '{student2}'", r.status_code == 200)

tasks2 = r.json()
all_empty = all(
    len(t.get("solutions", {})) == 0
    for t in tasks2
)
check("Other student's solutions are still empty", all_empty)

# ---------------------------------------------------------------
# 12. Cleanup - restore clean experiment data
# ---------------------------------------------------------------
section("12. Cleanup")

# Reload original clean data and restore
with open("issues-db-api/app/experiment_data.json") as f:
    current = json.load(f)

for sid, student in current["student_data"].items():
    for task in student["tasks"]:
        task["solutions"] = {}

with open("issues-db-api/app/experiment_data.json", "w") as f:
    json.dump(current, f, indent=4)

# Verify cleanup
r = requests.post(f"{API}/experiment/tasks",
                  json={"MtrNo": test_student}, verify=VERIFY_SSL)
tasks_clean = r.json()
all_clean_after = all(len(t.get("solutions", {})) == 0 for t in tasks_clean)
check("Experiment data cleaned up", all_clean_after)

# ---------------------------------------------------------------
# Summary
# ---------------------------------------------------------------
print(f"\n{'='*60}")
print(f"  RESULTS: {passed} passed, {failed} failed")
print(f"{'='*60}")

if errors:
    print("\nFailed tests:")
    for e in errors:
        print(e)

sys.exit(0 if failed == 0 else 1)
