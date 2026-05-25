#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
TS="$(date +%Y%m%d_%H%M%S)"
WORKSPACE_DIR="${WORKSPACE_DIR:-$HOME/catkin_ws}"
ROS_SETUP="${ROS_SETUP:-/opt/ros/noetic/setup.bash}"
EVIDENCE_DIR="${EVIDENCE_DIR:-$HOME/ugv-real-evidence/runtime-readonly-$TS}"
ECHO_TIMEOUT_S=5
TF_TIMEOUT_S=5
SOURCE_ENV=1
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage:
  probe_ugv_runtime_readonly.sh [options]

Read-only UGV runtime probe. It captures the live ROS graph, planner topics,
selected state frames, chassis feedback, and TF health. It does not publish
topics, call services, set parameters, or start/stop robot processes.

Options:
  --evidence-dir DIR       Output directory. Default: ~/ugv-real-evidence/runtime-readonly-<timestamp>
  --workspace-dir DIR      Catkin workspace. Default: ~/catkin_ws
  --ros-setup FILE         ROS setup.bash. Default: /opt/ros/noetic/setup.bash
  --echo-timeout-s SEC     rostopic echo timeout. Default: 5
  --tf-timeout-s SEC       tf_echo timeout. Default: 5
  --no-source              Do not source ROS/workspace setup files.
  --dry-run                Print commands without executing them.
  -h, --help               Show this help.
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

run_capture() {
  local outfile="$1"
  shift
  if (( DRY_RUN )); then
    echo "+ $*" | tee -a "$outfile"
    return 0
  fi
  {
    echo "+ $*"
    "$@" || true
  } > "$outfile" 2>&1
}

run_capture_shell() {
  local outfile="$1"
  shift
  if (( DRY_RUN )); then
    echo "+ $*" | tee -a "$outfile"
    return 0
  fi
  {
    echo "+ $*"
    bash -lc "$*" || true
  } > "$outfile" 2>&1
}

safe_name() {
  local value="$1"
  value="${value#/}"
  value="${value//\//_}"
  value="${value//[^A-Za-z0-9_.-]/_}"
  echo "$value"
}

mkdir -p "$EVIDENCE_DIR"

{
  echo "script: $SCRIPT_NAME"
  echo "generated_at: $(date -Is)"
  echo "hostname: $(hostname)"
  echo "user: $(whoami)"
  echo "workspace_dir: $WORKSPACE_DIR"
  echo "ros_setup: $ROS_SETUP"
  echo "source_env: $SOURCE_ENV"
  echo "dry_run: $DRY_RUN"
  echo "echo_timeout_s: $ECHO_TIMEOUT_S"
  echo "tf_timeout_s: $TF_TIMEOUT_S"
} | tee "$EVIDENCE_DIR/00_context.txt"

if (( SOURCE_ENV )) && (( ! DRY_RUN )); then
  [[ -f "$ROS_SETUP" ]] && source "$ROS_SETUP" || true
  [[ -f "$WORKSPACE_DIR/devel/setup.bash" ]] && source "$WORKSPACE_DIR/devel/setup.bash" || true
fi

run_capture_shell "$EVIDENCE_DIR/01_ros_env.txt" \
  'echo "$ROS_DISTRO"; echo "$ROS_MASTER_URI"; echo "$ROS_HOSTNAME"; echo "$ROS_IP"; env | grep -E "^(ROS|PYTHONPATH|LD_LIBRARY_PATH|PATH)=" | sort'

run_capture_shell "$EVIDENCE_DIR/02_processes.txt" \
  'ps -eo pid,ppid,cmd | grep -Ei "ros|move_base|yhs_can|velocity_smoother|ndt|amcl|map_server|rslidar|imu|camera" | grep -v grep'

if (( DRY_RUN )); then
  ROS_MASTER_REACHABLE="dry-run"
elif timeout 3s rostopic list >/dev/null 2>&1; then
  ROS_MASTER_REACHABLE="true"
else
  ROS_MASTER_REACHABLE="false"
fi

run_capture "$EVIDENCE_DIR/03_rosnode_list.txt" timeout 5s rosnode list
run_capture "$EVIDENCE_DIR/04_rostopic_list.txt" timeout 5s rostopic list
run_capture "$EVIDENCE_DIR/05_rosservice_list.txt" timeout 5s rosservice list
run_capture "$EVIDENCE_DIR/06_rosparam_core.txt" bash -lc \
  'for p in /common/chassis_type /move_base/base_global_planner /move_base/base_local_planner /yhs_can_control/tfUsed; do echo "===== $p ====="; rosparam get "$p"; done'

topics=(
  /cmd_vel
  /smoother_cmd_vel
  /robot_cmd_vel
  /move_base_simple/goal
  /move_base/goal
  /move_base/cancel
  /move_base/status
  /move_base/current_goal
  /move_base/result
  /odom
  /chassis_info_fb
  /imu_data
  /map
  /scan
  /scan1
  /scan2
  /scan3
)

for topic in "${topics[@]}"; do
  safe="$(safe_name "$topic")"
  run_capture "$EVIDENCE_DIR/topic_info_$safe.txt" timeout 5s rostopic info "$topic"
done

echo_topics=(
  /move_base/status
  /odom
  /chassis_info_fb
  /imu_data
  /cmd_vel
  /smoother_cmd_vel
)

for topic in "${echo_topics[@]}"; do
  safe="$(safe_name "$topic")"
  run_capture "$EVIDENCE_DIR/topic_echo_$safe.txt" timeout "$ECHO_TIMEOUT_S"s rostopic echo -n 1 "$topic"
done

run_capture "$EVIDENCE_DIR/tf_map_base_link.txt" timeout "$TF_TIMEOUT_S"s rosrun tf tf_echo map base_link
run_capture "$EVIDENCE_DIR/tf_odom_base_link.txt" timeout "$TF_TIMEOUT_S"s rosrun tf tf_echo odom base_link

run_capture_shell "$EVIDENCE_DIR/topic_subset.txt" \
  "rostopic list | egrep 'map|scan|odom|cmd_vel|move_base|chassis|imu|recharge' || true"

{
  echo "profile: ugv-runtime-readonly-probe"
  echo "evidence_dir: $EVIDENCE_DIR"
  echo "workspace_dir: $WORKSPACE_DIR"
  echo "ros_master_reachable: $ROS_MASTER_REACHABLE"
  echo "read_only: true"
  echo
  echo "primary_files:"
  echo "- 03_rosnode_list.txt"
  echo "- 04_rostopic_list.txt"
  echo "- 06_rosparam_core.txt"
  echo "- topic_info_move_base_status.txt"
  echo "- topic_echo_chassis_info_fb.txt"
  echo "- topic_echo_odom.txt"
  echo "- tf_map_base_link.txt"
  echo "- tf_odom_base_link.txt"
} | tee "$EVIDENCE_DIR/summary.txt"

echo
echo "[done] UGV runtime evidence written to: $EVIDENCE_DIR"
