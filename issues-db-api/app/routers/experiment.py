"""
Experiment backend router for comparing PyLucene+reranking vs archRag.

Supports two experiment types:
- "single": Between-subjects blinded design (one system per task)
- "dual": Within-subjects blinded side-by-side (both systems, random column assignment)

Data stored in MongoDB `experiment_sessions` for the newer session API and
PostgreSQL `experiment_ratings` for legacy browser rating submissions.

Also includes legacy file-based endpoints from Ajay's experiment (POST /tasks,
POST /submit-ratings, POST /gpt4-response, POST /logs).
"""

import hashlib
import json
import os
import random
import threading
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from pymongo import MongoClient
from app.routers.authentication import validate_token

load_dotenv()

router = APIRouter(prefix="/experiment", tags=["experiment"])

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "issues")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "pass")
POSTGRES_HOST = os.environ.get(
    "POSTGRES_HOST",
    "psql" if os.environ.get("DOCKER", False) else "localhost",
)
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", os.environ.get("OPEN_AI_API_KEY", ""))
LOCAL_PROXY_URL = os.environ.get("ISSUES_DB_LOCAL_PROXY_URL", "http://host.docker.internal:8118").strip()
PROXY_STATE_PATH = os.environ.get(
    "ISSUES_DB_PROXY_STATE_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runtime", "proxy_settings.json"),
)
NO_PROXY_VALUE = os.environ.get(
    "NO_PROXY",
    "127.0.0.1,localhost,::1,issues-db-api,psql,mongo,dl-manager,archrag",
)
_PROXY_ENV_KEYS = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
]
_proxy_enabled = False
_proxy_url = LOCAL_PROXY_URL
_legacy_results_table_lock = threading.Lock()
_legacy_results_table_ready = False

SYSTEMS = ["pylucene_rerank", "archrag"]
DEFAULT_EXPERIMENT_REPO = "Apache"
DEFAULT_EXPERIMENT_PROJECT = "HDFS"

PROJECT_DISPLAY_NAMES = {
    ("Apache", "HDFS"): "Hadoop HDFS",
    ("Apache", "TIKA"): "Apache Tika",
    ("Apache", "LUCENE"): "Apache Lucene",
    ("Apache", "JCLOUDS"): "Apache jclouds",
    ("Apache", "MAPREDUCE"): "Apache MapReduce",
    ("Apache", "YARN"): "Apache YARN",
}


def _get_db():
    client = MongoClient(MONGO_URL)
    return client["MaestroExperiment"]


def _get_legacy_results_connection():
    try:
        import psycopg2
    except ImportError as exc:
        raise RuntimeError(
            "psycopg2-binary must be installed to persist experiment ratings in PostgreSQL."
        ) from exc

    conn = psycopg2.connect(
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
    )
    _ensure_legacy_results_table(conn)
    return conn


