"""
Experiment backend router for comparing PyLucene+reranking vs archRag.

Supports two experiment types:
- "single": Between-subjects blinded design (one system per task)
- "dual": Within-subjects blinded side-by-side (both systems, random column assignment)

Data stored in MongoDB `experiment_sessions` and `experiment_tasks` collections.

Also includes legacy file-based endpoints from Ajay's experiment (POST /tasks,
POST /submit-ratings, POST /gpt4-response, POST /logs).
"""

import json
import os
import random
from datetime import datetime
from shutil import copyfile

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from pymongo import MongoClient

load_dotenv()

router = APIRouter(prefix="/experiment", tags=["experiment"])

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", os.environ.get("OPEN_AI_API_KEY", ""))

SYSTEMS = ["pylucene_rerank", "archrag"]


def _get_db():
    client = MongoClient(MONGO_URL)
    return client["MaestroExperiment"]


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
        "created_at": datetime.utcnow().isoformat(),
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
        "timestamp": req.timestamp or datetime.utcnow().isoformat(),
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
def export_data():
    """Export all experiment data as JSON for evaluation."""
    db = _get_db()
    sessions = list(db["experiment_sessions"].find({}))

    export = {
        "sessions": [_serialize_session(s) for s in sessions],
        "exported_at": datetime.utcnow().isoformat(),
    }
    return export


def _serialize_session(session):
    """Convert MongoDB document to JSON-serializable dict."""
    s = dict(session)
    if "_id" in s:
        s["_id"] = str(s["_id"])
    return s


# ---------------------------------------------------------------------------
# Legacy file-based experiment endpoints (from Ajay's branch)
# ---------------------------------------------------------------------------

class MtrNo(BaseModel):
    MtrNo: str

class LegacyRating(BaseModel):
    issue_id: str
    rating: str

class SaveResult(BaseModel):
    matriculationNumber: str
    taskId: str
    questionKey: str
    searchQuery: str
    ratings: List[LegacyRating]


def _get_experiment_file_path() -> str:
    current_directory = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_directory, "..", "experiment_data.json")


def _create_backup(file_path: str) -> None:
    backup_path = f"{file_path}.bak"
    copyfile(file_path, backup_path)


def _validate_json(data: Any) -> bool:
    try:
        json.dumps(data)
        return True
    except (TypeError, ValueError):
        return False


def _load_experiment_data() -> Dict[str, Any]:
    file_path = _get_experiment_file_path()
    with open(file_path, "r") as file:
        return json.load(file)


def _save_experiment_data(data: Dict[str, Any]) -> None:
    file_path = _get_experiment_file_path()
    _create_backup(file_path)
    if not _validate_json(data):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid data. Unable to save results."
        )
    with open(file_path, "w") as file:
        json.dump(data, file, indent=4)


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


@router.post("/tasks")
def get_experiment_tasks(request_data: MtrNo):
    """Get tasks assigned to a specific user (by matriculation number)."""
    mtr_no = request_data.MtrNo
    data = _load_experiment_data()

    student_data = data.get("student_data", {})
    if mtr_no not in student_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No experiment data found for MtrNo: {mtr_no}"
        )

    experiment_data = student_data[mtr_no]

    response = []
    for task in experiment_data["tasks"]:
        task_name = task["taskName"]
        task_info = {
            "taskName": task_name,
            "rerank_engine": task["rerank_engine"],
            "gpt": task["gpt"],
            "solutions": task["solutions"]
        }

        task_details = data.get("task_details", {}).get(task_name)
        if task_details:
            task_info["description"] = task_details.get("description")
            task_info["questions"] = task_details.get("questions")
            task_info["task_details"] = data.get("task_details", {}).get("task_details")
            task_info["lekert_scale"] = data.get("task_details", {}).get("Likert Scale")

        response.append(task_info)

    return response


@router.post("/submit-ratings")
def save_result(result_data: SaveResult):
    """Submit ratings for a legacy file-based experiment."""
    data = _load_experiment_data()

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
    ratings = [{"issue_id": r.issue_id, "rating": r.rating} for r in result_data.ratings]

    solution = {
        "taskId": task_id,
        "questionKey": question_key,
        "searchQuery": search_query,
        "ratings": ratings
    }

    for task in student["tasks"]:
        if task["taskName"] == task_id:
            task["solutions"].setdefault(question_key, []).append(solution)
            break

    _save_experiment_data(data)
    return {"success": "Result saved successfully"}


class GPT4Request(BaseModel):
    prompt: str


@router.post("/gpt4-response")
def fetch_gpt4_response(request: GPT4Request):
    """Legacy GPT-4 keyword extraction endpoint."""
    api_key = OPENAI_API_KEY
    if not api_key:
        return {"detail": "OpenAI API key not configured"}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        chat_completion = client.chat.completions.create(
            messages=[{
                "role": "user",
                "content": request.prompt + " Can you give us a list of the most useful 5 keywords to search for issues in the issue tracker of Hadoop HDFS that answer the provided question. Please provide only the list of keywords without duplication separated by a space. do not provide any other text.",
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
