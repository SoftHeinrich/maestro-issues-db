#!/usr/bin/env python3
"""
Demo: 23 students get different search configurations (Latin-square design).

Uses experiment_data.json where each student (by ID) is assigned tasks with
different search engine settings:
  - rerank_engine: true/false  (PyLucene ADD prediction reranking)
  - gpt: true/false            (GPT-4o keyword extraction before search)

Each search result is prefixed with the pipeline setting that produced it,
so the audience can see at a glance which engine configuration is active.

Run:  python demo_multi_user_search.py
Requires: MongoDB running on localhost:27017
"""

import json
import random
from app.app import app
from app.routers.experiment import get_experiment_tasks, MtrNo
from fastapi.testclient import TestClient

client = TestClient(app)

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RED = "\033[91m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
WHITE = "\033[97m"

COLORS = ["\033[94m", "\033[92m", "\033[93m", "\033[96m", "\033[95m",
          "\033[91m", "\033[34m", "\033[32m", "\033[33m", "\033[36m"]

# Mock issue data for demo — real issues from HDFS
MOCK_ISSUES = [
    {"id": "Apache-13261900", "key": "HDFS-14890", "summary": "DataNode block scanner improvements"},
    {"id": "Apache-12761510", "key": "HDFS-9806",  "summary": "NameNode HA failover controller redesign"},
    {"id": "Apache-13368292", "key": "HDFS-15234", "summary": "Block placement policy for rack awareness"},
    {"id": "Apache-12391937", "key": "HDFS-8201",  "summary": "DiskBalancer architecture and design decisions"},
    {"id": "Apache-13086530", "key": "HDFS-13561", "summary": "HDFS encryption zone design"},
    {"id": "Apache-12391510", "key": "HDFS-8195",  "summary": "NameNode federation namespace management"},
    {"id": "Apache-12760922", "key": "HDFS-9800",  "summary": "DataNode lifecycle and heartbeat protocol"},
    {"id": "Apache-12765758", "key": "HDFS-9850",  "summary": "Safe mode entry and exit conditions"},
    {"id": "Apache-12651593", "key": "HDFS-9100",  "summary": "Journal node quorum protocol"},
    {"id": "Apache-12731411", "key": "HDFS-9600",  "summary": "Block recovery and replication strategy"},
]


def banner(text):
    w = 76
    print(f"\n{BOLD}{'=' * w}")
    print(f"  {text}")
    print(f"{'=' * w}{RESET}\n")


def step(num, text):
    print(f"{BOLD}{CYAN}[Step {num}]{RESET} {text}")


def pipeline_tag(rerank, gpt):
    """Return a colored prefix tag for the search engine setting."""
    if gpt and rerank:
        return f"{BOLD}{MAGENTA}[GPT+RERANK]{RESET}"
    elif gpt:
        return f"{BOLD}{YELLOW}[GPT]{RESET}"
    elif rerank:
        return f"{BOLD}{BLUE}[RERANK]{RESET}"
    else:
        return f"{BOLD}{WHITE}[RAW]{RESET}"


def pipeline_name(rerank, gpt):
    if gpt and rerank:
        return "GPT keywords -> PyLucene + Reranking"
    elif gpt:
        return "GPT keywords -> PyLucene (no rerank)"
    elif rerank:
        return "Raw query  -> PyLucene + Reranking"
    else:
        return "Raw query  -> PyLucene (no rerank)"


def print_table(headers, rows, max_rows=None):
    display = rows[:max_rows] if max_rows else rows
    widths = [len(h) for h in headers]
    for row in display:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(f"  {DIM}{fmt.format(*headers)}{RESET}")
    print(f"  {DIM}{'-' * sum(widths + [2 * (len(widths)-1)])}{RESET}")
    for i, row in enumerate(display):
        color = COLORS[i % len(COLORS)]
        print(f"  {color}{fmt.format(*[str(c) for c in row])}{RESET}")
    if max_rows and len(rows) > max_rows:
        print(f"  {DIM}... and {len(rows) - max_rows} more assignments{RESET}")


