import argparse
import json
import os
from copy import deepcopy
from datetime import datetime, timezone


PROJECTS = [
    ("Apache", "HDFS", "Hadoop HDFS"),
    ("Apache", "TIKA", "Apache Tika"),
    ("Apache", "LUCENE", "Apache Lucene"),
    ("Apache", "JCLOUDS", "Apache jclouds"),
    ("Apache", "MAPREDUCE", "Apache MapReduce"),
    ("Apache", "YARN", "Apache YARN"),
]

MODEL_ID = "648ee4526b3fde4b1b33e099"
VERSION_ID = "648f1f6f6b3fde4b1b3429cf"
DEFAULT_REPO = "Apache"
DEFAULT_PROJECT = "HDFS"

HDFS_COMPONENT_TASKS = [
    "Component DataNode",
    "Component NameNode",
    "Component DiskBalancer",
    "Component BlockManagement",
    "Component Tools",
    "Component Qjournal",
]
HDFS_REQUIREMENT_TASKS = [
    "Requirement File Permissions and Security",
    "Requirement Recoverability",
    "Requirement Scalability",
    "Requirement Rack Awareness",
    "Requirement Safe Mode",
    "Requirement Upgrade and Rollback",
]
HDFS_TEST_TASKS = [
    "Test Task A - DataNode Overview",
    "Test Task B - HDFS Security",
    "Test Task C - Scalability",
]

