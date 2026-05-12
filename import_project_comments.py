#!/usr/bin/env python3
"""Import project comments from MongoDB Jira issues into PostgreSQL.

This script reads issue documents from `JiraRepos.<collection>` and flattens
their Jira comments into the shared `issues_comments` PostgreSQL table used by
PyLucene reranking and comment classification.

It is intentionally idempotent at the `(issue_id, comment_id)` level even
though the target table has no unique constraint for that pair.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

import psycopg2
import pymongo
from psycopg2.extras import execute_values


DEFAULT_MONGO_URI = "mongodb://localhost:27017"
DEFAULT_MONGO_DB = "JiraRepos"
DEFAULT_MONGO_COLLECTION = "Apache"
DEFAULT_PG_DB = "issues"
DEFAULT_PG_USER = "postgres"
DEFAULT_PG_PASSWORD = "pass"
DEFAULT_PG_HOST = "localhost"
DEFAULT_PG_PORT = 5432
DEFAULT_ISSUE_BATCH = 250


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import Jira comments for a project prefix into PostgreSQL."
    )
    parser.add_argument(
        "--project",
        required=True,
        help="Issue key prefix to import, e.g. LUCENE or YARN.",
    )
    parser.add_argument("--mongo-uri", default=DEFAULT_MONGO_URI)
    parser.add_argument("--mongo-db", default=DEFAULT_MONGO_DB)
    parser.add_argument("--mongo-collection", default=DEFAULT_MONGO_COLLECTION)
    parser.add_argument("--mongo-user", default=None)
    parser.add_argument("--mongo-password", default=None)
    parser.add_argument("--mongo-auth-db", default="admin")
    parser.add_argument("--pg-db", default=DEFAULT_PG_DB)
    parser.add_argument("--pg-user", default=DEFAULT_PG_USER)
    parser.add_argument("--pg-password", default=DEFAULT_PG_PASSWORD)
    parser.add_argument("--pg-host", default=DEFAULT_PG_HOST)
    parser.add_argument("--pg-port", type=int, default=DEFAULT_PG_PORT)
    parser.add_argument(
        "--issue-batch",
        type=int,
        default=DEFAULT_ISSUE_BATCH,
        help="Number of Mongo issues to process per batch.",
    )
    parser.add_argument(
        "--limit-issues",
        type=int,
        default=None,
        help="Optional cap for smoke-testing on a subset of issues.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute import stats without writing to PostgreSQL.",
    )
    return parser.parse_args()


def iter_chunks(cursor: Iterable[dict], chunk_size: int) -> Iterator[list[dict]]:
    batch: list[dict] = []
    for item in cursor:
        batch.append(item)
        if len(batch) >= chunk_size:
            yield batch
            batch = []
    if batch:
        yield batch


def load_known_bot_display_names(toolkit_dir: Path) -> set[str]:
    path = toolkit_dir / "known_bot_authors.txt"
    output: set[str] = set()
    if not path.exists():
        return output
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        output.add(line)
    return output


def load_known_bot_author_names(toolkit_dir: Path) -> set[str]:
    path = toolkit_dir / "bot_author_names_sql.txt"
    output: set[str] = set()
    if not path.exists():
        return output
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        output.add(line)
    return output


def parse_jira_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def is_bot_comment(
    author_name: str | None,
    author_display_name: str | None,
    body: str | None,
    bot_display_names: set[str],
    bot_author_names: set[str],
) -> bool:
    if author_display_name and author_display_name in bot_display_names:
        return True
    if author_name and author_name in bot_author_names:
        return True

    lower_name = (author_name or "").lower()
    lower_display = (author_display_name or "").lower()
    lower_body = (body or "").lower()

    for needle in ("bot", "jenkins", "hudson", "github", "qa", "ci"):
        if needle in lower_name or needle in lower_display:
            return True

    for needle in (
        "this message is automatically generated",
        "automatically generated",
        "moved to github issue",
    ):
        if needle in lower_body:
            return True
    return False


def fetch_existing_comment_pairs(pg_conn, issue_ids: list[str]) -> set[tuple[str, str]]:
    if not issue_ids:
        return set()
    query = """
        SELECT issue_id, comment_id
        FROM issues_comments
        WHERE issue_id = ANY(%s)
    """
    with pg_conn.cursor() as cur:
        cur.execute(query, (issue_ids,))
        return {(issue_id, comment_id) for issue_id, comment_id in cur.fetchall()}


def sync_issues_comments_sequence(pg_conn) -> None:
    query = """
        SELECT setval(
            'public.issues_comments_id_seq',
            COALESCE((SELECT MAX(id) FROM issues_comments), 0) + 1,
            false
        )
    """
    with pg_conn.cursor() as cur:
        cur.execute(query)
    pg_conn.commit()


def main() -> int:
    args = parse_args()
    project = args.project.upper()

    repo_root = Path(__file__).resolve().parents[1]
    toolkit_dir = repo_root / "maestro-toolkit"
    bot_display_names = load_known_bot_display_names(toolkit_dir)
    bot_author_names = load_known_bot_author_names(toolkit_dir)

    mongo_kwargs = {}
    if args.mongo_user is not None:
        mongo_kwargs["username"] = args.mongo_user
        mongo_kwargs["password"] = args.mongo_password if args.mongo_password is not None else ""
        mongo_kwargs["authSource"] = args.mongo_auth_db
    mongo = pymongo.MongoClient(args.mongo_uri, **mongo_kwargs)
    collection = mongo[args.mongo_db][args.mongo_collection]

    pg_conn = psycopg2.connect(
        dbname=args.pg_db,
        user=args.pg_user,
        password=args.pg_password,
        host=args.pg_host,
        port=args.pg_port,
    )
    sync_issues_comments_sequence(pg_conn)

    mongo_query = {
        "key": {"$regex": f"^{project}-"},
        "fields.comment.comments.0": {"$exists": True},
    }
    projection = {
        "_id": 1,
        "key": 1,
        "fields.comment.comments": 1,
    }

    total_issue_count = collection.count_documents(mongo_query)
    print(f"Mongo issues with comments for {project}: {total_issue_count}")
    if total_issue_count == 0:
        pg_conn.close()
        mongo.close()
        return 0

    cursor = collection.find(mongo_query, projection=projection).sort("key", 1)
    if args.limit_issues is not None:
        cursor = cursor.limit(args.limit_issues)

    total_comments_seen = 0
    total_comments_inserted = 0
    total_existing = 0
    total_bot_comments = 0
    total_classifier_candidates = 0

    insert_sql = """
        INSERT INTO issues_comments (
            mongo_id,
            issue_id,
            comment_id,
            author_name,
            author_display_name,
            author_time_zone,
            body,
            is_bot,
            created,
            updated
        ) VALUES %s
    """

    try:
        for issue_batch in iter_chunks(cursor, args.issue_batch):
            issue_ids = [doc["key"] for doc in issue_batch]
            existing_pairs = fetch_existing_comment_pairs(pg_conn, issue_ids)

            rows_to_insert: list[tuple] = []
            for doc in issue_batch:
                mongo_id = str(doc["_id"])
                issue_id = doc["key"]
                comments = doc.get("fields", {}).get("comment", {}).get("comments", [])

                for comment in comments:
                    total_comments_seen += 1
                    comment_id = str(comment.get("id") or "")
                    if not comment_id:
                        continue

                    key = (issue_id, comment_id)
                    if key in existing_pairs:
                        total_existing += 1
                        continue

                    author = comment.get("author", {}) or {}
                    author_name = author.get("name")
                    author_display_name = author.get("displayName")
                    author_time_zone = author.get("timeZone")
                    body = comment.get("body") or ""
                    is_bot = is_bot_comment(
                        author_name,
                        author_display_name,
                        body,
                        bot_display_names,
                        bot_author_names,
                    )
                    if is_bot:
                        total_bot_comments += 1
                    if (not is_bot) and len(body) > 200:
                        total_classifier_candidates += 1

                    rows_to_insert.append(
                        (
                            mongo_id,
                            issue_id,
                            comment_id,
                            author_name,
                            author_display_name,
                            author_time_zone,
                            body,
                            is_bot,
                            parse_jira_timestamp(comment.get("created")),
                            parse_jira_timestamp(comment.get("updated")),
                        )
                    )

            if rows_to_insert and not args.dry_run:
                with pg_conn.cursor() as cur:
                    execute_values(cur, insert_sql, rows_to_insert, page_size=1000)
                pg_conn.commit()
                total_comments_inserted += len(rows_to_insert)

            if rows_to_insert and args.dry_run:
                total_comments_inserted += len(rows_to_insert)

            print(
                f"Processed issues={len(issue_batch)} "
                f"seen_comments={total_comments_seen} "
                f"new_comments={total_comments_inserted} "
                f"existing_comments={total_existing}"
            )
    finally:
        pg_conn.close()
        mongo.close()

    mode = "dry-run" if args.dry_run else "import"
    print(
        f"{mode} complete for {project}: "
        f"seen={total_comments_seen}, "
        f"inserted={total_comments_inserted}, "
        f"existing={total_existing}, "
        f"bot_comments={total_bot_comments}, "
        f"classifier_candidates={total_classifier_candidates}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