def _ensure_legacy_results_table(conn) -> None:
    global _legacy_results_table_ready
    if _legacy_results_table_ready:
        return

    with _legacy_results_table_lock:
        if _legacy_results_table_ready:
            return

        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS experiment_ratings (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    repo TEXT NOT NULL,
                    project TEXT NOT NULL,
                    project_name TEXT NOT NULL,
                    matriculation_number TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    question_key TEXT NOT NULL,
                    search_query TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    rerank_engine BOOLEAN NOT NULL DEFAULT FALSE,
                    gpt BOOLEAN NOT NULL DEFAULT FALSE,
                    config_hash TEXT NOT NULL,
                    ratings JSONB NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_experiment_ratings_lookup
                ON experiment_ratings (
                    repo,
                    project,
                    matriculation_number,
                    task_id,
                    question_key,
                    created_at,
                    id
                )
                """
            )
        conn.commit()
        _legacy_results_table_ready = True


def _legacy_result_filter_columns() -> Dict[str, str]:
    return {
        "repo": "repo",
        "project": "project",
        "matriculationNumber": "matriculation_number",
        "taskId": "task_id",
        "questionKey": "question_key",
    }


def _build_legacy_results_where_clause(filters: Dict[str, Any]) -> tuple[str, list[Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    for key, column in _legacy_result_filter_columns().items():
        value = filters.get(key)
        if value is None:
            continue
        clauses.append(f"{column} = %s")
        params.append(value)
    return " AND ".join(clauses), params


def _legacy_result_record_to_dict(record: Dict[str, Any]) -> Dict[str, Any]:
    ratings = record.get("ratings")
    if isinstance(ratings, str):
        ratings = json.loads(ratings)
    return {
        "_id": str(record["id"]),
        "repo": record["repo"],
        "project": record["project"],
        "project_name": record["project_name"],
        "matriculationNumber": record["matriculation_number"],
        "taskId": record["task_id"],
        "questionKey": record["question_key"],
        "searchQuery": record["search_query"],
        "engine": record["engine"],
        "rerank_engine": record["rerank_engine"],
        "gpt": record["gpt"],
        "config_hash": record["config_hash"],
        "ratings": ratings,
        "created_at": record["created_at"],
    }


def _insert_legacy_result(result: Dict[str, Any]) -> Dict[str, Any]:
    from psycopg2.extras import Json, RealDictCursor

    conn = _get_legacy_results_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO experiment_ratings (
                    repo,
                    project,
                    project_name,
                    matriculation_number,
                    task_id,
                    question_key,
                    search_query,
                    engine,
                    rerank_engine,
                    gpt,
                    config_hash,
                    ratings,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING
                    id,
                    repo,
                    project,
                    project_name,
                    matriculation_number,
                    task_id,
                    question_key,
                    search_query,
                    engine,
                    rerank_engine,
                    gpt,
                    config_hash,
                    ratings,
                    created_at
                """,
                (
                    result["repo"],
                    result["project"],
                    result["project_name"],
                    result["matriculationNumber"],
                    result["taskId"],
                    result["questionKey"],
                    result["searchQuery"],
                    result["engine"],
                    result["rerank_engine"],
                    result["gpt"],
                    result["config_hash"],
                    Json(result["ratings"]),
                    result["created_at"],
                ),
            )
            row = cur.fetchone()
        conn.commit()
        return _legacy_result_record_to_dict(row)
    finally:
        conn.close()


def _find_legacy_results(
    filters: Dict[str, Any],
    *,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    from psycopg2.extras import RealDictCursor

    conn = _get_legacy_results_connection()
    try:
        query = """
            SELECT
                id,
                repo,
                project,
                project_name,
                matriculation_number,
                task_id,
                question_key,
                search_query,
                engine,
                rerank_engine,
                gpt,
                config_hash,
                ratings,
                created_at
            FROM experiment_ratings
        """
        where_clause, params = _build_legacy_results_where_clause(filters)
        if where_clause:
            query += f" WHERE {where_clause}"
        query += " ORDER BY created_at ASC, id ASC"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [_legacy_result_record_to_dict(row) for row in rows]
    finally:
        conn.close()


def _count_legacy_results(filters: Dict[str, Any]) -> int:
    conn = _get_legacy_results_connection()
    try:
        query = "SELECT COUNT(*) FROM experiment_ratings"
        where_clause, params = _build_legacy_results_where_clause(filters)
        if where_clause:
            query += f" WHERE {where_clause}"
        with conn.cursor() as cur:
            cur.execute(query, params)
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def _read_proxy_state() -> dict | None:
    if not os.path.exists(PROXY_STATE_PATH):
        return None
    try:
        with open(PROXY_STATE_PATH, "r") as handle:
            return json.load(handle)
    except Exception:
        return None


def _write_proxy_state(enabled: bool, proxy_url: str) -> None:
    try:
        os.makedirs(os.path.dirname(PROXY_STATE_PATH), exist_ok=True)
        with open(PROXY_STATE_PATH, "w") as handle:
            json.dump({"enabled": enabled, "proxy_url": proxy_url}, handle, indent=2)
    except Exception:
        pass


def _apply_proxy_settings(enabled: bool, proxy_url: str, persist: bool = False) -> None:
    global _proxy_enabled, _proxy_url
    normalized_url = (proxy_url or LOCAL_PROXY_URL).strip() or LOCAL_PROXY_URL

    if enabled:
        for env_key in _PROXY_ENV_KEYS:
            os.environ[env_key] = normalized_url
        os.environ["NO_PROXY"] = NO_PROXY_VALUE
        os.environ["no_proxy"] = NO_PROXY_VALUE
    else:
        for env_key in _PROXY_ENV_KEYS:
            os.environ.pop(env_key, None)

    _proxy_enabled = enabled
    _proxy_url = normalized_url

    if persist:
        _write_proxy_state(enabled, normalized_url)


_stored_proxy_state = _read_proxy_state()
if _stored_proxy_state is not None:
    _apply_proxy_settings(
        bool(_stored_proxy_state.get("enabled", False)),
        str(_stored_proxy_state.get("proxy_url", LOCAL_PROXY_URL)),
        persist=False,
    )


def _load_task_definitions():
    """Load task definitions from the bundled JSON config."""
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "experiment_tasks.json"
    )
    if not os.path.exists(config_path):
        return None
    with open(config_path) as f:
        return json.load(f)


