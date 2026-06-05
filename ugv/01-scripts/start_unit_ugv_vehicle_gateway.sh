#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ACTION="status"

WORKSPACE_DIR="${WORKSPACE_DIR:-$HOME/catkin_ws}"
ROS_SETUP="${ROS_SETUP:-/opt/ros/noetic/setup.bash}"
PLATFORM_ID="${PLATFORM_ID:-ugv_0}"
CAPABILITY="${CAPABILITY:-confirm_target}"
SERVICE_SYMBOL="${SERVICE_SYMBOL:-platform_gateway_msgs.srv:TaskCommandJson}"
TARGET_MAP="${UNIT_UGV_TARGET_MAP:-$HOME/changxin_gateway_runtime/unit_ugv_targets.json}"
PROGRESS_OUTPUT="${UNIT_UGV_PROGRESS_OUTPUT:-/tmp/changxin-task-progress.json}"
MOVE_BASE_ACTION="${UNIT_UGV_MOVE_BASE_ACTION:-/move_base}"
MAX_MOVE_BASE_DISTANCE_M="${UNIT_UGV_MAX_MOVE_BASE_DISTANCE_M:-0.6}"
NODE_NAME="${NODE_NAME:-changxin_unit_ugv_gateway}"
STATE_DIR="${UNIT_UGV_GATEWAY_STATE_DIR:-$HOME/changxin_gateway_runtime/gateway_state}"
EVIDENCE_DIR="${UNIT_UGV_EVIDENCE_DIR:-$HOME/changxin_gateway_runtime/evidence/runtime-probe-$(date +%Y%m%d_%H%M%S)}"
SERVICE_TIMEOUT_S="${UNIT_UGV_SERVICE_TIMEOUT_S:-20}"
MOVE_BASE_SERVER_TIMEOUT_S="${UNIT_UGV_MOVE_BASE_SERVER_TIMEOUT_S:-5.0}"
ECHO_TIMEOUT_S="${UNIT_UGV_ECHO_TIMEOUT_S:-5}"
TF_TIMEOUT_S="${UNIT_UGV_TF_TIMEOUT_S:-5}"
TAIL_LINES="${TAIL_LINES:-120}"
SELECT_OBJECT_QUERY="${SELECT_OBJECT_QUERY:-}"

SOURCE_ENV=1
OPERATOR_APPROVED=0
ENABLE_MOVE_BASE=0
REQUIRE_MOVE_BASE_SERVER=0
SKIP_ROS_MASTER_CHECK=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage:
  start_unit_ugv_vehicle_gateway.sh [action] [options]

Vehicle-side lifecycle controller for the single-UGV ROS1 platform gateway.
Codex is not required on the vehicle. Run this on the UGV IPC / vehicle-local
ROS computer, or invoke it remotely from the 4060 through SSH.

Actions:
  precheck       Validate repo, ROS env, target map, imports, and ROS master
  command        Print the exact wrapper command
  start          Start gateway wrapper without move_base enablement by default
  start-motion   Start wrapper with operator approval and move_base enabled
  stop           Stop the managed wrapper process
  restart        Stop, then start
  status         Print pid/log/state and service-registration status
  signature      Capture rosservice list/type/args evidence for gateway services
  runtime-probe  Run a read-only vehicle runtime probe for navigation debugging
  logs           Print the latest wrapper log lines