def generate_mock_results(rerank, gpt, seed=42):
    """Generate mock search results with different ordering/scores per pipeline."""
    rng = random.Random(seed)
    results = list(MOCK_ISSUES)

    if gpt:
        # GPT keyword extraction changes which issues match -> shuffle more
        rng.shuffle(results)
        base_score = 8.5
    else:
        base_score = 7.0

    if rerank:
        # Reranking changes order within same result set
        results = sorted(results, key=lambda x: rng.random())
        score_boost = 1.5
    else:
        score_boost = 0.0

    scored = []
    for i, issue in enumerate(results):
        score = round(base_score + score_boost - i * 0.3 + rng.uniform(-0.2, 0.2), 2)
        scored.append({**issue, "score": max(score, 0.5)})

    return scored


def main():
    banner("DEMO: Per-User Differentiated Search (23 Students, 12 Tasks)")

    # ── Step 1: Load experiment data and show overview ──
    step(1, "Loading experiment_data.json — 23 students, Latin-square design\n")

    with open("app/experiment_data.json") as f:
        exp_data = json.load(f)

    students = exp_data["student_data"]
    task_defs = exp_data["task_details"]
    user_ids = sorted(students.keys())

    print(f"  {BOLD}{len(user_ids)} students{RESET}: {', '.join(user_ids[:8])}, ...")
    print(f"  {BOLD}{len(task_defs)} tasks{RESET}: {', '.join(list(task_defs.keys())[:4])}, ...")
    print(f"  {BOLD}4 pipeline combinations{RESET}:")
    print(f"    {pipeline_tag(False, False)} Raw query  -> PyLucene (no rerank)")
    print(f"    {pipeline_tag(True, False)}   Raw query  -> PyLucene + Reranking")
    print(f"    {pipeline_tag(False, True)}       GPT keywords -> PyLucene (no rerank)")
    print(f"    {pipeline_tag(True, True)} GPT keywords -> PyLucene + Reranking\n")

    rows = []
    for uid in user_ids:
        for task in students[uid]["tasks"]:
            rerank = task.get("rerank_engine", False)
            gpt = task.get("gpt", False)
            rows.append([uid, task["taskName"][:30], str(rerank), str(gpt), pipeline_name(rerank, gpt)])

    print_table(["Student", "Task", "Rerank", "GPT", "Search Pipeline"], rows, max_rows=20)
    print()

    # ── Step 2: Call POST /experiment/tasks for each student ──
    step(2, "Live API: POST /experiment/tasks — verifying all 23 students\n")

    pipeline_counts = {"[RAW]": 0, "[RERANK]": 0, "[GPT]": 0, "[GPT+RERANK]": 0}
    for i, uid in enumerate(user_ids):
        color = COLORS[i % len(COLORS)]
        resp = client.post("/experiment/tasks", json={"MtrNo": uid})
        assert resp.status_code == 200, f"Failed for {uid}: {resp.text}"
        data = resp.json()
        task_summary = []
        for task in data:
            rerank = task.get("rerank_engine", False)
            gpt = task.get("gpt", False)
            tag = pipeline_tag(rerank, gpt)
            task_summary.append(f"{tag} {task['taskName'][:25]}")
            # Count pipelines
            if gpt and rerank: pipeline_counts["[GPT+RERANK]"] += 1
            elif gpt: pipeline_counts["[GPT]"] += 1
            elif rerank: pipeline_counts["[RERANK]"] += 1
            else: pipeline_counts["[RAW]"] += 1
        print(f"  {color}{uid}{RESET}: {len(data)} tasks — {', '.join(task_summary)}")

    print(f"\n  {BOLD}Pipeline distribution:{RESET}")
    for tag, count in pipeline_counts.items():
        print(f"    {tag}: {count} task assignments")

    # Verify unknown user gets 404
    resp = client.post("/experiment/tasks", json={"MtrNo": "unknown"})
    print(f"\n  {RED}unknown{RESET}: {resp.status_code} — {resp.json()['detail']}")
    print()

    # ── Step 3: Mock search results with pipeline prefixes ──
    step(3, "Mock search: same query, different results per pipeline\n")

    query = "data replication strategy"
    print(f"  Query: {BOLD}\"{query}\"{RESET}\n")

    # Pick 4 students with different pipeline configs for first task
    demo_students = []
    seen_combos = set()
    for uid in user_ids:
        task = students[uid]["tasks"][0]
        combo = (task["rerank_engine"], task["gpt"])
        if combo not in seen_combos:
            seen_combos.add(combo)
            demo_students.append(uid)
        if len(demo_students) == 4:
            break

    for uid in demo_students:
        task = students[uid]["tasks"][0]
        rerank = task.get("rerank_engine", False)
        gpt = task.get("gpt", False)
        tag = pipeline_tag(rerank, gpt)

        # Generate mock results unique to this pipeline combination
        seed = hash((rerank, gpt, query)) % 10000
        results = generate_mock_results(rerank, gpt, seed)

        print(f"  {BOLD}Student {uid}{RESET} — {task['taskName']}")
        print(f"  Pipeline: {tag} {pipeline_name(rerank, gpt)}")
        print(f"  {DIM}{'─' * 60}{RESET}")

        for i, r in enumerate(results[:5]):
            print(f"    {tag} {BOLD}#{i+1}{RESET} [{r['score']:.2f}] {r['key']}: {r['summary']}")
        print()

    # ── Step 4: Side-by-side comparison of two contrasting students ──
    step(4, "Side-by-side: RAW vs GPT+RERANK for same query\n")

    # Find one RAW and one GPT+RERANK student
    raw_student = None
    full_student = None
    for uid in user_ids:
        task = students[uid]["tasks"][0]
        if not task["rerank_engine"] and not task["gpt"] and not raw_student:
            raw_student = uid
        if task["rerank_engine"] and task["gpt"] and not full_student:
            full_student = uid
        if raw_student and full_student:
            break

    for uid, label in [(raw_student, "Student A"), (full_student, "Student B")]:
        task = students[uid]["tasks"][0]
        rerank = task.get("rerank_engine", False)
        gpt = task.get("gpt", False)
        tag = pipeline_tag(rerank, gpt)
        q1 = list(task.get("questions", {}).values())[0] if task.get("questions") else {}
        dd = q1.get("design_decision", {})

        if rerank:
            preds = {k: dd.get(k) for k in ["existence", "executive", "property"]}
        else:
            preds = {"existence": None, "executive": None, "property": None}

        payload = {
            "database_url": "https://maestro.localhost:4269/issues-db-api",
            "model_id": "648ee4526b3fde4b1b33e099",
            "version_id": "648f1f6f6b3fde4b1b3429cf",
            "repos_and_projects": {"Apache": ["HDFS"]},
            "query": "<GPT-4o extracted keywords>" if gpt else query,
            "num_results": 10,
            "predictions": preds,
        }

        print(f"  {BOLD}{label}: {uid}{RESET} — {task['taskName']}")
        print(f"  Pipeline: {tag}")
        print(f"  {DIM}POST /pylucene/search{RESET}")
        for line in json.dumps(payload, indent=4).split("\n"):
            print(f"    {line}")

        # Show mock results with prefix
        seed = hash((rerank, gpt, query)) % 10000
        results = generate_mock_results(rerank, gpt, seed)
        print(f"\n  {BOLD}Results:{RESET}")
        for i, r in enumerate(results[:5]):
            print(f"    {tag} #{i+1} [{r['score']:.2f}] {r['key']}: {r['summary']}")
        print()

    # ── Step 5: Show actual solution data from experiment ──
    step(5, "Real evaluation data: students' actual search queries & ratings\n")

    solutions_shown = 0
    for uid in user_ids[:5]:
        for task in students[uid]["tasks"][:1]:
            rerank = task.get("rerank_engine", False)
            gpt = task.get("gpt", False)
            tag = pipeline_tag(rerank, gpt)
            solutions = task.get("solutions", {})
            if not solutions:
                continue

            print(f"  {BOLD}{uid}{RESET} — {task['taskName']} {tag}")
            for qkey, searches in solutions.items():
                for search in searches[:1]:
                    q = search.get("searchQuery", "")[:60]
                    ratings = search.get("ratings", [])
                    avg_rating = sum(int(r["rating"]) for r in ratings) / len(ratings) if ratings else 0
                    print(f"    {tag} Query: \"{q}\"")
                    print(f"    {tag} {len(ratings)} results rated, avg={avg_rating:.1f}")
                    for r in ratings[:3]:
                        stars = "★" * int(r["rating"]) + "☆" * (5 - int(r["rating"]))
                        print(f"      {tag} {r['issue_id']}: {stars} ({r['rating']}/5)")
                    if len(ratings) > 3:
                        print(f"      {DIM}... and {len(ratings) - 3} more{RESET}")
            print()
            solutions_shown += 1
    print(f"  {DIM}Showing {solutions_shown} of {len(user_ids)} students with solution data{RESET}\n")

    # ── Step 6: Explain the difference ──
    step(6, "Why results differ per user\n")

    print(f"""  {YELLOW}Two mechanisms create different results per user:{RESET}

  1. {BOLD}GPT keyword extraction{RESET} ({pipeline_tag(False, True)} / {pipeline_tag(True, True)})
     User types: "data replication strategy"
     GPT-4o extracts: "replication factor replica placement datanode"
     -> {GREEN}Different query text = different search results{RESET}

  2. {BOLD}Prediction reranking{RESET} ({pipeline_tag(True, False)} / {pipeline_tag(True, True)})
     PyLucene results are re-scored using DL model confidence
     for the question's ADD type (existence/property/executive)
     -> {GREEN}Same results but different ordering{RESET}

  Combined ({pipeline_tag(True, True)}): user gets BOTH effects.
  Baseline ({pipeline_tag(False, False)}): raw query, no reranking.

  {BOLD}Latin-square design:{RESET} Each student gets 4 tasks, one per pipeline,
  ensuring balanced coverage across all 12 tasks and 4 pipelines.
""")

    # ── How to run ──
    banner("HOW TO SHOW THIS DEMO")

    print(f"""  {BOLD}Option A: This terminal demo{RESET}
    cd maestro-issues-db && docker compose up -d mongo
    cd issues-db-api
    python demo_multi_user_search.py

  {BOLD}Option B: Live web UI demo{RESET}
    # 1. Start all services
    cd Maestro && ./setup_components.sh

    # 2. Open browser: https://maestro.localhost:4269/archui/experiment

    # 3. Enter student ID "{demo_students[0]}"
    #    -> Pipeline: {pipeline_tag(
            students[demo_students[0]]['tasks'][0]['rerank_engine'],
            students[demo_students[0]]['tasks'][0]['gpt'])}
    #    Search "data replication" -> observe results

    # 4. Open incognito, enter "{demo_students[1]}"
    #    -> Pipeline: {pipeline_tag(
            students[demo_students[1]]['tasks'][0]['rerank_engine'],
            students[demo_students[1]]['tasks'][0]['gpt'])}
    #    Search "data replication" -> different results!

    # 5. Compare side by side — each result prefixed with pipeline tag

  {BOLD}Key points for presentation:{RESET}
    - 23 students, 12 tasks, 4 pipeline combinations (Latin-square)
    - Same search engine, same database, same query
    - Each student ID maps to different search pipeline settings
    - Settings stored in experiment_data.json (easily configurable)
    - Frontend reads config via POST /experiment/tasks
    - Frontend sends different parameters to PyLucene accordingly
    - Users are blind to which pipeline they're using
    - Each search result prefixed with pipeline tag: {pipeline_tag(False, False)} {pipeline_tag(True, False)} {pipeline_tag(False, True)} {pipeline_tag(True, True)}
""")


if __name__ == "__main__":
    main()
