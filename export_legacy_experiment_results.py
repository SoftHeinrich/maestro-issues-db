#!/usr/bin/env python3
"""Export persisted legacy experiment results via the authenticated API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://maestro.localhost:4269")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--repo", default=None)
    parser.add_argument("--project", default=None)
    parser.add_argument("--matriculation-number", default=None)
    parser.add_argument("--task-id", default=None)
    parser.add_argument("--question-key", default=None)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--output", required=True, help="Output JSON path.")
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


def main() -> int:
    args = parse_args()
    token = fetch_token(args.base_url, args.username, args.password)
    params = {"limit": args.limit}
    if args.repo:
        params["repo"] = args.repo
    if args.project:
        params["project"] = args.project
    if args.matriculation_number:
        params["matriculation_number"] = args.matriculation_number
    if args.task_id:
        params["task_id"] = args.task_id
    if args.question_key:
        params["question_key"] = args.question_key

    response = requests.get(
        f"{args.base_url.rstrip('/')}/issues-db-api/experiment/legacy-results",
        verify=False,
        timeout=120,
        headers={"Authorization": f"Bearer {token}"},
        params=params,
    )
    response.raise_for_status()

    payload = response.json()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2))
    print(
        f"Wrote {payload['returned']} of {payload['total']} results to {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
