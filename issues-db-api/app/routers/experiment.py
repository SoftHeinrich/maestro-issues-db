import json
import os
from datetime import datetime
from shutil import copyfile
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Any, Dict, List
from openai import OpenAI


load_dotenv()
api_key = os.getenv("OPEN_AI_API_KEY", "")

router = APIRouter(tags=["experiment"])

class MtrNo(BaseModel):
    MtrNo: str

class Rating(BaseModel):
    issue_id: str
    rating: str

class SaveResult(BaseModel):
    matriculationNumber: str
    taskId: str
    questionKey: str
    searchQuery: str
    ratings: List[Rating]

def get_experiment_file_path() -> str:
    current_directory = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_directory, "..", "experiment_data.json")

def create_backup(file_path: str) -> None:
    backup_path = f"{file_path}.bak"
    copyfile(file_path, backup_path)

def validate_json(data: Any) -> bool:
    """
    Validates if the given data can be converted to a JSON string.
    Returns True if valid, False otherwise.
    """
    try:
        json.dumps(data)
        return True
    except (TypeError, ValueError):
        return False

def load_experiment_data() -> Dict[str, Any]:
    file_path = get_experiment_file_path()
    with open(file_path, "r") as file:
        return json.load(file)

def save_experiment_data(data: Dict[str, Any]) -> None:
    file_path = get_experiment_file_path()

    # Create a backup before saving
    create_backup(file_path)

    # Validate JSON before saving
    if not validate_json(data):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid data. Unable to save results."
        )

    # Save the updated data
    with open(file_path, "w") as file:
        json.dump(data, file, indent=4)

def validate_result_data(result_data: SaveResult, experiment_data: Dict[str, Any]) -> bool:
    student_data = experiment_data.get("student_data", {})
    matriculation_number = result_data.matriculationNumber

    # Ensure the student exists
    if matriculation_number not in student_data:
        return False

    student = student_data[matriculation_number]

    # Ensure the task exists
    task_names = [task["taskName"] for task in student["tasks"]]
    if result_data.taskId not in task_names:
        return False

    return True

@router.post("/tasks")
def get_experiment_tasks(request_data: MtrNo):
    mtr_no = request_data.MtrNo
    data = load_experiment_data()
    
    # Finding the experiment data for the provided MtrNo
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

        # Find task details from the task_details section of the JSON
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
    data = load_experiment_data()

    # Validate data before saving
    if not validate_result_data(result_data, data):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid data. Unable to save results."
        )

    # Get the student data section
    student_data = data["student_data"]
    matriculation_number = result_data.matriculationNumber

    student = student_data[matriculation_number]

    # Add the result to the solutions
    task_id = result_data.taskId
    question_key = result_data.questionKey
    search_query = result_data.searchQuery

    # Convert `Rating` objects to dictionaries for serialization
    ratings = [{"issue_id": rating.issue_id, "rating": rating.rating} for rating in result_data.ratings]

    solution = {
        "taskId": task_id,
        "questionKey": question_key,
        "searchQuery": search_query,
        "ratings": ratings
    }

    # Append the solution to the student's task solutions
    for task in student["tasks"]:
        if task["taskName"] == task_id:
            task["solutions"].setdefault(question_key, []).append(solution)
            break

    # Save updated data back to the JSON file
    save_experiment_data(data)

    return {"success": "Result saved successfully"}





class GPT4Request(BaseModel):
    prompt: str


@router.post("/gpt4-response")
def fetch_gpt4_response(request: GPT4Request):
    
    try:
        client = OpenAI(
            api_key=api_key
        )

        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": request.prompt + " Can you give us a list of the most useful 5 keywords to search for issues in the issue tracker of Hadoop HDFS that answer the provided question. Please provide only the list of keywords without duplication separated by a space. do not provide any other text.",
                }
            ],
            model="gpt-4o",
        )
        
        # Extract the assistant's reply
        answer = chat_completion.choices[0].message.content.strip()
        print(answer)

        # Validate the response
        keywords = answer.split()
        if (len(keywords) < 5 or len(keywords) > 10)  or any(not keyword.isalpha() for keyword in keywords):
            raise ValueError("failed to fetch the results")

        return {"answer": answer}
    
    except Exception as e:
        return {"detail":f"An error occurred: {e}"}


class LogEntry(BaseModel):
    level: str
    message: str
    timestamp: str

# New endpoint for storing logs
@router.post("/logs")
def save_log(log_entry: LogEntry):
    current_date = datetime.now().strftime("%Y-%m-%d")
    log_file_name = f"logs_{current_date}.log"
    log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), log_file_name)

    # Load existing logs
    if os.path.exists(log_file_path):
        with open(log_file_path, "r") as file:
            try:
                logs = json.load(file)
            except json.JSONDecodeError:
                logs = []
    else:
        logs = []

    # Append new log entry
    logs.append(log_entry.dict())

    # Validate JSON before saving
    if not validate_json(logs):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid log data. Cannot save."
        )

    # Save logs back to file
    with open(log_file_path, "w") as file:
        json.dump(logs, file, indent=4)

    return {"success": "Log saved successfully"}