Options:
  --repo-dir DIR                  changxin-code checkout. Default: script repo root
  --workspace-dir DIR             Catkin workspace. Default: ~/catkin_ws
  --ros-setup FILE                ROS setup.bash. Default: /opt/ros/noetic/setup.bash
  --platform-id ID                Platform id. Default: ugv_0
  --target-map FILE               UnitUgvTargetMap.v1 JSON. Default: ~/changxin_gateway_runtime/unit_ugv_targets.json
  --select-object-query TEXT      Require target map to match this object query
  --progress-output FILE          TaskProgressSet.v1 output. Default: /tmp/changxin-task-progress.json
  --move-base-action NAME         move_base action name. Default: /move_base
  --max-move-base-distance-m M    Maximum allowed target-map radius. Default: 0.6
  --move-base-server-timeout-s S  move_base action wait timeout passed to wrapper. Default: 5.0
  --state-dir DIR                 Managed pid/log/state dir. Default: ~/changxin_gateway_runtime/gateway_state
  --evidence-dir DIR              Read-only runtime probe output dir
  --service-timeout-s S           Service registration wait timeout. Default: 20
  --echo-timeout-s S              rostopic echo timeout for runtime-probe. Default: 5
  --tf-timeout-s S                tf_echo timeout for runtime-probe. Default: 5
  --operator-approved             Record local operator approval for dispatch
  --enable-move-base              Allow move_base_goal target-map actions
  --require-move-base-server      Precheck should wait for a move_base action server
  --skip-ros-master-check         Do not require ROS master during precheck
  --dry-run                       Print commands without starting/stopping processes
  --no-source                     Do not source ROS/workspace setup files
  -h, --help                      Show this help

