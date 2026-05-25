#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
TS="$(date +%Y%m%d_%H%M%S)"
WORKSPACE_DIR="${WORKSPACE_DIR:-$HOME/catkin_ws}"
ROS_SETUP="${ROS_SETUP:-/opt/ros/noetic/setup.bash}"
EVIDENCE_DIR="${EVIDENCE_DIR:-$HOME/ugv-probe-$TS}"
SOURCE_ENV=1
PACK_SOURCE=0

usage() {
  cat <<'EOF'
Usage:
  probe_ugv_readonly.sh [options]

Read-only OS-mate / UGV probe. It collects system, ROS, device, launch,
YAML, and runtime graph evidence. It does not publish ROS topics, call
services, change parameters, or start/stop robot processes.

Options:
  --evidence-dir DIR     Output directory. Default: ~/ugv-probe-<timestamp>
  --workspace-dir DIR    Catkin workspace. Default: ~/catkin_ws
  --ros-setup FILE       ROS setup.bash. Default: /opt/ros/noetic/setup.bash
  --no-source            Do not source ROS/workspace setup files.
  --pack-source          Also create a filtered source tarball in evidence dir.
  -h, --help             Show this help.
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
    --no-source)
      SOURCE_ENV=0
      shift
      ;;
    --pack-source)
      PACK_SOURCE=1
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
  {
    echo "+ $*"
    "$@" || true
  } > "$outfile" 2>&1
}

run_capture_shell() {
  local outfile="$1"
  shift
  {
    echo "+ $*"
    bash -lc "$*" || true
  } > "$outfile" 2>&1
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
  echo "pack_source: $PACK_SOURCE"
} | tee "$EVIDENCE_DIR/00_context.txt"

if (( SOURCE_ENV )); then
  [[ -f "$ROS_SETUP" ]] && source "$ROS_SETUP" || true
  [[ -f "$WORKSPACE_DIR/devel/setup.bash" ]] && source "$WORKSPACE_DIR/devel/setup.bash" || true
fi

run_capture_shell "$EVIDENCE_DIR/01_system.txt" \
  'uname -a; echo; cat /etc/os-release 2>/dev/null; echo; lsb_release -a 2>/dev/null; echo; env | grep -E "^(ROS|CMAKE|PYTHONPATH|LD_LIBRARY_PATH|PATH)=" | sort'

run_capture_shell "$EVIDENCE_DIR/02_network.txt" \
  'hostname -I 2>/dev/null; echo; ip addr 2>/dev/null; echo; ip route 2>/dev/null; echo; ss -lntup 2>/dev/null | sed -n "1,120p"'

run_capture_shell "$EVIDENCE_DIR/03_devices.txt" \
  'ls -l /dev/can* /dev/ttyUSB* /dev/ttyACM* /dev/input/js* 2>/dev/null; echo; lsusb 2>/dev/null; echo; ip -details link show can0 2>/dev/null'

run_capture_shell "$EVIDENCE_DIR/04_processes.txt" \
  'ps -eo pid,ppid,cmd | grep -Ei "ros|yhs|move_base|amcl|gmapping|cartographer|lio|timoo|imu|can|nmea|nxserver|NoMachine" | grep -v grep'

run_capture_shell "$EVIDENCE_DIR/05_code_index.txt" \
  "find '$WORKSPACE_DIR/src' -type f \\( -name package.xml -o -name CMakeLists.txt -o -name '*.launch' -o -name '*.launch.py' -o -name '*.yaml' -o -name '*.py' -o -name '*.cpp' -o -name '*.h' \\) 2>/dev/null | sort"

run_capture_shell "$EVIDENCE_DIR/06_launch_files.txt" \
  "find '$WORKSPACE_DIR/src' -type f \\( -name '*.launch' -o -name '*.launch.py' \\) 2>/dev/null | sort"

run_capture_shell "$EVIDENCE_DIR/07_yaml_configs.txt" \
  "find '$WORKSPACE_DIR/src' -type f -name '*.yaml' 2>/dev/null | sort"

run_capture_shell "$EVIDENCE_DIR/08_ros_packages.txt" \
  'rospack list 2>/dev/null | grep -Ei "yhs|timoo|serial_imu|lio|robot_localization|ascamera|nmea|navigation|move_base|amcl|gmapping|cartographer" || true'

if timeout 3s rostopic list >/dev/null 2>&1; then
  run_capture "$EVIDENCE_DIR/09_rosnode_list.txt" timeout 5s rosnode list
  run_capture "$EVIDENCE_DIR/10_rostopic_list.txt" timeout 5s rostopic list
  run_capture "$EVIDENCE_DIR/11_rosservice_list.txt" timeout 5s rosservice list
  run_capture "$EVIDENCE_DIR/12_rosparam_list.txt" timeout 5s rosparam list
  for topic in /smoother_cmd_vel /chassis_info_fb /odom /imu_data /tmlidar_points /scan /scan1 /move_base_simple/goal /move_base/goal; do
    safe="${topic//\//_}"
    run_capture "$EVIDENCE_DIR/topic${safe}.txt" timeout 5s rostopic info "$topic"
  done
else
  echo "ROS master not reachable; runtime graph capture skipped." > "$EVIDENCE_DIR/09_ros_runtime_skipped.txt"
fi

if (( PACK_SOURCE )); then
  tar \
    --exclude='*/build' \
    --exclude='*/devel' \
    --exclude='*/install' \
    --exclude='*/log' \
    --exclude='*.bag' \
    --exclude='*.pcd' \
    --exclude='*.db3' \
    --exclude='*.zip' \
    --exclude='*.tar.gz' \
    -czf "$EVIDENCE_DIR/ugv_source_filtered_$TS.tar.gz" \
    -C "$(dirname "$WORKSPACE_DIR")" "$(basename "$WORKSPACE_DIR")" \
    > "$EVIDENCE_DIR/99_tar_stdout.txt" 2> "$EVIDENCE_DIR/99_tar_stderr.txt" || true
fi

{
  echo "profile: ugv-os-mate-readonly-probe"
  echo "evidence_dir: $EVIDENCE_DIR"
  echo "workspace_dir: $WORKSPACE_DIR"
  echo "ros_master_reachable: $(test -f "$EVIDENCE_DIR/09_ros_runtime_skipped.txt" && echo false || echo true)"
  echo "source_tarball: $(ls "$EVIDENCE_DIR"/ugv_source_filtered_*.tar.gz 2>/dev/null | head -n 1 || true)"
  echo
  echo "next_files_to_share:"
  echo "- 00_context.txt"
  echo "- 01_system.txt"
  echo "- 05_code_index.txt"
  echo "- 06_launch_files.txt"
  echo "- 07_yaml_configs.txt"
  echo "- 10_rostopic_list.txt if present"
  echo "- topic_smoother_cmd_vel.txt if present"
  echo "- topic_move_base_goal.txt if present"
} | tee "$EVIDENCE_DIR/summary.txt"

echo
echo "[done] UGV evidence written to: $EVIDENCE_DIR"