PROJECT_TASK_CATALOGS = {
    "LUCENE": {
        "components": [
            {
                "name": "Component IndexWriter",
                "focus": "the indexing pipeline, commit flow, and segment lifecycle in IndexWriter",
                "keywords": ["IndexWriter", "segments", "flush", "commit", "merge"],
            },
            {
                "name": "Component Query Parser",
                "focus": "how Query Parser turns user syntax into executable search structures",
                "keywords": ["QueryParser", "syntax", "parser", "query", "analysis"],
            },
            {
                "name": "Component Merge Policy",
                "focus": "how Lucene selects, schedules, and applies segment merges",
                "keywords": ["MergePolicy", "segments", "merge", "tiered", "performance"],
            },
            {
                "name": "Component Block Join",
                "focus": "how Lucene models and queries relationships across grouped documents",
                "keywords": ["BlockJoin", "documents", "parent", "child", "query"],
            },
            {
                "name": "Component Analyzer Pipeline",
                "focus": "how analyzers, token filters, and normalization steps shape indexing and search behavior",
                "keywords": ["Analyzer", "tokenizer", "filters", "stemming", "normalization"],
            },
            {
                "name": "Component Replication",
                "focus": "how Lucene replicates index files and coordinates index distribution",
                "keywords": ["replication", "NRT", "files", "copy", "distribution"],
            },
        ],
        "requirements": [
            {
                "name": "Requirement Index Integrity and Security",
                "focus": "index integrity, corruption handling, and safe file access are critical requirements in Apache Lucene.",
                "keywords": ["integrity", "corruption", "checksums", "locking", "security"],
            },
            {
                "name": "Requirement Recoverability",
                "focus": "recoverability after failed writes or partial commits is an important requirement in Apache Lucene.",
                "keywords": ["recoverability", "commit", "rollback", "crash", "durability"],
            },
            {
                "name": "Requirement Scalability",
                "focus": "scalability for large indexes and high query throughput is a key requirement in Apache Lucene.",
                "keywords": ["scalability", "large index", "throughput", "performance", "segments"],
            },
            {
                "name": "Requirement Near-Real-Time Search",
                "focus": "near-real-time search freshness is an important requirement in Apache Lucene.",
                "keywords": ["NRT", "reopen", "refresh", "latency", "searcher"],
            },
            {
                "name": "Requirement Query Safety",
                "focus": "safe handling of complex or malformed queries is a core requirement in Apache Lucene.",
                "keywords": ["query safety", "parser", "escaping", "limits", "robustness"],
            },
            {
                "name": "Requirement Backward Compatibility",
                "focus": "backward compatibility across index formats and upgrades is a recurring requirement in Apache Lucene.",
                "keywords": ["backward compatibility", "codec", "upgrade", "format", "migration"],
            },
        ],
        "tests": [
            {
                "name": "Test Task A - IndexWriter Overview",
                "focus": "the IndexWriter component",
                "question1": "TEST: What are the main components and responsibilities of IndexWriter?",
                "question2": "TEST: Which quality attributes matter most for IndexWriter?",
                "keywords": ["IndexWriter", "architecture", "components", "quality"],
            },
            {
                "name": "Test Task B - Lucene Query Safety",
                "focus": "query parsing and defensive handling in Lucene",
                "question1": "TEST: Which architectural elements handle query parsing and validation in Lucene?",
                "question2": "TEST: Which quality attributes matter for safe query handling in Lucene?",
                "keywords": ["Lucene", "query parser", "validation", "security", "robustness"],
            },
            {
                "name": "Test Task C - Search Scalability",
                "focus": "Lucene scalability mechanisms",
                "question1": "TEST: Which architectural elements support Lucene scalability?",
                "question2": "TEST: Which quality attributes matter for Lucene scalability?",
                "keywords": ["Lucene", "scalability", "segments", "throughput", "performance"],
            },
        ],
    },
    "TIKA": {
        "components": [
            {
                "name": "Component AutoDetectParser",
                "focus": "how AutoDetectParser coordinates detection, parser selection, and extraction flow",
                "keywords": ["AutoDetectParser", "detection", "parser", "metadata", "extraction"],
            },
            {
                "name": "Component MIME Detection",
                "focus": "how Tika detects content types from file signatures, metadata, and parser hints",
                "keywords": ["MIME", "detection", "magic", "media type", "metadata"],
            },
            {
                "name": "Component OCR Integration",
                "focus": "how Tika invokes OCR tools and integrates extracted text back into the pipeline",
                "keywords": ["OCR", "Tesseract", "integration", "text extraction", "pipeline"],
            },
            {
                "name": "Component Recursive Metadata Parser",
                "focus": "how Tika extracts nested documents and aggregates metadata across embedded resources",
                "keywords": ["recursive parser", "embedded", "metadata", "containers", "documents"],
            },
            {
                "name": "Component Parser Framework",
                "focus": "how parser interfaces, delegation, and fallback strategies are organized",
                "keywords": ["parser framework", "delegation", "fallback", "interfaces", "dispatch"],
            },
            {
                "name": "Component Content Handlers",
                "focus": "how content handlers stream, filter, and post-process extracted content",
                "keywords": ["content handler", "SAX", "streaming", "filtering", "output"],
            },
        ],
        "requirements": [
            {
                "name": "Requirement Safe Parsing and Security",
                "focus": "safe parsing of untrusted documents is a central requirement in Apache Tika.",
                "keywords": ["safe parsing", "security", "sandbox", "limits", "untrusted"],
            },
            {
                "name": "Requirement Recoverability",
                "focus": "recoverability from parser failures and malformed content is an important requirement in Apache Tika.",
                "keywords": ["recoverability", "malformed", "exceptions", "fallback", "robustness"],
            },
            {
                "name": "Requirement Scalability",
                "focus": "scalability for large document sets and memory-efficient extraction is a key requirement in Apache Tika.",
                "keywords": ["scalability", "batch extraction", "streaming", "memory", "throughput"],
            },
            {
                "name": "Requirement Extensibility",
                "focus": "extensibility for adding new parsers and detectors is a recurring requirement in Apache Tika.",
                "keywords": ["extensibility", "parser plugins", "detectors", "modularity", "registry"],
            },
            {
                "name": "Requirement Detection Accuracy",
                "focus": "accurate content type detection is a core requirement in Apache Tika.",
                "keywords": ["detection accuracy", "MIME", "heuristics", "metadata", "signatures"],
            },
            {
                "name": "Requirement Upgrade Compatibility",
                "focus": "compatible upgrades across parser dependencies and extraction behavior are an important requirement in Apache Tika.",
                "keywords": ["upgrade", "compatibility", "dependencies", "behavior", "migration"],
            },
        ],
        "tests": [
            {
                "name": "Test Task A - AutoDetectParser Overview",
                "focus": "the AutoDetectParser component",
                "question1": "TEST: What are the main components and responsibilities of AutoDetectParser?",
                "question2": "TEST: Which quality attributes matter for AutoDetectParser?",
                "keywords": ["AutoDetectParser", "architecture", "components", "quality"],
            },
            {
                "name": "Test Task B - Tika Security",
                "focus": "safe parsing in Tika",
                "question1": "TEST: Which architectural elements support safe parsing in Tika?",
                "question2": "TEST: Which quality attributes matter for Tika security and robustness?",
                "keywords": ["Tika", "security", "safe parsing", "sandbox", "robustness"],
            },
            {
                "name": "Test Task C - Extraction Scalability",
                "focus": "Tika scalability mechanisms",
                "question1": "TEST: Which architectural elements support scalable content extraction in Tika?",
                "question2": "TEST: Which quality attributes matter for scalable extraction in Tika?",
                "keywords": ["Tika", "scalability", "streaming", "memory", "throughput"],
            },
        ],
    },
    "JCLOUDS": {
        "components": [
            {
                "name": "Component BlobStore API",
                "focus": "how BlobStore presents a portable storage abstraction across providers",
                "keywords": ["BlobStore", "storage", "portable API", "provider", "object store"],
            },
            {
                "name": "Component ComputeService",
                "focus": "how ComputeService models machine lifecycle operations across cloud providers",
                "keywords": ["ComputeService", "instances", "provisioning", "portable API", "cloud"],
            },
            {
                "name": "Component Retry and Backoff",
                "focus": "how jclouds structures retry policies, fallback handlers, and error recovery",
                "keywords": ["retry", "backoff", "fallback", "errors", "robustness"],
            },
            {
                "name": "Component Provider Metadata",
                "focus": "how provider capabilities, defaults, and API mappings are represented",
                "keywords": ["provider metadata", "capabilities", "API mapping", "defaults", "metadata"],
            },
            {
                "name": "Component Authentication",
                "focus": "how jclouds handles credential acquisition, signing, and request authentication",
                "keywords": ["authentication", "credentials", "signing", "security", "identity"],
            },
            {
                "name": "Component Endpoint Resolution",
                "focus": "how jclouds resolves providers, regions, and endpoints across deployments",
                "keywords": ["endpoint", "region", "provider", "resolution", "location"],
            },
        ],
        "requirements": [
            {
                "name": "Requirement Credential Security",
                "focus": "credential security and request signing are central requirements in Apache jclouds.",
                "keywords": ["credential security", "signing", "secrets", "authentication", "access"],
            },
            {
                "name": "Requirement Recoverability",
                "focus": "recoverability from provider errors, timeouts, and partial failures is an important requirement in Apache jclouds.",
                "keywords": ["recoverability", "timeouts", "retry", "provider failure", "fallback"],
            },
            {
                "name": "Requirement Scalability",
                "focus": "scalability across large cloud resource sets and concurrent API calls is a key requirement in Apache jclouds.",
                "keywords": ["scalability", "parallel calls", "cloud resources", "throughput", "concurrency"],
            },
            {
                "name": "Requirement Provider Portability",
                "focus": "provider portability across clouds is a defining requirement in Apache jclouds.",
                "keywords": ["portability", "multi-cloud", "abstraction", "provider differences", "compatibility"],
            },
            {
                "name": "Requirement Safe Defaults",
                "focus": "safe default behavior across providers is an important requirement in Apache jclouds.",
                "keywords": ["safe defaults", "provider differences", "validation", "guardrails", "consistency"],
            },
            {
                "name": "Requirement Upgrade Compatibility",
                "focus": "upgrade compatibility across providers and API revisions is a recurring requirement in Apache jclouds.",
                "keywords": ["upgrade", "compatibility", "API version", "provider changes", "migration"],
            },
        ],
        "tests": [
            {
                "name": "Test Task A - BlobStore Overview",
                "focus": "the BlobStore component",
                "question1": "TEST: What are the main components and responsibilities of BlobStore?",
                "question2": "TEST: Which quality attributes matter for BlobStore portability?",
                "keywords": ["BlobStore", "architecture", "portability", "components", "quality"],
            },
            {
                "name": "Test Task B - jclouds Security",
                "focus": "credential handling in jclouds",
                "question1": "TEST: Which architectural elements support credential handling and secure requests in jclouds?",
                "question2": "TEST: Which quality attributes matter for jclouds security?",
                "keywords": ["jclouds", "security", "credentials", "authentication", "signing"],
            },
            {
                "name": "Test Task C - Multi-Cloud Scalability",
                "focus": "jclouds scalability mechanisms",
                "question1": "TEST: Which architectural elements support scalable multi-cloud operations in jclouds?",
                "question2": "TEST: Which quality attributes matter for scalability in jclouds?",
                "keywords": ["jclouds", "scalability", "multi-cloud", "throughput", "concurrency"],
            },
        ],
    },
    "MAPREDUCE": {
        "components": [
            {
                "name": "Component ApplicationMaster",
                "focus": "how the MapReduce ApplicationMaster coordinates jobs, tasks, and retries",
                "keywords": ["ApplicationMaster", "job lifecycle", "task coordination", "retry", "scheduling"],
            },
            {
                "name": "Component InputFormat",
                "focus": "how InputFormat and RecordReader partition data and expose records to tasks",
                "keywords": ["InputFormat", "RecordReader", "splits", "input", "tasks"],
            },
            {
                "name": "Component Shuffle and Sort",
                "focus": "how MapReduce moves intermediate data and organizes it for reducers",
                "keywords": ["shuffle", "sort", "intermediate data", "reducers", "network"],
            },
            {
                "name": "Component OutputCommitter",
                "focus": "how OutputCommitter handles atomic output publication and cleanup",
                "keywords": ["OutputCommitter", "commit", "atomic output", "cleanup", "failure"],
            },
            {
                "name": "Component Speculative Execution",
                "focus": "how speculative execution detects stragglers and launches backup attempts",
                "keywords": ["speculative execution", "stragglers", "backup tasks", "performance", "heuristics"],
            },
            {
                "name": "Component TaskAttempt",
                "focus": "how task attempts are tracked, retried, and isolated during execution",
                "keywords": ["TaskAttempt", "retry", "execution", "failure", "state"],
            },
        ],
        "requirements": [
            {
                "name": "Requirement Output Security and Integrity",
                "focus": "output integrity and safe publication are central requirements in Apache MapReduce.",
                "keywords": ["integrity", "output", "commit", "security", "consistency"],
            },
            {
                "name": "Requirement Recoverability",
                "focus": "recoverability from task, node, and job failures is a major requirement in Apache MapReduce.",
                "keywords": ["recoverability", "failure", "retry", "fault tolerance", "job recovery"],
            },
            {
                "name": "Requirement Scalability",
                "focus": "scalability across large clusters and large input datasets is a key requirement in Apache MapReduce.",
                "keywords": ["scalability", "cluster", "parallelism", "large dataset", "throughput"],
            },
            {
                "name": "Requirement Data Locality",
                "focus": "data locality is an important requirement in Apache MapReduce.",
                "keywords": ["data locality", "scheduling", "placement", "network", "performance"],
            },
            {
                "name": "Requirement Safe Execution",
                "focus": "safe execution of user jobs and task isolation are core requirements in Apache MapReduce.",
                "keywords": ["safe execution", "isolation", "sandbox", "user jobs", "robustness"],
            },
            {
                "name": "Requirement Upgrade Compatibility",
                "focus": "upgrade compatibility across job APIs and cluster behavior is an important requirement in Apache MapReduce.",
                "keywords": ["upgrade", "compatibility", "API", "behavior", "migration"],
            },
        ],
        "tests": [
            {
                "name": "Test Task A - ApplicationMaster Overview",
                "focus": "the ApplicationMaster component",
                "question1": "TEST: What are the main components and responsibilities of the MapReduce ApplicationMaster?",
                "question2": "TEST: Which quality attributes matter for the ApplicationMaster?",
                "keywords": ["ApplicationMaster", "architecture", "components", "quality"],
            },
            {
                "name": "Test Task B - MapReduce Reliability",
                "focus": "failure handling in MapReduce",
                "question1": "TEST: Which architectural elements support failure handling in MapReduce?",
                "question2": "TEST: Which quality attributes matter for MapReduce reliability?",
                "keywords": ["MapReduce", "reliability", "failure", "retry", "fault tolerance"],
            },
            {
                "name": "Test Task C - Job Scalability",
                "focus": "MapReduce scalability mechanisms",
                "question1": "TEST: Which architectural elements support scalability in MapReduce?",
                "question2": "TEST: Which quality attributes matter for MapReduce scalability?",
                "keywords": ["MapReduce", "scalability", "parallelism", "throughput", "cluster"],
            },
        ],
    },
    "YARN": {
        "components": [
            {
                "name": "Component ResourceManager",
                "focus": "how the ResourceManager coordinates cluster-wide scheduling and allocation",
                "keywords": ["ResourceManager", "scheduling", "allocation", "cluster", "resources"],
            },
            {
                "name": "Component NodeManager",
                "focus": "how the NodeManager launches, monitors, and reports container execution",
                "keywords": ["NodeManager", "containers", "monitoring", "node", "execution"],
            },
            {
                "name": "Component Capacity Scheduler",
                "focus": "how the Capacity Scheduler organizes queues, quotas, and placement decisions",
                "keywords": ["Capacity Scheduler", "queues", "capacity", "placement", "multi-tenant"],
            },
            {
                "name": "Component Log Aggregation",
                "focus": "how YARN collects and serves container logs across the cluster",
                "keywords": ["log aggregation", "logs", "containers", "storage", "diagnostics"],
            },
            {
                "name": "Component Federation",
                "focus": "how YARN federation splits and coordinates large clusters",
                "keywords": ["federation", "subclusters", "routing", "scalability", "coordination"],
            },
            {
                "name": "Component ApplicationMaster",
                "focus": "how an ApplicationMaster negotiates resources and orchestrates an application",
                "keywords": ["ApplicationMaster", "resource negotiation", "containers", "orchestration", "application"],
            },
        ],
        "requirements": [
            {
                "name": "Requirement Resource Isolation and Security",
                "focus": "resource isolation and secure multi-tenant execution are central requirements in Apache YARN.",
                "keywords": ["resource isolation", "security", "containers", "multi-tenant", "limits"],
            },
            {
                "name": "Requirement Recoverability",
                "focus": "recoverability from manager and application failures is an important requirement in Apache YARN.",
                "keywords": ["recoverability", "HA", "failover", "restart", "resilience"],
            },
            {
                "name": "Requirement Scalability",
                "focus": "scalability across very large clusters is a key requirement in Apache YARN.",
                "keywords": ["scalability", "large cluster", "federation", "throughput", "resources"],
            },
            {
                "name": "Requirement Multi-Tenancy",
                "focus": "multi-tenancy and queue fairness are important requirements in Apache YARN.",
                "keywords": ["multi-tenancy", "queues", "fairness", "capacity", "sharing"],
            },
            {
                "name": "Requirement Safe Rolling Upgrade",
                "focus": "safe rolling upgrades are an important operational requirement in Apache YARN.",
                "keywords": ["rolling upgrade", "safe mode", "compatibility", "restart", "operations"],
            },
            {
                "name": "Requirement Scheduling Compatibility",
                "focus": "compatibility across scheduling policies and cluster evolution is a recurring requirement in Apache YARN.",
                "keywords": ["scheduler compatibility", "policies", "evolution", "migration", "compatibility"],
            },
        ],
        "tests": [
            {
                "name": "Test Task A - ResourceManager Overview",
                "focus": "the ResourceManager component",
                "question1": "TEST: What are the main components and responsibilities of the ResourceManager?",
                "question2": "TEST: Which quality attributes matter for the ResourceManager?",
                "keywords": ["ResourceManager", "architecture", "components", "quality"],
            },
            {
                "name": "Test Task B - YARN Isolation",
                "focus": "resource isolation in YARN",
                "question1": "TEST: Which architectural elements support resource isolation and safe execution in YARN?",
                "question2": "TEST: Which quality attributes matter for YARN isolation and security?",
                "keywords": ["YARN", "isolation", "security", "containers", "multi-tenant"],
            },
            {
                "name": "Test Task C - Cluster Scalability",
                "focus": "YARN scalability mechanisms",
                "question1": "TEST: Which architectural elements support scalability in YARN?",
                "question2": "TEST: Which quality attributes matter for YARN scalability?",
                "keywords": ["YARN", "scalability", "federation", "cluster", "throughput"],
            },
        ],
    },
}