Safety:
  This script never sends a TaskCommand by itself. It only starts/stops the
  vehicle-side service wrapper. The 4060/HMI side must call dry_run or dispatch
  through /fleet/<platform_id>/gateway/*.
EOF
}

die() {
  echo "[ERR] $*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    precheck|command|start|start-motion|stop|restart|status|signature|runtime-probe|logs)
      ACTION="$1"
      shift
      ;;
    --repo-dir)
      [[ $# -ge 2 ]] || die "--repo-dir requires a value"
      REPO_DIR="$2"
      shift 2
      ;;
    --workspace-dir)
      [[ $# -ge 2 ]] || die "--workspace-dir requires a value"
      WORKSPACE_DIR="$2"
      shift 2
      ;;
    --ros-setup)
      [[ $# -ge 2 ]] || die "--ros-setup requires a value"
      ROS_SETUP="$2"
      shift 2
      ;;
    --platform-id)
      [[ $# -ge 2 ]] || die "--platform-id requires a value"
      PLATFORM_ID="$2"
      shift 2
      ;;
    --target-map)
      [[ $# -ge 2 ]] || die "--target-map requires a value"
      TARGET_MAP="$2"
      shift 2
      ;;
    --select-object-query)
      [[ $# -ge 2 ]] || die "--select-object-query requires a value"
      SELECT_OBJECT_QUERY="$2"
      shift 2
      ;;
    --progress-output)
      [[ $# -ge 2 ]] || die "--progress-output requires a value"
      PROGRESS_OUTPUT="$2"
      shift 2
      ;;
    --move-base-action)
      [[ $# -ge 2 ]] || die "--move-base-action requires a value"
      MOVE_BASE_ACTION="$2"
      shift 2
      ;;
    --max-move-base-distance-m)
      [[ $# -ge 2 ]] || die "--max-move-base-distance-m requires a value"
      MAX_MOVE_BASE_DISTANCE_M="$2"
      shift 2
      ;;
    --move-base-server-timeout-s)
      [[ $# -ge 2 ]] || die "--move-base-server-timeout-s requires a value"
      MOVE_BASE_SERVER_TIMEOUT_S="$2"
      shift 2
      ;;
    --state-dir)
      [[ $# -ge 2 ]] || die "--state-dir requires a value"
      STATE_DIR="$2"
      shift 2
      ;;
    --evidence-dir)
      [[ $# -ge 2 ]] || die "--evidence-dir requires a value"
      EVIDENCE_DIR="$2"
      shift 2
      ;;
    --service-timeout-s)
      [[ $# -ge 2 ]] || die "--service-timeout-s requires a value"
      SERVICE_TIMEOUT_S="$2"
      shift 2
      ;;
    --echo-timeout-s)
      [[ $# -ge 2 ]] || die "--echo-timeout-s requires a value"
      ECHO_TIMEOUT_S="$2"
      shift 2
      ;;
    --tf-timeout-s)
      [[ $# -ge 2 ]] || die "--tf-timeout-s requires a value"
      TF_TIMEOUT_S="$2"
      shift 2
      ;;
    --operator-approved)
      OPERATOR_APPROVED=1
      shift
      ;;
    --enable-move-base)
      ENABLE_MOVE_BASE=1
      shift
      ;;
    --require-move-base-server)
      REQUIRE_MOVE_BASE_SERVER=1
      shift
      ;;
    --skip-ros-master-check)
      SKIP_ROS_MASTER_CHECK=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --no-source)
      SOURCE_ENV=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option or action: $1"
      ;;
  esac
done

PID_FILE="$STATE_DIR/$PLATFORM_ID.gateway.pid"
LOG_FILE="$STATE_DIR/$PLATFORM_ID.gateway.log"
STATE_FILE="$STATE_DIR/$PLATFORM_ID.gateway.state.json"
COMMAND_FILE="$STATE_DIR/$PLATFORM_ID.gateway.command.txt"
ROS_LIST_FILE="$STATE_DIR/$PLATFORM_ID.rosservice-list.txt"
ROS_TYPE_FILE="$STATE_DIR/$PLATFORM_ID.rosservice-types.txt"
ROS_ARGS_FILE="$STATE_DIR/$PLATFORM_ID.rosservice-args.txt"
TARGET_CHECK_FILE="$STATE_DIR/$PLATFORM_ID.target-map-check.json"
DRY_RUN_SERVICE="/fleet/$PLATFORM_ID/gateway/dry_run"
DISPATCH_SERVICE="/fleet/$PLATFORM_ID/gateway/dispatch"

source_setup_file() {
  local setup_file="$1"
  set +e
  set +u
  # shellcheck disable=SC1090
  source "$setup_file"
  local rc=$?
  set -u
  set -e
  return "$rc"
}

source_env() {
  if (( SOURCE_ENV )); then
    [[ -f "$ROS_SETUP" ]] || die "ROS setup not found: $ROS_SETUP"
    source_setup_file "$ROS_SETUP" || die "failed to source ROS setup: $ROS_SETUP"
    if [[ -f "$WORKSPACE_DIR/devel/setup.bash" ]]; then
      source_setup_file "$WORKSPACE_DIR/devel/setup.bash" || die "failed to source workspace setup: $WORKSPACE_DIR/devel/setup.bash"
    fi
  fi
}

print_context() {
  cat <<EOF
script: $SCRIPT_NAME
action: $ACTION
repo_dir: $REPO_DIR
workspace_dir: $WORKSPACE_DIR
ros_setup: $ROS_SETUP
platform_id: $PLATFORM_ID
target_map: $TARGET_MAP
select_object_query: $SELECT_OBJECT_QUERY
progress_output: $PROGRESS_OUTPUT
move_base_action: $MOVE_BASE_ACTION
max_move_base_distance_m: $MAX_MOVE_BASE_DISTANCE_M
operator_approved: $OPERATOR_APPROVED
enable_move_base: $ENABLE_MOVE_BASE
require_move_base_server: $REQUIRE_MOVE_BASE_SERVER
state_dir: $STATE_DIR
evidence_dir: $EVIDENCE_DIR
ros_master_uri: ${ROS_MASTER_URI:-}
ros_ip: ${ROS_IP:-}
ros_hostname: ${ROS_HOSTNAME:-}
EOF
}

json_state() {
  local status="$1"
  local reason="${2:-}"
  mkdir -p "$STATE_DIR"
  STATE_STATUS="$status" \
  STATE_REASON="$reason" \
  STATE_FILE="$STATE_FILE" \
  PID_FILE="$PID_FILE" \
  LOG_FILE="$LOG_FILE" \
  COMMAND_FILE="$COMMAND_FILE" \
  PLATFORM_ID="$PLATFORM_ID" \
  TARGET_MAP="$TARGET_MAP" \
  PROGRESS_OUTPUT="$PROGRESS_OUTPUT" \
  DRY_RUN_SERVICE="$DRY_RUN_SERVICE" \
  DISPATCH_SERVICE="$DISPATCH_SERVICE" \
  OPERATOR_APPROVED="$OPERATOR_APPROVED" \
  ENABLE_MOVE_BASE="$ENABLE_MOVE_BASE" \
  python3 - <<'PY'
import json
import os
import socket
from datetime import datetime, timezone

pid = None
pid_file = os.environ["PID_FILE"]
if os.path.exists(pid_file):
    text = open(pid_file, encoding="utf-8").read().strip()
    pid = int(text) if text.isdigit() else None

data = {
    "schema": "UnitUgvVehicleGatewayLifecycleState.v1",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "host": socket.gethostname(),
    "status": os.environ["STATE_STATUS"],
    "reason": os.environ["STATE_REASON"],
    "platform_id": os.environ["PLATFORM_ID"],
    "pid": pid,
    "pid_file": pid_file,
    "log_file": os.environ["LOG_FILE"],
    "command_file": os.environ["COMMAND_FILE"],
    "target_map": os.environ["TARGET_MAP"],
    "progress_output": os.environ["PROGRESS_OUTPUT"],
    "dry_run_service": os.environ["DRY_RUN_SERVICE"],
    "dispatch_service": os.environ["DISPATCH_SERVICE"],
    "operator_approved": os.environ["OPERATOR_APPROVED"] == "1",
    "enable_move_base": os.environ["ENABLE_MOVE_BASE"] == "1",
}
with open(os.environ["STATE_FILE"], "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
    fh.write("\n")
PY
}

read_pid() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(tr -d '[:space:]' < "$PID_FILE")"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  echo "$pid"
}

is_running() {
  local pid
  pid="$(read_pid)" || return 1
  kill -0 "$pid" >/dev/null 2>&1
}

require_common_files() {
  [[ -d "$REPO_DIR" ]] || die "repo dir not found: $REPO_DIR"
  [[ -f "$REPO_DIR/tools/run_ros1_platform_gateway_node.py" ]] || die "wrapper tool missing under repo: $REPO_DIR"
  [[ -f "$REPO_DIR/tools/check_unit_ugv_target_map.py" ]] || die "target-map checker missing under repo: $REPO_DIR"
  [[ -f "$TARGET_MAP" ]] || die "target map not found: $TARGET_MAP"
}

check_imports() {
  PYTHONDONTWRITEBYTECODE=1 python3 - "$ENABLE_MOVE_BASE" <<'PY'
import importlib
import sys

enable_move_base = sys.argv[1] == "1"
required = [
    "rospy",
    "actionlib",
    "platform_gateway_msgs.srv",
]
if enable_move_base:
    required.append("move_base_msgs.msg")

for name in required:
    importlib.import_module(name)

print("vehicle gateway imports ok")
PY
}

check_target_map() {
  mkdir -p "$STATE_DIR"
  local cmd=(
    python3 "$REPO_DIR/tools/check_unit_ugv_target_map.py"
    --target-map "$TARGET_MAP"
    --platform-id "$PLATFORM_ID"
    --require-object-queries
    --output "$TARGET_CHECK_FILE"
  )
  if [[ -n "$SELECT_OBJECT_QUERY" ]]; then
    cmd+=(--select-object-query "$SELECT_OBJECT_QUERY")
  fi
  PYTHONDONTWRITEBYTECODE=1 "${cmd[@]}"
}

check_ros_master() {
  if (( SKIP_ROS_MASTER_CHECK )); then
    echo "ros master check skipped"
    return 0
  fi
  timeout 5s rosservice list >/dev/null
}

check_move_base_server() {
  if (( ! REQUIRE_MOVE_BASE_SERVER )); then
    return 0
  fi
  PYTHONDONTWRITEBYTECODE=1 python3 - "$MOVE_BASE_ACTION" "$MOVE_BASE_SERVER_TIMEOUT_S" <<'PY'
import sys
import actionlib
import rospy
from move_base_msgs.msg import MoveBaseAction

action_name = sys.argv[1]
timeout_s = float(sys.argv[2])
rospy.init_node("changxin_gateway_move_base_precheck", anonymous=True, disable_signals=True)
client = actionlib.SimpleActionClient(action_name, MoveBaseAction)
if not client.wait_for_server(rospy.Duration(timeout_s)):
    raise SystemExit(f"move_base action server not reachable: {action_name}")
print(f"move_base action server reachable: {action_name}")
PY
}

precheck() {
  source_env
  print_context
  require_common_files
  check_imports
  check_target_map
  check_ros_master
  check_move_base_server
  json_state "precheck_ok" ""
  echo "[done] precheck ok"
}

build_command() {
  GATEWAY_CMD=(
    python3 "$REPO_DIR/tools/run_ros1_platform_gateway_node.py"
    --platform-id "$PLATFORM_ID"
    --platform-type ugv
    --capability "$CAPABILITY"
    --service-symbol "$SERVICE_SYMBOL"
    --dry-run-service "$DRY_RUN_SERVICE"
    --dispatch-service "$DISPATCH_SERVICE"
    --node-name "$NODE_NAME"
    --unit-ugv-target-map "$TARGET_MAP"
    --unit-ugv-move-base-action "$MOVE_BASE_ACTION"
    --unit-ugv-move-base-server-timeout-s "$MOVE_BASE_SERVER_TIMEOUT_S"
    --unit-ugv-max-move-base-distance-m "$MAX_MOVE_BASE_DISTANCE_M"
    --unit-ugv-progress-output "$PROGRESS_OUTPUT"
  )
  if (( OPERATOR_APPROVED )); then
    GATEWAY_CMD+=(--unit-ugv-operator-approved)
  fi
  if (( ENABLE_MOVE_BASE )); then
    GATEWAY_CMD+=(--unit-ugv-enable-move-base)
  fi
}

print_command() {
  build_command
  printf 'cd %q && exec env PYTHONDONTWRITEBYTECODE=1' "$REPO_DIR"
  printf ' %q' "${GATEWAY_CMD[@]}"
  printf '\n'
}

wait_for_services() {
  local deadline=$((SECONDS + SERVICE_TIMEOUT_S))
  while (( SECONDS <= deadline )); do
    if rosservice list 2>/dev/null | grep -Fx "$DRY_RUN_SERVICE" >/dev/null \
      && rosservice list 2>/dev/null | grep -Fx "$DISPATCH_SERVICE" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_gateway() {
  if [[ "$ACTION" == "start-motion" ]]; then
    OPERATOR_APPROVED=1
    ENABLE_MOVE_BASE=1
    REQUIRE_MOVE_BASE_SERVER=1
  fi
  precheck
  if is_running; then
    echo "[done] gateway already running: pid $(read_pid)"
    return 0
  fi
  build_command
  mkdir -p "$STATE_DIR" "$(dirname "$PROGRESS_OUTPUT")"
  print_command > "$COMMAND_FILE"
  : > "$LOG_FILE"
  if (( DRY_RUN )); then
    echo "+ $(cat "$COMMAND_FILE")"
    json_state "dry_run" "start command printed"
    return 0
  fi
  (
    cd "$REPO_DIR"
    exec env PYTHONDONTWRITEBYTECODE=1 "${GATEWAY_CMD[@]}"
  ) >> "$LOG_FILE" 2>&1 &
  local pid=$!
  echo "$pid" > "$PID_FILE"
  json_state "starting" "waiting for service registration"
  if ! wait_for_services; then
    json_state "failed" "gateway services did not register before timeout"
    echo "[ERR] gateway services did not register before timeout" >&2
    tail -n "$TAIL_LINES" "$LOG_FILE" >&2 || true
    return 1
  fi
  json_state "running" "gateway services registered"
  echo "[done] gateway running: pid $pid"
}

stop_gateway() {
  mkdir -p "$STATE_DIR"
  if ! is_running; then
    echo "[done] gateway not running"
    json_state "stopped" "no live pid"
    return 0
  fi
  local pid
  pid="$(read_pid)"
  if (( DRY_RUN )); then
    echo "+ kill $pid"
    return 0
  fi
  kill "$pid"
  for _ in $(seq 1 10); do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      rm -f "$PID_FILE"
      json_state "stopped" "process stopped"
      echo "[done] stopped pid $pid"
      return 0
    fi
    sleep 1
  done
  kill -9 "$pid" >/dev/null 2>&1 || true
  rm -f "$PID_FILE"
  json_state "stopped" "process killed after timeout"
  echo "[done] killed pid $pid"
}

status_gateway() {
  mkdir -p "$STATE_DIR"
  if (( SOURCE_ENV )); then
    if [[ -f "$ROS_SETUP" ]]; then
      source_setup_file "$ROS_SETUP" || echo "ros_setup_source_failed: $ROS_SETUP"
      if [[ -f "$WORKSPACE_DIR/devel/setup.bash" ]]; then
        source_setup_file "$WORKSPACE_DIR/devel/setup.bash" || echo "workspace_setup_source_failed: $WORKSPACE_DIR/devel/setup.bash"
      fi
    else
      echo "ros_setup_missing: $ROS_SETUP"
    fi
  fi
  print_context
  echo "pid_file: $PID_FILE"
  echo "log_file: $LOG_FILE"
  echo "state_file: $STATE_FILE"
  if is_running; then
    echo "process_alive: true"
    echo "pid: $(read_pid)"
  else
    echo "process_alive: false"
  fi
  if timeout 3s rosservice list > "$ROS_LIST_FILE" 2>/dev/null; then
    echo "rosservice_list: ok"
    grep -Fx "$DRY_RUN_SERVICE" "$ROS_LIST_FILE" || true
    grep -Fx "$DISPATCH_SERVICE" "$ROS_LIST_FILE" || true
  else
    echo "rosservice_list: failed"
  fi
}

signature_gateway() {
  source_env
  mkdir -p "$STATE_DIR"
  rosservice list | tee "$ROS_LIST_FILE"
  : > "$ROS_TYPE_FILE"
  : > "$ROS_ARGS_FILE"
  for service in "$DRY_RUN_SERVICE" "$DISPATCH_SERVICE"; do
    {
      printf "%s " "$service"
      rosservice type "$service"
    } | tee -a "$ROS_TYPE_FILE"
    {
      printf "%s " "$service"
      rosservice args "$service"
    } | tee -a "$ROS_ARGS_FILE"
  done
  echo "rosservice_list_file: $ROS_LIST_FILE"
  echo "rosservice_type_file: $ROS_TYPE_FILE"
  echo "rosservice_args_file: $ROS_ARGS_FILE"
}

runtime_probe() {
  source_env
  local probe="$REPO_DIR/ugv/01-scripts/probe_ugv_runtime_readonly.sh"
  [[ -f "$probe" ]] || die "runtime probe script missing: $probe"
  if (( DRY_RUN )); then
    printf '+ %q' "$probe"
    printf ' --evidence-dir %q --workspace-dir %q --ros-setup %q --echo-timeout-s %q --tf-timeout-s %q' \
      "$EVIDENCE_DIR" "$WORKSPACE_DIR" "$ROS_SETUP" "$ECHO_TIMEOUT_S" "$TF_TIMEOUT_S"
    printf '\n'
    return 0
  fi
  "$probe" \
    --evidence-dir "$EVIDENCE_DIR" \
    --workspace-dir "$WORKSPACE_DIR" \
    --ros-setup "$ROS_SETUP" \
    --echo-timeout-s "$ECHO_TIMEOUT_S" \
    --tf-timeout-s "$TF_TIMEOUT_S"
}

logs_gateway() {
  if [[ -f "$LOG_FILE" ]]; then
    tail -n "$TAIL_LINES" "$LOG_FILE"
  else
    echo "log missing: $LOG_FILE"
  fi
}

case "$ACTION" in
  precheck)
    precheck
    ;;
  command)
    print_command
    ;;
  start|start-motion)
    start_gateway
    ;;
  stop)
    stop_gateway
    ;;
  restart)
    stop_gateway
    ACTION="start"
    start_gateway
    ;;
  status)
    status_gateway
    ;;
  signature)
    signature_gateway
    ;;
  runtime-probe)
    runtime_probe
    ;;
  logs)
    logs_gateway
    ;;
  *)
    die "unsupported action: $ACTION"
    ;;
esac