def _normalize_experiment_selection(
    repo: Optional[str] = None,
    project: Optional[str] = None,
) -> tuple[str, str]:
    selected_repo = (repo or DEFAULT_EXPERIMENT_REPO).strip() or DEFAULT_EXPERIMENT_REPO
    selected_project = (project or DEFAULT_EXPERIMENT_PROJECT).strip().upper() or DEFAULT_EXPERIMENT_PROJECT
    return selected_repo, selected_project


def _experiment_configs_dir() -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "experiment_configs",
    )


def _find_experiment_file_path(
    repo: Optional[str] = None,
    project: Optional[str] = None,
) -> Optional[str]:
    selected_repo, selected_project = _normalize_experiment_selection(repo, project)
    config_path = os.path.join(
        _experiment_configs_dir(),
        selected_repo,
        selected_project,
        "experiment_data.json",
    )
    if os.path.exists(config_path):
        return config_path

    legacy_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "experiment_data.json",
    )
    if (
        selected_repo == DEFAULT_EXPERIMENT_REPO
        and selected_project == DEFAULT_EXPERIMENT_PROJECT
        and os.path.exists(legacy_path)
    ):
        return legacy_path
    return None


def _list_available_experiment_projects() -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    configs_dir = _experiment_configs_dir()
    if os.path.isdir(configs_dir):
        for repo_name in sorted(os.listdir(configs_dir)):
            repo_dir = os.path.join(configs_dir, repo_name)
            if not os.path.isdir(repo_dir):
                continue
            for project_name in sorted(os.listdir(repo_dir)):
                project_dir = os.path.join(repo_dir, project_name)
                config_path = os.path.join(project_dir, "experiment_data.json")
                if not os.path.isfile(config_path):
                    continue
                project_display_name = _default_project_name(repo_name, project_name)
                try:
                    with open(config_path, "r") as handle:
                        payload = json.load(handle)
                    project_display_name = payload.get("project_name", project_display_name)
                except Exception:
                    pass
                items.append({
                    "repo": repo_name,
                    "project": project_name,
                    "project_name": project_display_name,
                })

    default_item = {
        "repo": DEFAULT_EXPERIMENT_REPO,
        "project": DEFAULT_EXPERIMENT_PROJECT,
        "project_name": _default_project_name(DEFAULT_EXPERIMENT_REPO, DEFAULT_EXPERIMENT_PROJECT),
    }
    if not any(
        item["repo"] == default_item["repo"] and item["project"] == default_item["project"]
        for item in items
    ) and _find_experiment_file_path(DEFAULT_EXPERIMENT_REPO, DEFAULT_EXPERIMENT_PROJECT):
        items.insert(0, default_item)

    return items


def _default_project_name(repo: str, project: str) -> str:
    return PROJECT_DISPLAY_NAMES.get((repo, project), f"{repo} {project}".strip())


def _load_legacy_task_definitions(experiment_data: Dict[str, Any]) -> Dict[str, Any]:
    """Prefer bundled task definitions, fall back to legacy in-file definitions."""
    bundled = _load_task_definitions() or {}
    legacy = experiment_data.get("task_details", {})

    if not bundled:
        return legacy
    if not legacy:
        return bundled

    merged = dict(bundled)
    for key, value in legacy.items():
        if key not in merged:
            merged[key] = value
    return merged


