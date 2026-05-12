#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/.runtime"
LOG_FILE="$LOG_DIR/followup_comment_backfills.log"
QUERY="with eligible as (select split_part(issue_id,'-',1) as project, count(*) as eligible from issues_comments where is_bot = false and length(body) > 200 group by 1), classified as (select split_part(ic.issue_id,'-',1) as project, count(*) as classified from classification_results cr join issues_comments ic on ic.id = cr.issue_comment_id where ic.is_bot = false and length(ic.body) > 200 group by 1) select (e.eligible - coalesce(c.classified,0)) as remaining from eligible e left join classified c using(project) where e.project = '%s';"

mkdir -p "$LOG_DIR"

timestamp() {
  date '+%Y-%m-%d %H:%M:%S'
}

remaining_for_project() {
  local project="$1"
  docker exec psql psql -U postgres -d issues -At -c "$(printf "$QUERY" "$project")"
}

log_line() {
  local message="$1"
  printf '[%s] %s\n' "$(timestamp)" "$message" | tee -a "$LOG_FILE"
}

wait_for_project_completion() {
  local project="$1"
  local remaining
  remaining="$(remaining_for_project "$project")"
  while [[ "$remaining" != "0" ]]; do
    log_line "$project remaining comments: $remaining"
    sleep 300
    remaining="$(remaining_for_project "$project")"
  done
  log_line "$project completed"
}

run_project() {
  local project="$1"
  local remaining
  remaining="$(remaining_for_project "$project")"
  if [[ "$remaining" == "0" ]]; then
    log_line "$project already complete"
    return
  fi

  log_line "starting $project classification"
  python3 "$ROOT_DIR/maestro-issues-db/run_project_comment_classification.py" \
    --project "$project" \
    --batch-size 500 | tee -a "$LOG_FILE"
  log_line "$project classification request finished"
}

log_line "waiting for LUCENE backfill to finish before follow-up projects"
wait_for_project_completion "LUCENE"
run_project "MAPREDUCE"
run_project "YARN"
log_line "follow-up backfills complete"