def _default_project_name(repo: str, project: str) -> str:
    return f"{repo} {project}".strip()


def _canonical_task_name(task_name: str) -> str:
    if "] " in task_name:
        return task_name.split("] ", 1)[1]
    return task_name


def _design_decision(question_type: str) -> dict:
    if question_type == "existence":
        return {"existence": True}
    if question_type == "property":
        return {"property": True}
    if question_type == "executive":
        return {"executive": True}
    return {}


def _build_component_task(project_name: str, component: dict) -> dict:
    name = component["name"].replace("Component ", "")
    focus = component["focus"]
    return {
        "description": (
            f"As a developer working on {project_name}, your task is to understand the design decisions "
            f"behind the {name} component. You want to study {focus} and understand the underlying "
            f"architectural structure, tradeoffs, and implementation choices."
        ),
        "questions": {
            "question1": {
                "type": "existence",
                "description": (
                    f"What are the components and connectors of {name}, and what rationale is given "
                    f"for those architectural choices?"
                ),
                "design_decision": _design_decision("existence"),
            },
            "question2": {
                "type": "property",
                "description": f"Which quality attributes are considered in the design of {name}?",
                "design_decision": _design_decision("property"),
            },
            "question3": {
                "type": "property",
                "description": (
                    f"What architectural tactics or patterns are used in {name} to satisfy those quality attributes?"
                ),
                "design_decision": _design_decision("property"),
            },
            "question4": {
                "type": "executive",
                "description": (
                    f"Which technologies, libraries, or mechanisms are used in {name}, and what rationale "
                    f"is given for selecting them?"
                ),
                "design_decision": _design_decision("executive"),
            },
        },
    }