def _resolve_project_context(
    task_assignment: Dict[str, Any],
    task_definition: Dict[str, Any] | None,
    question_definition: Dict[str, Any] | None,
) -> Dict[str, str]:
    repo = (
        (question_definition or {}).get("repo")
        or (task_definition or {}).get("repo")
        or task_assignment.get("repo")
        or "Apache"
    )
    project = (
        (question_definition or {}).get("project")
        or (task_definition or {}).get("project")
        or task_assignment.get("project")
        or "HDFS"
    )
    project_name = (
        (question_definition or {}).get("project_name")
        or (task_definition or {}).get("project_name")
        or task_assignment.get("project_name")
        or _default_project_name(repo, project)
    )
    return {
        "repo": repo,
        "project": project,
        "project_name": project_name,
    }


def _config_hash(data: dict) -> str:
    """SHA-256 hash of JSON-serialized config for versioning."""
    raw = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _validate_gpt_caller(
    session_id: str | None,
    mtr_no: str | None,
    repo: Optional[str] = None,
    project: Optional[str] = None,
):
    """Reject GPT requests that lack a valid session_id or MtrNo."""
    from bson import ObjectId

    # Try session_id first
    if session_id:
        db = _get_db()
        try:
            session = db["experiment_sessions"].find_one({"_id": ObjectId(session_id)}, {"_id": 1})
        except Exception:
            session = None
        if session is not None:
            return

    # Try MtrNo against legacy experiment data
    if mtr_no:
        try:
            data = _load_experiment_data(repo=repo, project=project)
            student_data = data.get("student_data", {})
            if mtr_no in student_data:
                return
        except Exception:
            pass

    raise HTTPException(
        status_code=400,
        detail="A valid session_id or MtrNo is required to use this endpoint.",
    )


# --- Models (MongoDB-based) ---

class CreateSessionRequest(BaseModel):
    participant_id: str
    experiment_type: str  # "single" or "dual"

class SearchRating(BaseModel):
    issue_id: str
    rating: int

class SubmitResultsRequest(BaseModel):
    task_name: str
    question_key: str
    query: str
    system: Optional[str] = None  # For single: which system produced results
    results: Optional[List[SearchRating]] = None  # For single-system
    results_left: Optional[List[SearchRating]] = None  # For dual
    results_right: Optional[List[SearchRating]] = None  # For dual
    use_gpt_keywords: bool = False
    timestamp: Optional[str] = None

class GPTKeywordsRequest(BaseModel):
    prompt: str
    project_name: str = "Hadoop HDFS"
    repo: Optional[str] = None
    project: Optional[str] = None
    session_id: Optional[str] = None
    MtrNo: Optional[str] = None


class ProxySettingsUpdate(BaseModel):
    enabled: bool
    proxy_url: Optional[str] = None


# --- MongoDB-based endpoints ---

@router.post("/sessions")
def create_session(req: CreateSessionRequest):
    """Create a new experiment session with randomized system assignments."""
    if req.experiment_type not in ("single", "dual"):
        raise HTTPException(400, "experiment_type must be 'single' or 'dual'")

    db = _get_db()
    task_defs = _load_task_definitions()
    if task_defs is None:
        raise HTTPException(500, "Task definitions not found (experiment_tasks.json)")

    task_names = [k for k in task_defs.keys() if k not in ("task_details", "Likert Scale")]

    # Build system assignments with counterbalancing
    system_assignments = {}
    shuffled_systems = list(SYSTEMS)

    if req.experiment_type == "single":
        seed = hash(req.participant_id) % 1000
        rng = random.Random(seed)
        rng.shuffle(shuffled_systems)
        for i, task_name in enumerate(task_names):
            system_assignments[task_name] = {
                "assigned_system": shuffled_systems[i % len(SYSTEMS)]
            }
    else:  # dual
        seed = hash(req.participant_id) % 1000
        rng = random.Random(seed)
        for i, task_name in enumerate(task_names):
            if rng.random() < 0.5:
                mapping = {"left": "pylucene_rerank", "right": "archrag"}
            else:
                mapping = {"left": "archrag", "right": "pylucene_rerank"}
            system_assignments[task_name] = {
                "column_mapping": mapping
            }

    tasks = []
    for task_name in task_names:
        td = task_defs[task_name]
        tasks.append({
            "task_name": task_name,
            "description": td.get("description", ""),
            "questions": td.get("questions", {}),
        })

    session = {
        "participant_id": req.participant_id,
        "experiment_type": req.experiment_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config_hash": _config_hash(task_defs),
        "system_assignments": system_assignments,
        "tasks": tasks,
        "searches": [],
        "likert_scale": task_defs.get("Likert Scale", {}),
    }

    result = db["experiment_sessions"].insert_one(session)
    session["_id"] = str(result.inserted_id)

    return {"session_id": session["_id"], "session": _serialize_session(session)}


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    """Get session details including assigned tasks and system assignments."""
    from bson import ObjectId
    db = _get_db()
    try:
        session = db["experiment_sessions"].find_one({"_id": ObjectId(session_id)})
    except Exception:
        raise HTTPException(404, "Invalid session ID")
    if session is None:
        raise HTTPException(404, "Session not found")
    return _serialize_session(session)


