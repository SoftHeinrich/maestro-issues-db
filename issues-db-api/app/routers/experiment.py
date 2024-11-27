import json
import os
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Any, Dict

router = APIRouter(tags=["experiment"])


class MtrNo(BaseModel):
    MtrNo: str


class SaveResult(BaseModel):
    matriculationNumber: str
    taskId: str
    questionKey: str
    searchQuery: str
    ratings: Dict[str, str]


def load_experiment_data() -> Dict[str, Any]:
    # Get the directory of the current file and construct the path to experiment_data.json
    current_directory = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_directory, "..", "experiment_data.json")
    with open(file_path, "r") as file:
        return json.load(file)


def save_experiment_data(data: Dict[str, Any]) -> None:
    # Get the directory of the current file and construct the path to experiment_data.json
    current_directory = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_directory, "..", "experiment_data.json")
    with open(file_path, "w") as file:
        json.dump(data, file, indent=4)


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
            "solutions": task["solutions"]
        }

        # Find task details from the task_details section of the JSON
        task_details = data.get("task_details", {}).get(task_name)
        if task_details:
            task_info["description"] = task_details.get("description")
            task_info["questions"] = task_details.get("questions")
            task_info["task_details"] = task_details.get("task_details")
            task_info["lekert_scale"] = task_details.get("Likert Scale")

        response.append(task_info)

    return response


@router.post("/submit-ratings")
def save_result(result_data: SaveResult):
    data = load_experiment_data()

    # Get the student data section
    student_data = data.setdefault("student_data", {})
    matriculation_number = result_data.matriculationNumber

    # Ensure student exists in the data
    if matriculation_number not in student_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No student data found for Matriculation Number: {matriculation_number}"
        )
    
    
    student = student_data[matriculation_number]
    
    
    # Add the result to the solutions
    task_id = result_data.taskId
    question_key = result_data.questionKey
    search_query = result_data.searchQuery
    ratings = result_data.ratings

    solution = {
        "taskId": task_id,
        "questionKey": question_key,
        "searchQuery": search_query,
        "ratings": ratings
    }
    
    # Append the solution to the student's task solutions
    for task in student["tasks"]:
        # find the task
        if task["taskName"] == task_id:
            task["solutions"].setdefault(question_key,[]).append(solution)
            # task.setdefault("solutions", {}).append(solution)
            break

    

    # Save updated data back to the JSON file
    save_experiment_data(data)

    return {"message": "Result saved successfully"}