def _build_requirement_task(project_name: str, requirement: dict) -> dict:
    name = requirement["name"].replace("Requirement ", "")
    focus = requirement["focus"]
    return {
        "description": (
            f"{focus} Your task is to explore the architectural decisions that {project_name} uses "
            f"to address {name}."
        ),
        "questions": {
            "question1": {
                "type": "existence",
                "description": (
                    f"What are the architectural components and connectors in {project_name} that are "
                    f"responsible for {name}?"
                ),
                "design_decision": _design_decision("existence"),
            },
            "question2": {
                "type": "property",
                "description": (
                    f"What architectural tactics or patterns are used in {project_name} to implement {name}?"
                ),
                "design_decision": _design_decision("property"),
            },
            "question3": {
                "type": "executive",
                "description": (
                    f"Which technologies, libraries, or mechanisms are integrated into {project_name} "
                    f"to achieve {name}?"
                ),
                "design_decision": _design_decision("executive"),
            },
        },
    }


def _build_test_task(project_name: str, test_task: dict) -> dict:
    return {
        "description": (
            f"TEST TASK: This is a test task for system validation. Explore {test_task['focus']} "
            f"in {project_name}."
        ),
        "questions": {
            "question1": {
                "type": "existence",
                "description": test_task["question1"],
                "design_decision": _design_decision("existence"),
            },
            "question2": {
                "type": "property",
                "description": test_task["question2"],
                "design_decision": _design_decision("property"),
            },
        },
    }


