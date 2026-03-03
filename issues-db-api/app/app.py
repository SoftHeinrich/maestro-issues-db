from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import (
    tags,
    issue_data,
    issue_ids,
    manual_labels,
    models,
    projects,
    issues,
    jirarepos_download,
    authentication,
    embeddings,
    ui,
    repos,
    statistics,
    bulk,
    files,
    experiment,
)
from .streaming import ui_updates
import uvicorn

app = FastAPI(root_path="/issues-db-api")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(authentication.router)
app.include_router(bulk.router)
app.include_router(embeddings.router)
app.include_router(files.router)
app.include_router(issue_data.router)
app.include_router(issue_ids.router)
app.include_router(issues.router)
app.include_router(jirarepos_download.router)
app.include_router(manual_labels.router)
app.include_router(models.router)
app.include_router(projects.router)
app.include_router(repos.router)
app.include_router(statistics.router)
app.include_router(tags.router)
app.include_router(ui.router)
app.include_router(ui_updates.router)
app.include_router(experiment.router)

def run_app():
    uvicorn.run(
        "app.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