@router.post("/sessions/{session_id}/results")
def submit_results(session_id: str, req: SubmitResultsRequest):
    """Submit ratings for a search within a session."""
    from bson import ObjectId
    db = _get_db()

    try:
        session = db["experiment_sessions"].find_one({"_id": ObjectId(session_id)})
    except Exception:
        raise HTTPException(404, "Invalid session ID")
    if session is None:
        raise HTTPException(404, "Session not found")

    search_entry = {
        "task_name": req.task_name,
        "question_key": req.question_key,
        "query": req.query,
        "use_gpt_keywords": req.use_gpt_keywords,
        "timestamp": req.timestamp or datetime.now(timezone.utc).isoformat(),
    }

    if session["experiment_type"] == "single":
        search_entry["system"] = req.system
        search_entry["results"] = [r.model_dump() for r in (req.results or [])]
    else:  # dual
        search_entry["results_left"] = [r.model_dump() for r in (req.results_left or [])]
        search_entry["results_right"] = [r.model_dump() for r in (req.results_right or [])]

    db["experiment_sessions"].update_one(
        {"_id": ObjectId(session_id)},
        {"$push": {"searches": search_entry}}
    )

    return {"success": True, "message": "Results saved"}


@router.post("/gpt-keywords")
def gpt_keywords(req: GPTKeywordsRequest):
    """Extract search keywords using GPT-4o."""
    # Rate check: require a valid session_id or MtrNo
    _validate_gpt_caller(
        req.session_id,
        req.MtrNo,
        repo=req.repo,
        project=req.project,
    )
    if not OPENAI_API_KEY:
        raise HTTPException(500, "OpenAI API key not configured")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        chat = client.chat.completions.create(
            messages=[{
                "role": "user",
                "content": (
                    f"{req.prompt} Can you give us a list of the most useful "
                    f"5 keywords to search for issues in the issue tracker of "
                    f"{req.project_name} that answer the provided question. "
                    f"Please provide only the list of keywords without "
                    f"duplication separated by a space. Do not provide any other text."
                ),
            }],
            model="gpt-4o",
        )
        answer = chat.choices[0].message.content.strip()
        keywords = answer.split()
        if len(keywords) < 3 or len(keywords) > 15:
            return {"keywords": None, "error": "Unexpected keyword count", "raw": answer}
        return {"keywords": answer}
    except Exception as e:
        return {"keywords": None, "error": str(e)}


@router.get("/task-definitions")
def list_tasks():
    """List all task definitions."""
    task_defs = _load_task_definitions()
    if task_defs is None:
        raise HTTPException(500, "Task definitions not found")

    tasks = {}
    for key, value in task_defs.items():
        if key not in ("task_details", "Likert Scale"):
            tasks[key] = value

    return {
        "tasks": tasks,
        "likert_scale": task_defs.get("Likert Scale", {}),
        "instructions": task_defs.get("task_details", ""),
    }


@router.get("/export")
def export_data(token=Depends(validate_token)):
    """Export all experiment data as JSON for evaluation."""
    db = _get_db()
    sessions = list(db["experiment_sessions"].find({}))

    task_defs = _load_task_definitions()
    export = {
        "sessions": [_serialize_session(s) for s in sessions],
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "current_config_hash": _config_hash(task_defs) if task_defs else None,
    }
    return export