def _build_project_task_details(project: str, project_name: str, instructions: dict) -> dict:
    catalog = PROJECT_TASK_CATALOGS[project]
    task_details = {
        "task_details": instructions.get("task_details"),
        "Likert Scale": instructions.get("Likert Scale"),
    }

    for component in catalog["components"]:
        task_details[component["name"]] = _build_component_task(project_name, component)
    for requirement in catalog["requirements"]:
        task_details[requirement["name"]] = _build_requirement_task(project_name, requirement)
    for test_task in catalog["tests"]:
        task_details[test_task["name"]] = _build_test_task(project_name, test_task)

    return task_details


def _build_project_task_mapping(project: str) -> dict:
    catalog = PROJECT_TASK_CATALOGS[project]
    mapping = {}
    mapping.update(dict(zip(HDFS_COMPONENT_TASKS, [item["name"] for item in catalog["components"]])))
    mapping.update(dict(zip(HDFS_REQUIREMENT_TASKS, [item["name"] for item in catalog["requirements"]])))
    mapping.update(dict(zip(HDFS_TEST_TASKS, [item["name"] for item in catalog["tests"]])))
    return mapping


def _question_query(project: str, task_name: str, question: dict, keywords: list[str]) -> str:
    question_type = question.get("type", "existence")
    type_suffix = {
        "existence": "architecture components connectors rationale",
        "property": "quality attributes tactics patterns tradeoffs",
        "executive": "technologies libraries mechanisms implementation rationale",
    }.get(question_type, "architecture rationale")
    return " ".join([project, task_name, *keywords, type_suffix])


