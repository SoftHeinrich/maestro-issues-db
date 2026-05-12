#!/usr/bin/env python3
"""Drive project-scoped comment classification jobs through dl-manager."""

from __future__ import annotations

import argparse
import json
from typing import Iterable

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_PROJECTS = ["TIKA", "MAPREDUCE", "YARN"]
MODEL_ID = "648ee4526b3fde4b1b33e099"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://maestro.localhost:4269")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument(
        "--project",
        action="append",
        dest="projects",
        help="Project key to classify. Repeat to run multiple projects.",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--database-url",
        default="http://issues-db-api:8000",
        help="Internal issues-db-api URL visible from dl-manager.",
    )
    return parser.parse_args()


def fetch_token(base_url: str, username: str, password: str) -> str:
    response = requests.post(
        f"{base_url.rstrip('/')}/issues-db-api/token",
        verify=False,
        timeout=120,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"username": username, "password": password},
    )
    response.raise_for_status()
    return response.json()["access_token"]


def run_job(
    base_url: str,
    token: str,
    project: str,
    batch_size: int,
    database_url: str,
) -> dict:
    body = {
        "auth": {"token": token},
        "config": {
            "database-url": database_url,
            "model": MODEL_ID,
            "version": "most-recent",
            "issue-keys": "",
            "issue-prefixes": project,
            "batch-size": batch_size,
        },
    }
    response = requests.post(
        f"{base_url.rstrip('/')}/dl-manager/predict-comments",
        verify=False,
        timeout=60 * 60 * 12,
        headers={"Content-Type": "application/json"},
        data=json.dumps(body),
    )
    response.raise_for_status()
    return response.json()


def iter_projects(projects: Iterable[str] | None) -> list[str]:
    chosen = projects or DEFAULT_PROJECTS
    return [project.strip().upper() for project in chosen if project.strip()]


def main() -> int:
    args = parse_args()
    token = fetch_token(args.base_url, args.username, args.password)
    for project in iter_projects(args.projects):
        print(f"[{project}] starting classification")
        payload = run_job(
            args.base_url,
            token,
            project,
            args.batch_size,
            args.database_url,
        )
        print(f"[{project}] {json.dumps(payload)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
