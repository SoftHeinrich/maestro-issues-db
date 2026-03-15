# Setting Up Student Experiments

This guide explains how to create and run student experiments in Maestro. The experiment system lets students search for Architectural Design Decisions (ADDs) in HDFS issues using either PyLucene or archRag, and rate the relevance of results.

## Prerequisites

- All Maestro services running (`cd Maestro && ./setup_components.sh`)
- MongoDB restored with HDFS data and BERT model
- PyLucene index built (via Search page "Generate Index" button)
- OpenAI API key configured in `archRag/.env` (needed for GPT keyword extraction tasks)

## Concepts

### Task Structure

Each experiment is defined in `experiment_data.json` with:

- **Students** (`student_data`): Maps student IDs to their assigned tasks
- **Task definitions** (`task_details`): Describes each task, its questions, and Likert scale

### Task Types

Each task is assigned a search engine and optional modifiers:

| Field | Values | Description |
|-------|--------|-------------|
| `engine` | `"pylucene"` or `"archrag"` | Which search system the student uses |
| `rerank_engine` | `true`/`false` | Enable ADD-type prediction reranking (PyLucene only) |
| `gpt` | `true`/`false` | Use GPT-4 to extract keywords from the student's query before searching |

### Question Types

Questions map to ADD classification dimensions used for reranking:

| Type | `design_decision` | Description |
|------|-------------------|-------------|
| `existence` | `{"existence": true}` | Components and connectors |
| `property` | `{"property": true}` | Quality attributes and tactics |
| `executive` | `{"executive": true}` | Technologies and rationales |

### Experiment Flow

```
Student enters ID → Gets assigned tasks → For each task:
  → Reads task description and question
  → Enters search query (optionally processed by GPT-4)
  → Views 10 search results with comments
  → Rates each result on Likert scale (1-5)
  → Submits ratings (must rate all 10 results)
  → Repeats with at least 2 queries per question
```

## Step-by-Step Setup

### 1. Define Task Definitions

Task definitions describe the questions students will answer. These go in the `task_details` section of `experiment_data.json`.

Available tasks are defined in `experiment_tasks.json` (12 tasks, 42 questions total):

**Component tasks** (4 questions each):
- Component DataNode, NameNode, DiskBalancer, BlockManagement, Tools, Qjournal

**Requirement tasks** (3 questions each):
- Requirement File Permissions and Security, Recoverability, Scalability, Rack Awareness, Safe Mode, Upgrade and Rollback

You can use these directly or define custom tasks following the same format.

### 2. Create `experiment_data.json`

Edit the file at `maestro-issues-db/issues-db-api/app/experiment_data.json`:

```json
{
    "student_data": {
        "student001": {
            "tasks": [
                {
                    "taskName": "Component DataNode",
                    "engine": "pylucene",
                    "rerank_engine": true,
                    "gpt": false,
                    "solutions": {}
                },
                {
                    "taskName": "Component NameNode",
                    "engine": "archrag",
                    "rerank_engine": false,
                    "gpt": false,
                    "solutions": {}
                },
                {
                    "taskName": "Requirement Scalability",
                    "engine": "pylucene",
                    "rerank_engine": false,
                    "gpt": true,
                    "solutions": {}
                }
            ]
        },
        "student002": {
            "tasks": [
                {
                    "taskName": "Component DataNode",
                    "engine": "archrag",
                    "rerank_engine": false,
                    "gpt": false,
                    "solutions": {}
                },
                {
                    "taskName": "Component NameNode",
                    "engine": "pylucene",
                    "rerank_engine": true,
                    "gpt": false,
                    "solutions": {}
                }
            ]
        }
    },
    "task_details": {
        "Component DataNode": {
            "description": "Your task description here...",
            "questions": {
                "question1": {
                    "type": "existence",
                    "description": "What are the components and connectors of DataNode?",
                    "design_decision": {
                        "existence": true
                    }
                },
                "question2": {
                    "type": "property",
                    "description": "What quality attributes are considered in DataNode?",
                    "design_decision": {
                        "property": true
                    }
                }
            },
            "task_details": "Instructions:\n* Execute at least two queries per question.",
            "Likert Scale": {
                "5": "Very Relevant",
                "4": "Relevant",
                "3": "Distantly Relevant",
                "2": "Less Relevant",
                "1": "Not Relevant"
            }
        }
    }
}
```