def _build_predictions(question: dict, rerank_engine: bool) -> dict:
    design_decision = question.get("design_decision", {})
    if not rerank_engine:
        return {
            "existence": None,
            "executive": None,
            "property": None,
        }
    return {
        "existence": design_decision.get("existence"),
        "executive": design_decision.get("executive"),
        "property": design_decision.get("property"),
    }


def _load_hdfs_template(base_dir: str) -> dict:
    candidate_paths = [
        os.path.join(base_dir, "experiment_configs", "Apache", "HDFS", "experiment_data.json"),
        os.path.join(base_dir, "experiment_data.json"),
    ]
    for path in candidate_paths:
        if os.path.exists(path):
            with open(path, "r") as handle:
                return json.load(handle)
    raise FileNotFoundError("Unable to locate the real HDFS experiment_data.json template")


def _task_keywords(project: str, task_name: str) -> list[str]:
    if project == "HDFS":
        parts = task_name.replace(" - ", " ").replace("Component ", "").replace("Requirement ", "").split()
        return parts[:5]

    catalog = PROJECT_TASK_CATALOGS[project]
    for section in ("components", "requirements", "tests"):
        for item in catalog[section]:
            if item["name"] == task_name:
                return item["keywords"]
    return task_name.split()[:5]


def _build_project_queries(
    repo: str,
    project: str,
    project_name: str,
    task_details: dict,
) -> dict:
    query_tasks = {}
    for task_name, task in task_details.items():
        if task_name in {"task_details", "Likert Scale"}:
            continue
        keywords = _task_keywords(project, task_name)
        query_task = {
            "repo": repo,
            "project": project,
            "project_name": project_name,
            "questions": {},
        }
        for qkey, question in task.get("questions", {}).items():
            query = _question_query(project, task_name, question, keywords)
            query_task["questions"][qkey] = {
                "query": query,
                "archrag_request": {
                    "repo": repo,
                    "project": project,
                    "query": query,
                    "num_results": 10,
                },
                "pylucene_request": {
                    "database_url": "http://issues-db-api:8000",
                    "model_id": MODEL_ID,
                    "version_id": VERSION_ID,
                    "repos_and_projects": {repo: [project]},
                    "query": query,
                    "num_results": 10,
                    "predictions": _build_predictions(question, False),
                },
                "pylucene_rerank_request": {
                    "database_url": "http://issues-db-api:8000",
                    "model_id": MODEL_ID,
                    "version_id": VERSION_ID,
                    "repos_and_projects": {repo: [project]},
                    "query": query,
                    "num_results": 10,
                    "predictions": _build_predictions(question, True),
                },
            }
        query_tasks[task_name] = query_task
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": repo,
        "project": project,
        "project_name": project_name,
        "model_id": MODEL_ID,
        "version_id": VERSION_ID,
        "tasks": query_tasks,
    }