def _serialize_session(session):
    """Convert MongoDB document to JSON-serializable dict."""
    s = dict(session)
    if "_id" in s:
        s["_id"] = str(s["_id"])
    return s


def _serialize_legacy_result(row: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(row)
    if "_id" in item:
        item["_id"] = str(item["_id"])
    created_at = item.get("created_at")
    if isinstance(created_at, datetime):
        item["created_at"] = created_at.isoformat()
    return item


@router.get("/projects")
def list_legacy_experiment_projects():
    """List legacy experiment projects backed by per-project JSON configs."""
    projects = _list_available_experiment_projects()
    return {
        "projects": projects,
        "default": {
            "repo": DEFAULT_EXPERIMENT_REPO,
            "project": DEFAULT_EXPERIMENT_PROJECT,
            "project_name": _default_project_name(
                DEFAULT_EXPERIMENT_REPO,
                DEFAULT_EXPERIMENT_PROJECT,
            ),
        },
    }


@router.get("/proxy-settings")
def get_proxy_settings():
    return {
        "enabled": _proxy_enabled,
        "proxy_url": _proxy_url,
        "local_proxy_url": LOCAL_PROXY_URL,
    }


@router.post("/proxy-settings")
def set_proxy_settings(request: ProxySettingsUpdate):
    _apply_proxy_settings(
        enabled=request.enabled,
        proxy_url=request.proxy_url or LOCAL_PROXY_URL,
        persist=True,
    )
    return {
        "enabled": _proxy_enabled,
        "proxy_url": _proxy_url,
        "local_proxy_url": LOCAL_PROXY_URL,
    }


@router.get("/legacy-results")
def export_legacy_results(
    repo: Optional[str] = None,
    project: Optional[str] = None,
    matriculation_number: Optional[str] = None,
    task_id: Optional[str] = None,
    question_key: Optional[str] = None,
    limit: int = 1000,
    token=Depends(validate_token),
):
    """Export persisted legacy experiment submissions from PostgreSQL."""
    filters: Dict[str, Any] = {}
    if repo:
        filters["repo"] = repo
    if project:
        filters["project"] = project.upper()
    if matriculation_number:
        filters["matriculationNumber"] = matriculation_number
    if task_id:
        filters["taskId"] = task_id
    if question_key:
        filters["questionKey"] = question_key

    capped_limit = max(1, min(limit, 10000))
    total = _count_legacy_results(filters)
    rows = _find_legacy_results(filters, limit=capped_limit)

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "filters": filters,
        "limit": capped_limit,
        "returned": len(rows),
        "total": total,
        "results": [_serialize_legacy_result(row) for row in rows],
    }


# ---------------------------------------------------------------------------
# Legacy file-based experiment endpoints (from Ajay's branch)
# ---------------------------------------------------------------------------

class MtrNo(BaseModel):
    MtrNo: str
    password: Optional[str] = None
    repo: Optional[str] = None
    project: Optional[str] = None


class GPT4Request(BaseModel):
    prompt: str
    project_name: str = "Hadoop HDFS"
    repo: Optional[str] = None
    project: Optional[str] = None
    session_id: Optional[str] = None
    MtrNo: Optional[str] = None

class LegacyRating(BaseModel):
    issue_id: str
    rating: Any

class SaveResult(BaseModel):
    matriculationNumber: str
    taskId: str
    questionKey: str
    searchQuery: str
    ratings: List[LegacyRating]
    repo: Optional[str] = None
    project: Optional[str] = None


def _get_experiment_file_path(
    repo: Optional[str] = None,
    project: Optional[str] = None,
) -> str:
    file_path = _find_experiment_file_path(repo=repo, project=project)
    if file_path:
        return file_path
    selected_repo, selected_project = _normalize_experiment_selection(repo, project)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No experiment config found for {selected_repo}/{selected_project}",
    )


def _validate_json(data: Any) -> bool:
    try:
        json.dumps(data)
        return True
    except (TypeError, ValueError):
        return False