### 3. Design the Experiment

For a **between-subjects** comparison (each student uses one system per task):

- Assign half the students `"engine": "pylucene"` and half `"engine": "archrag"` for the same task
- **Counterbalance**: Alternate engines across tasks per student

For a **within-subjects** comparison:

- Assign the same student the same task twice with different engines (not typical)
- Or use the MongoDB-based session system with `experiment_type: "dual"`

Typical assignment pattern for 4 tasks:

| Student | Task 1 | Task 2 | Task 3 | Task 4 |
|---------|--------|--------|--------|--------|
| Group A | pylucene | archrag | pylucene+gpt | archrag |
| Group B | archrag | pylucene | archrag | pylucene+gpt |

### 4. Populate from Toolkit Results

To create a fresh experiment from existing toolkit data (removing previous ratings):

```python
import json

# Load toolkit results
with open("maestro-toolkit/data_experiment/data13/experiment_data.json") as f:
    data = json.load(f)

# Clear all solutions (ratings) - keep task assignments
for student_id, student in data["student_data"].items():
    for task in student["tasks"]:
        task["solutions"] = {}

# Save as new experiment
with open("maestro-issues-db/issues-db-api/app/experiment_data.json", "w") as f:
    json.dump(data, f, indent=4)
```

### 5. Restart the API

```bash
cd maestro-issues-db && docker compose restart issues-db-api
```

The API reads `experiment_data.json` on each request, so a restart isn't strictly needed, but it ensures the file is accessible.

### 6. Verify Setup

Test that a student can fetch their tasks:

```bash
curl -s -X POST https://maestro.localhost:4269/issues-db-api/experiment/tasks \
  -H "Content-Type: application/json" \
  -d '{"MtrNo": "student001"}' | python3 -m json.tool
```

### 7. Students Access the Experiment

Students navigate to: `https://maestro.localhost:4269/archui/experiment`

1. Enter their student ID (matriculation number)
2. Click "Get Tasks"
3. Click "Attempt" next to each question
4. Search, rate results, submit

### 8. Collect Results

Results are saved back to `experiment_data.json` in the `solutions` field of each task. To export:

```bash
# Copy from container
docker cp issues-db-api:/python-docker/app/experiment_data.json ./results.json

# Or read directly (bind-mounted)
cat maestro-issues-db/issues-db-api/app/experiment_data.json
```

## File Reference

| File | Location | Purpose |
|------|----------|---------|
| `experiment_data.json` | `issues-db-api/app/` | Student assignments and collected ratings |
| `experiment_tasks.json` | `issues-db-api/app/` | Full task/question definitions (12 tasks) |
| `experiment.py` | `issues-db-api/app/routers/` | Backend API endpoints |
| `experiment.tsx` | `maestro-ArchUI/src/routes/` | Task listing UI |
| `experiment_search.tsx` | `maestro-ArchUI/src/routes/` | Search and rating UI |

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| "No experiment data found for MtrNo" | Student ID not in `experiment_data.json` | Add the student ID to `student_data` |
| "An error occurred while fetching search results" | GPT-4 API key missing or invalid | Set `OPENAI_API_KEY` in `archRag/.env` |
| "PyLucene index not built" | Index needs to be created first | Go to Search page, select model+project, click "Generate Index" |
| Search returns no results | Index doesn't cover the selected project | Rebuild index with Apache/HDFS selected |
| "Model was not found" | MongoDB missing BERT model data | Restore from `mongodump-MiningDesignDecisions-lite.archive` |