def _build_mock_student_data(project: str, project_name: str, hdfs_template: dict) -> tuple[dict, dict]:
    task_mapping = _build_project_task_mapping(project)
    student_data = {}
    passwords = {}

    template_students = list(hdfs_template.get("student_data", {}).items())
    for index, (_, template_student) in enumerate(template_students, start=1):
        student_id = f"mock_{project.lower()}_{index:03d}"
        passwords[student_id] = student_id

        tasks = []
        for template_task in template_student.get("tasks", []):
            mapped_name = task_mapping[template_task["taskName"]]
            tasks.append({
                "taskName": mapped_name,
                "repo": "Apache",
                "project": project,
                "project_name": project_name,
                "solutions": {},
                "questions": deepcopy(template_task.get("questions", {})),
            })
        student_data[student_id] = {"tasks": tasks}

    return student_data, passwords


def main():
    parser = argparse.ArgumentParser(description="Generate per-project mock experiment configs.")
    parser.add_argument(
        "--tasks-path",
        default=os.path.join(os.path.dirname(__file__), "experiment_tasks.json"),
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "mock_experiments"),
    )
    parser.add_argument(
        "--project-configs-dir",
        default=os.path.join(os.path.dirname(__file__), "experiment_configs"),
    )
    args = parser.parse_args()

    with open(args.tasks_path, "r") as handle:
        instructions = json.load(handle)

    hdfs_template = _load_hdfs_template(os.path.dirname(__file__))

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(args.project_configs_dir, exist_ok=True)

    generated_tasks = {
        "task_details": instructions.get("task_details"),
        "Likert Scale": instructions.get("Likert Scale"),
    }
    generated_queries = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_id": MODEL_ID,
        "version_id": VERSION_ID,
        "tasks": {},
    }
    generated_data = {
        "debug": True,
        "passwords": {},
        "student_data": {},
        "task_details": generated_tasks,
    }

    for repo, project, project_name in PROJECTS:
        project_dir = os.path.join(args.project_configs_dir, repo, project)
        os.makedirs(project_dir, exist_ok=True)
        project_data_path = os.path.join(project_dir, "experiment_data.json")
        project_queries_path = os.path.join(project_dir, "experiment_queries.json")

        if repo == DEFAULT_REPO and project == DEFAULT_PROJECT:
            project_payload = deepcopy(hdfs_template)
            project_payload["repo"] = repo
            project_payload["project"] = project
            project_payload["project_name"] = project_name
            task_details = project_payload["task_details"]
        else:
            task_details = _build_project_task_details(project, project_name, instructions)
            student_data, passwords = _build_mock_student_data(project, project_name, hdfs_template)
            project_payload = {
                "debug": True,
                "repo": repo,
                "project": project,
                "project_name": project_name,
                "passwords": passwords,
                "student_data": student_data,
                "task_details": task_details,
            }
            generated_data["passwords"].update(passwords)
            generated_data["student_data"].update(student_data)

        project_queries = _build_project_queries(repo, project, project_name, task_details)

        with open(project_data_path, "w") as handle:
            json.dump(project_payload, handle, indent=2)
        with open(project_queries_path, "w") as handle:
            json.dump(project_queries, handle, indent=2)

        for task_name, task in task_details.items():
            if task_name in {"task_details", "Likert Scale"}:
                continue
            prefixed_name = f"[{project}] {_canonical_task_name(task_name)}"
            task_copy = deepcopy(task)
            task_copy["repo"] = repo
            task_copy["project"] = project
            task_copy["project_name"] = project_name
            for question in task_copy.get("questions", {}).values():
                question["repo"] = repo
                question["project"] = project
                question["project_name"] = project_name
            generated_tasks[prefixed_name] = task_copy
            generated_queries["tasks"][prefixed_name] = deepcopy(project_queries["tasks"][task_name])

    with open(os.path.join(args.output_dir, "experiment_tasks.mock_multi_project.json"), "w") as handle:
        json.dump(generated_tasks, handle, indent=2)
    with open(os.path.join(args.output_dir, "experiment_data.mock_multi_project.json"), "w") as handle:
        json.dump(generated_data, handle, indent=2)
    with open(os.path.join(args.output_dir, "experiment_queries.mock_multi_project.json"), "w") as handle:
        json.dump(generated_queries, handle, indent=2)

    print(f"Generated project configs in {args.project_configs_dir}")


if __name__ == "__main__":
    main()
