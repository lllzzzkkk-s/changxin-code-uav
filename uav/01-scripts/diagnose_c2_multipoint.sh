#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
ROS_SETUP="${ROS_SETUP:-/opt/ros/noetic/setup.bash}"
DIFF_PLANNER_DIR="${DIFF_PLANNER_DIR:-$HOME/Diff-planner}"
WORKSPACE_SETUP=""
EVIDENCE_DIR=""
MULTIPOINT_LOG=""
TRIGGER_WINDOW_S=15
STATE_TIMEOUT_S=5
SOURCE_ENV=1
DRY_RUN=0

ACTION_TOPICS=(
  "/goal"
  "/move_base_simple/goal"
  "/back_trigger"
  "/px4ctrl/takeoff_land"
  "/setpoints_cmd"
)

STATE_TOPICS=(
  "/mavros/state"
  "/mavros/rc/in"
  "/mavros/battery"
  "/ekf/ekf_odom"
  "/laserMapping/odometry"
)

INFO_TOPICS=(
  "/goal"
  "/move_base_simple/goal"
  "/back_trigger"
  "/px4ctrl/takeoff_land"
  "/setpoints_cmd"
  "/drone_0_planning/trajectory"
)

usage() {
  cat <<'EOF'
Usage:
  diagnose_c2_multipoint.sh [options]

Read-only C2 multipoint diagnostic. This script does not publish ROS topics,
does not arm, and does not change parameters. It captures graph, params,
state snapshots, multipoint logs, and a concurrent passive action-topic
listening window.

Options:
  --evidence-dir DIR
      Output directory. Default: ~/uav-g3e-real-evidence/c2-diag-<timestamp>
  --diff-planner-dir DIR
      Diff-planner workspace path. Default: ~/Diff-planner
  --ros-setup FILE
      ROS setup.bash path. Default: /opt/ros/noetic/setup.bash
  --workspace-setup FILE
      Workspace setup.bash path. Default: <diff-planner-dir>/devel/setup.bash
  --multipoint-log FILE
      Explicit multipoint log path. Default: latest ~/uav-safe-bringup-logs/*/multipoint.log if present.
  --trigger-window-s SECONDS
      Concurrent passive echo window for action topics. Default: 15
  --state-timeout-s SECONDS
      Timeout for one-shot state topic echoes. Default: 5
  --no-source
      Do not source ROS/workspace setup files; use current shell environment.
  --dry-run
      Print the read-only commands that would run without creating evidence.
  -h, --help
      Show this help.

Typical C2 observation:
  # Terminal A
  bash uav/01-scripts/diagnose_c2_multipoint.sh --trigger-window-s 20

  # Terminal B, only after Terminal A prints "ACTION MONITORS ARMED"
  cd ~/Diff-planner && ./sh_files/pub_trigger.sh
EOF
}

die() {
  echo "[ERR] $*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --evidence-dir)
      [[ $# -ge 2 ]] || die "--evidence-dir requires a value"
      EVIDENCE_DIR="$2"
      shift 2
      ;;
    --diff-planner-dir)
      [[ $# -ge 2 ]] || die "--diff-planner-dir requires a value"
      DIFF_PLANNER_DIR="$2"
      shift 2
      ;;
    --ros-setup)
      [[ $# -ge 2 ]] || die "--ros-setup requires a value"
      ROS_SETUP="$2"
      shift 2
      ;;
    --workspace-setup)
      [[ $# -ge 2 ]] || die "--workspace-setup requires a value"
      WORKSPACE_SETUP="$2"
      shift 2
      ;;
    --multipoint-log)
      [[ $# -ge 2 ]] || die "--multipoint-log requires a value"
      MULTIPOINT_LOG="$2"
      shift 2
      ;;
    --trigger-window-s)
      [[ $# -ge 2 ]] || die "--trigger-window-s requires a value"
      TRIGGER_WINDOW_S="$2"
      shift 2
      ;;
    --state-timeout-s)
      [[ $# -ge 2 ]] || die "--state-timeout-s requires a value"
      STATE_TIMEOUT_S="$2"
      shift 2
      ;;
    --no-source)
      SOURCE_ENV=0
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

if [[ -z "$EVIDENCE_DIR" ]]; then
  EVIDENCE_DIR="$HOME/uav-g3e-real-evidence/c2-diag-$(date +%Y%m%d-%H%M%S)"
fi
if [[ -z "$WORKSPACE_SETUP" ]]; then
  WORKSPACE_SETUP="$DIFF_PLANNER_DIR/devel/setup.bash"
fi

safe_name() {
  echo "$1" | sed 's#[^A-Za-z0-9_]#_#g'
}

latest_multipoint_log() {
  if [[ -n "$MULTIPOINT_LOG" ]]; then
    echo "$MULTIPOINT_LOG"
    return 0
  fi

  local latest_dir=""
  if [[ -d "$HOME/uav-safe-bringup-logs" ]]; then
    latest_dir="$(ls -td "$HOME"/uav-safe-bringup-logs/* 2>/dev/null | head -n 1 || true)"
  fi
  if [[ -n "$latest_dir" && -f "$latest_dir/multipoint.log" ]]; then
    echo "$latest_dir/multipoint.log"
    return 0
  fi

  echo ""
}

print_config() {
  cat <<EOF
SCRIPT=$SCRIPT_NAME
EVIDENCE_DIR=$EVIDENCE_DIR
DIFF_PLANNER_DIR=$DIFF_PLANNER_DIR
ROS_SETUP=$ROS_SETUP
WORKSPACE_SETUP=$WORKSPACE_SETUP
MULTIPOINT_LOG=${MULTIPOINT_LOG:-<auto>}
TRIGGER_WINDOW_S=$TRIGGER_WINDOW_S
STATE_TIMEOUT_S=$STATE_TIMEOUT_S
SOURCE_ENV=$SOURCE_ENV
DRY_RUN=$DRY_RUN
EOF
}

run_readonly() {
  local label="$1"
  local outfile="$2"
  local timeout_s="$3"
  shift 3

  echo "[capture] $label -> $outfile"
  if (( DRY_RUN )); then
    echo "+ timeout ${timeout_s}s $*"
    return 0
  fi

  {
    echo "### $label"
    echo "+ timeout ${timeout_s}s $*"
    timeout "${timeout_s}s" "$@" || true
  } > "$outfile" 2>&1
}

capture_topic_info() {
  local outfile="$EVIDENCE_DIR/02-topic-info.txt"
  echo "[capture] topic info -> $outfile"
  if (( DRY_RUN )); then
    for topic in "${INFO_TOPICS[@]}"; do
      echo "+ timeout 5s rostopic info $topic"
    done
    return 0
  fi

  {
    for topic in "${INFO_TOPICS[@]}"; do
      echo "===== $topic ====="
      timeout 5s rostopic info "$topic" || true
      echo
    done
  } > "$outfile" 2>&1
}

capture_rosparams() {
  local outfile="$EVIDENCE_DIR/03-rosparam-multipoint.txt"
  echo "[capture] multipoint rosparams -> $outfile"
  if (( DRY_RUN )); then
    echo "+ timeout 5s rosparam list"
    echo "+ timeout 5s rosparam get /multipointplan/yaml_path"
    echo "+ timeout 5s rosparam get /multipointplan/next_distance"
    return 0
  fi

  {
    echo "===== rosparam list | grep multipoint ====="
    timeout 5s rosparam list | grep -E 'multipoint|points|next_distance|start_plan|back_plan|fligt_type|flight_type' || true
    echo
    for param in \
      /multipointplan/yaml_path \
      /multipointplan/next_distance \
      /multipointplan/start_plan \
      /multipointplan/back_plan \
      /multipointplan/fligt_type \
      /multipointplan/flight_type; do
      echo "===== $param ====="
      timeout 5s rosparam get "$param" || true
      echo
    done
  } > "$outfile" 2>&1
}

capture_state_topics() {
  local outfile="$EVIDENCE_DIR/04-state-snapshots.txt"
  echo "[capture] state snapshots -> $outfile"
  if (( DRY_RUN )); then
    for topic in "${STATE_TOPICS[@]}"; do
      echo "+ timeout ${STATE_TIMEOUT_S}s rostopic echo -n 1 $topic"
    done
    return 0
  fi

  {
    for topic in "${STATE_TOPICS[@]}"; do
      echo "===== $topic ====="
      timeout "${STATE_TIMEOUT_S}s" rostopic echo -n 1 "$topic" || echo "NO_MESSAGE_WITHIN_${STATE_TIMEOUT_S}S"
      echo
    done
  } > "$outfile" 2>&1
}

capture_action_window() {
  local action_dir="$EVIDENCE_DIR/action-topic-echo"
  local outfile="$EVIDENCE_DIR/05-action-topic-passive-echo.txt"
  echo "[capture] action-topic passive window -> $outfile"
  if (( DRY_RUN )); then
    for topic in "${ACTION_TOPICS[@]}"; do
      echo "+ timeout ${TRIGGER_WINDOW_S}s rostopic echo -n 1 $topic"
    done
    echo "[dry-run] no action topic monitors are started"
    return 0
  fi

  mkdir -p "$action_dir"
  local pids=()
  local files=()
  local topics=()
  for topic in "${ACTION_TOPICS[@]}"; do
    local file="$action_dir/$(safe_name "$topic").txt"
    files+=("$file")
    topics+=("$topic")
    timeout "${TRIGGER_WINDOW_S}s" rostopic echo -n 1 "$topic" > "$file" 2>&1 &
    pids+=("$!")
  done

  echo
  echo "===== ACTION MONITORS ARMED ====="
  echo "For a C2 trigger observation, run ./sh_files/pub_trigger.sh in another terminal now."
  echo "Listening for ${TRIGGER_WINDOW_S}s on: ${ACTION_TOPICS[*]}"
  echo

  local pid
  for pid in "${pids[@]}"; do
    wait "$pid" || true
  done

  {
    local idx
    for idx in "${!topics[@]}"; do
      echo "===== ${topics[$idx]} ====="
      cat "${files[$idx]}" || true
      if [[ ! -s "${files[$idx]}" ]]; then
        echo "NO_MESSAGE_WITHIN_${TRIGGER_WINDOW_S}S"
      fi
      echo
    done
  } > "$outfile"
}

capture_multipoint_log() {
  local outfile="$EVIDENCE_DIR/06-multipoint-log-keywords.txt"
  local log_path
  log_path="$(latest_multipoint_log)"
  echo "[capture] multipoint log keywords -> $outfile"
  if (( DRY_RUN )); then
    echo "+ grep -nE 'Loaded pyt|Get start trigger|Publish the first pyt|No pyt|Failed|ERROR' <multipoint-log>"
    return 0
  fi

  {
    echo "multipoint_log: ${log_path:-<not-found>}"
    echo
    if [[ -n "$log_path" && -f "$log_path" ]]; then
      grep -nE 'Loaded pyt|Get start trigger|Publish the first pyt|No pyt|Failed|ERROR|WARN|pyt|trigger' "$log_path" || true
      echo
      echo "===== tail -120 ====="
      tail -n 120 "$log_path" || true
    else
      echo "NO_MULTIPOINT_LOG_FOUND"
    fi
  } > "$outfile" 2>&1
}

topic_message_seen() {
  local file="$1"
  [[ -s "$file" ]] || return 1
  if grep -Eq '^(WARNING|ERROR):|does not appear|Unable to communicate|Cannot load message|unknown topic|not appear to be published' "$file"; then
    return 1
  fi
  return 0
}

write_summary() {
  local outfile="$EVIDENCE_DIR/summary.txt"
  echo "[write] summary -> $outfile"
  if (( DRY_RUN )); then
    return 0
  fi

  local action_dir="$EVIDENCE_DIR/action-topic-echo"
  local any_action="false"
  local goal_seen="false"
  local trigger_seen="false"
  local setpoints_seen="false"
  local topic
  for topic in "${ACTION_TOPICS[@]}"; do
    local file="$action_dir/$(safe_name "$topic").txt"
    if topic_message_seen "$file"; then
      any_action="true"
      case "$topic" in
        /goal) goal_seen="true" ;;
        /move_base_simple/goal|/back_trigger|/px4ctrl/takeoff_land) trigger_seen="true" ;;
        /setpoints_cmd) setpoints_seen="true" ;;
      esac
    fi
  done

  local nodes_file="$EVIDENCE_DIR/01-rosnode-list.txt"
  local multipoint_node="false"
  local planner_node="false"
  local traj_server_node="false"
  local px4ctrl_node="false"
  if [[ -f "$nodes_file" ]]; then
    grep -qx "/multipointplan" "$nodes_file" && multipoint_node="true" || true
    grep -qx "/drone_0_diff_planner_node" "$nodes_file" && planner_node="true" || true
    grep -qx "/drone_0_traj_server" "$nodes_file" && traj_server_node="true" || true
    grep -qx "/px4ctrl" "$nodes_file" && px4ctrl_node="true" || true
  fi

  local keyword_hits="0"
  if [[ -f "$EVIDENCE_DIR/06-multipoint-log-keywords.txt" ]]; then
    keyword_hits="$(grep -cE 'Loaded pyt|Get start trigger|Publish the first pyt|No pyt|Failed|ERROR|WARN|pyt|trigger' "$EVIDENCE_DIR/06-multipoint-log-keywords.txt" || true)"
  fi

  {
    echo "profile: c2-multipoint-diagnostic"
    echo "evidence_dir: $EVIDENCE_DIR"
    echo "generated_at: $(date)"
    echo "read_only_script: true"
    echo "trigger_window_s: $TRIGGER_WINDOW_S"
    echo "multipoint_node_present: $multipoint_node"
    echo "planner_node_present: $planner_node"
    echo "traj_server_node_present: $traj_server_node"
    echo "px4ctrl_node_present: $px4ctrl_node"
    echo "action_topic_message_received: $any_action"
    echo "goal_message_received: $goal_seen"
    echo "operator_trigger_message_received: $trigger_seen"
    echo "setpoints_cmd_message_received: $setpoints_seen"
    echo "multipoint_keyword_hits: $keyword_hits"
    echo
    echo "files:"
    echo "- 00-context.txt"
    echo "- 01-rosnode-list.txt"
    echo "- 02-topic-info.txt"
    echo "- 03-rosparam-multipoint.txt"
    echo "- 04-state-snapshots.txt"
    echo "- 05-action-topic-passive-echo.txt"
    echo "- 06-multipoint-log-keywords.txt"
    echo
    echo "interpretation_hint:"
    if [[ "$trigger_seen" == "true" && "$goal_seen" == "false" ]]; then
      echo "- trigger was observed but /goal was not; inspect multipoint log and yaml_path/points."
    elif [[ "$goal_seen" == "true" && "$setpoints_seen" == "false" ]]; then
      echo "- /goal was observed but /setpoints_cmd was not; inspect planner/traj_server path."
    elif [[ "$goal_seen" == "true" && "$setpoints_seen" == "true" ]]; then
      echo "- /goal and /setpoints_cmd were observed; C2 produced planner output during the window."
    else
      echo "- no action topic message was observed; confirm listener was armed before operator trigger."
    fi
  } > "$outfile"
}

if (( DRY_RUN )); then
  print_config
  echo "[dry-run] no files are written and no ROS commands are executed"
  echo "+ source $ROS_SETUP"
  echo "+ source $WORKSPACE_SETUP"
  echo "+ rosnode list"
  capture_topic_info
  capture_rosparams
  capture_state_topics
  capture_action_window
  capture_multipoint_log
  exit 0
fi

mkdir -p "$EVIDENCE_DIR"
print_config | tee "$EVIDENCE_DIR/00-context.txt"

if (( SOURCE_ENV )); then
  [[ -f "$ROS_SETUP" ]] || die "ROS setup not found: $ROS_SETUP"
  [[ -f "$WORKSPACE_SETUP" ]] || die "workspace setup not found: $WORKSPACE_SETUP"
  # shellcheck disable=SC1090
  source "$ROS_SETUP"
  # shellcheck disable=SC1090
  source "$WORKSPACE_SETUP"
fi

run_readonly "rosnode list" "$EVIDENCE_DIR/01-rosnode-list.txt" 5 rosnode list
capture_topic_info
capture_rosparams
run_readonly "rosnode info /multipointplan" "$EVIDENCE_DIR/02a-rosnode-info-multipointplan.txt" 5 rosnode info /multipointplan
run_readonly "rosnode info /drone_0_diff_planner_node" "$EVIDENCE_DIR/02b-rosnode-info-diff-planner.txt" 5 rosnode info /drone_0_diff_planner_node
run_readonly "rosnode info /drone_0_traj_server" "$EVIDENCE_DIR/02c-rosnode-info-traj-server.txt" 5 rosnode info /drone_0_traj_server
capture_state_topics
capture_action_window
capture_multipoint_log
write_summary

echo
echo "[done] C2 multipoint diagnostic evidence written to:"
echo "$EVIDENCE_DIR"
echo
cat "$EVIDENCE_DIR/summary.txt"