def _load_experiment_data(
    repo: Optional[str] = None,
    project: Optional[str] = None,
) -> Dict[str, Any]:
    file_path = _get_experiment_file_path(repo=repo, project=project)
    with open(file_path, "r") as file:
        data = json.load(file)
    selected_repo, selected_project = _normalize_experiment_selection(repo, project)
    data.setdefault("repo", selected_repo)
    data.setdefault("project", selected_project)
    data.setdefault("project_name", _default_project_name(selected_repo, selected_project))
    return data


def _validate_result_data(result_data: SaveResult, experiment_data: Dict[str, Any]) -> bool:
    student_data = experiment_data.get("student_data", {})
    matriculation_number = result_data.matriculationNumber
    if matriculation_number not in student_data:
        return False
    student = student_data[matriculation_number]
    task_names = [task["taskName"] for task in student["tasks"]]
    if result_data.taskId not in task_names:
        return False
    return True


def _load_legacy_results(
    repo: str,
    project: str,
    matriculation_number: str,
) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    rows = _find_legacy_results(
        {
            "repo": repo,
            "project": project,
            "matriculationNumber": matriculation_number,
        }
    )

    results: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for row in rows:
        task_id = row["taskId"]
        question_key = row["questionKey"]
        entry = {k: v for k, v in row.items() if k not in {"_id", "matriculationNumber", "created_at"}}
        results.setdefault(task_id, {}).setdefault(question_key, []).append(entry)
    return results


def _merge_solutions(
    base_solutions: Dict[str, List[Dict[str, Any]]] | None,
    persisted_solutions: Dict[str, List[Dict[str, Any]]] | None,
) -> Dict[str, List[Dict[str, Any]]]:
    merged: Dict[str, List[Dict[str, Any]]] = {}
    for source in (base_solutions or {}, persisted_solutions or {}):
        for question_key, entries in source.items():
            merged.setdefault(question_key, []).extend(list(entries))
    return merged


@router.post("/tasks")
def get_experiment_tasks(request_data: MtrNo):
    """Get tasks assigned to a specific user (by matriculation number)."""
    mtr_no = request_data.MtrNo
    selected_repo, selected_project = _normalize_experiment_selection(
        request_data.repo,
        request_data.project,
    )
    data = _load_experiment_data(repo=selected_repo, project=selected_project)

    student_data = data.get("student_data", {})
    if mtr_no not in student_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No experiment data found for MtrNo: {mtr_no}"
        )

    # Password check
    passwords = data.get("passwords", {})
    expected_pw = passwords.get(mtr_no)
    if expected_pw is not None:
        if request_data.password != expected_pw:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password"
            )

    experiment_data = student_data[mtr_no]

    debug = data.get("debug", False)
    project_name = data.get("project_name", _default_project_name(selected_repo, selected_project))

    task_definitions = _load_legacy_task_definitions(data)
    response = []
    persisted_results = _load_legacy_results(selected_repo, selected_project, mtr_no)
    for task in experiment_data["tasks"]:
        task_name = task["taskName"]
        per_question_config = task.get("questions", {})
        task_info = {
            "taskName": task_name,
            "solutions": _merge_solutions(
                task.get("solutions", {}),
                persisted_results.get(task_name),
            ),
        }

        top_level = task_definitions
        task_details = top_level.get(task_name)
        if task_details:
            task_info.update(_resolve_project_context(task, task_details, None))
            task_info["description"] = task_details.get("description")
            # Merge per-question config (engine, rerank_engine, gpt) into each question object
            questions = {}
            for qkey, qval in (task_details.get("questions") or {}).items():
                q = dict(qval)
                q.update(_resolve_project_context(task, task_details, qval))
                q_config = per_question_config.get(qkey, {})
                q["engine"] = q_config.get("engine", "pylucene")
                q["rerank_engine"] = q_config.get("rerank_engine", False)
                q["gpt"] = q_config.get("gpt", False)
                questions[qkey] = q
            task_info["questions"] = questions
            task_info["task_details"] = (
                task_details.get("task_details")
                or top_level.get("task_details")
            )
            task_info["lekert_scale"] = (
                task_details.get("Likert Scale")
                or top_level.get("Likert Scale")
            )

        response.append(task_info)

    return {
        "debug": debug,
        "repo": selected_repo,
        "project": selected_project,
        "project_name": project_name,
        "tasks": response,
    }


