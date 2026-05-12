#!/usr/bin/env python3
"""Audit project experiment query fixtures against live PyLucene and archRag.

This script is intended for sanity-checking per-project mock experiment configs.
It loads each project's `experiment_queries.json`, executes every question against
both backends, and reports weak tasks whose result counts fall below a threshold.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = "https://maestro.localhost:4269"
VERIFY_SSL = False
DEFAULT_PROJECTS = ["LUCENE", "TIKA", "JCLOUDS", "MAPREDUCE", "YARN"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=BASE,
        help="Base Maestro URL.",
    )
    parser.add_argument(
        "--project",
        action="append",
        dest="projects",
        help="Project to audit. Repeat to audit multiple. Defaults to all non-HDFS projects.",
    )
    parser.add_argument(
        "--min-results",
        type=int,
        default=3,
        help="Flag a backend/question as weak when it returns fewer results than this.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Per-request timeout in seconds.",
    )
    return parser.parse_args()


def request_json(method: str, url: str, timeout: int, **kwargs) -> tuple[int, dict[str, Any] | None]:
    response = requests.request(method, url, verify=VERIFY_SSL, timeout=timeout, **kwargs)
    try:
        payload = response.json()
    except Exception:
        payload = None
    return response.status_code, payload


def payload_count(payload: dict[str, Any] | None) -> int:
    if not payload or payload.get("result") != "done":
        return 0
    return len(payload.get("payload", []))


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    search_engine_url = f"{base_url}/search-engine/search"
    archrag_url = f"{base_url}/archrag/search"

    root = Path(__file__).resolve().parent / "issues-db-api" / "app" / "experiment_configs" / "Apache"
    projects = args.projects or DEFAULT_PROJECTS

    overall = []
    weak = []

    for project in projects:
        path = root / project / "experiment_queries.json"
        with path.open() as handle:
            tasks = json.load(handle)["tasks"]

        project_rows = []
        for task_name, task in tasks.items():
            task_summary = {
                "project": project,
                "task_name": task_name,
                "questions": [],
            }
            for question_key, question in task["questions"].items():
                py_status, py_payload = request_json(
                    "POST",
                    search_engine_url,
                    timeout=args.timeout,
                    json=question["pylucene_request"],
                )
                rerank_status, rerank_payload = request_json(
                    "POST",
                    search_engine_url,
                    timeout=args.timeout,
                    json=question["pylucene_rerank_request"],
                )
                ar_status, ar_payload = request_json(
                    "POST",
                    archrag_url,
                    timeout=args.timeout,
                    json=question["archrag_request"],
                )

                row = {
                    "question_key": question_key,
                    "query": question["query"],
                    "pylucene_status": py_status,
                    "pylucene_count": payload_count(py_payload),
                    "pylucene_rerank_status": rerank_status,
                    "pylucene_rerank_count": payload_count(rerank_payload),
                    "archrag_status": ar_status,
                    "archrag_count": payload_count(ar_payload),
                }
                task_summary["questions"].append(row)

                if (
                    py_status != 200
                    or rerank_status != 200
                    or ar_status != 200
                    or row["pylucene_count"] < args.min_results
                    or row["pylucene_rerank_count"] < args.min_results
                    or row["archrag_count"] < args.min_results
                ):
                    weak.append({
                        "project": project,
                        "task_name": task_name,
                        **row,
                    })

            project_rows.append(task_summary)

        overall.append({"project": project, "tasks": project_rows})

    for project_entry in overall:
        project = project_entry["project"]
        print(f"\n[{project}]")
        for task in project_entry["tasks"]:
            counts = [
                (
                    q["pylucene_count"],
                    q["pylucene_rerank_count"],
                    q["archrag_count"],
                )
                for q in task["questions"]
            ]
            min_py = min(item[0] for item in counts)
            min_rerank = min(item[1] for item in counts)
            min_ar = min(item[2] for item in counts)
            print(
                f"  {task['task_name']}: min counts"
                f" py={min_py} rerank={min_rerank} rag={min_ar}"
            )

    print("\nWeak questions:")
    if not weak:
        print("  none")
        return 0

    for row in weak:
        print(
            "  "
            f"{row['project']} | {row['task_name']} | {row['question_key']} | "
            f"py={row['pylucene_status']}:{row['pylucene_count']} | "
            f"rerank={row['pylucene_rerank_status']}:{row['pylucene_rerank_count']} | "
            f"rag={row['archrag_status']}:{row['archrag_count']}"
        )

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