@router.post("/submit-ratings")
def save_result(result_data: SaveResult):
    """Submit ratings for a legacy file-based experiment."""
    selected_repo, selected_project = _normalize_experiment_selection(
        result_data.repo,
        result_data.project,
    )
    data = _load_experiment_data(repo=selected_repo, project=selected_project)

    if not _validate_result_data(result_data, data):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid data. Unable to save results."
        )

    student_data = data["student_data"]
    matriculation_number = result_data.matriculationNumber
    student = student_data[matriculation_number]

    task_id = result_data.taskId
    question_key = result_data.questionKey
    search_query = result_data.searchQuery
    ratings = [{"issue_id": r.issue_id, "rating": str(r.rating)} for r in result_data.ratings]

    engine = "pylucene"
    rerank_engine = False
    gpt = False
    task_definitions = _load_legacy_task_definitions(data)
    project_context = {
        "repo": selected_repo,
        "project": selected_project,
        "project_name": data.get("project_name", _default_project_name(selected_repo, selected_project)),
    }
    for task in student["tasks"]:
        if task["taskName"] == task_id:
            q_config = task.get("questions", {}).get(question_key, {})
            task_definition = task_definitions.get(task_id, {})
            question_definition = (task_definition.get("questions") or {}).get(question_key)
            if question_definition is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid question key '{question_key}' for task '{task_id}'",
                )
            project_context = _resolve_project_context(task, task_definition, question_definition)
            engine = q_config.get("engine", "pylucene")
            rerank_engine = q_config.get("rerank_engine", False)
            gpt = q_config.get("gpt", False)
            break

    solution = {
        "repo": project_context["repo"],
        "project": project_context["project"],
        "project_name": project_context["project_name"],
        "matriculationNumber": matriculation_number,
        "taskId": task_id,
        "questionKey": question_key,
        "searchQuery": search_query,
        "engine": engine,
        "rerank_engine": rerank_engine,
        "gpt": gpt,
        "config_hash": _config_hash(data),
        "ratings": ratings,
        "created_at": datetime.now(timezone.utc),
    }
    _insert_legacy_result(solution)
    return {"success": "Result saved successfully"}

@router.post("/gpt4-response")
def fetch_gpt4_response(request: GPT4Request):
    """Legacy GPT-4 keyword extraction endpoint."""
    # Rate check: require a valid session_id or MtrNo
    _validate_gpt_caller(
        request.session_id,
        request.MtrNo,
        repo=request.repo,
        project=request.project,
    )
    api_key = OPENAI_API_KEY
    if not api_key:
        return {"detail": "OpenAI API key not configured"}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        chat_completion = client.chat.completions.create(
            messages=[{
                "role": "user",
                "content": request.prompt + f" Can you give us a list of the most useful 5 keywords to search for issues in the issue tracker of {request.project_name} that answer the provided question. Please provide only the list of keywords without duplication separated by a space. do not provide any other text.",
            }],
            model="gpt-4o",
        )

        answer = chat_completion.choices[0].message.content.strip()
        keywords = answer.split()
        if (len(keywords) < 5 or len(keywords) > 10) or any(not keyword.isalpha() for keyword in keywords):
            raise ValueError("failed to fetch the results")

        return {"answer": answer}

    except Exception as e:
        return {"detail": f"An error occurred: {e}"}


class LogEntry(BaseModel):
    level: str
    message: str
    timestamp: str


@router.post("/logs")
def save_log(log_entry: LogEntry):
    """Save experiment log entry to a daily log file."""
    current_date = datetime.now().strftime("%Y-%m-%d")
    log_file_name = f"logs_{current_date}.log"
    log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), log_file_name)

    if os.path.exists(log_file_path):
        with open(log_file_path, "r") as file:
            try:
                logs = json.load(file)
            except json.JSONDecodeError:
                logs = []
    else:
        logs = []

    logs.append(log_entry.model_dump())

    if not _validate_json(logs):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid log data. Cannot save."
        )

    with open(log_file_path, "w") as file:
        json.dump(logs, file, indent=4)

    return {"success": "Log saved successfully"}
