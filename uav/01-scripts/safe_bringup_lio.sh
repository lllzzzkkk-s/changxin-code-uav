#!/usr/bin/env zsh
set -eu

SCRIPT_NAME="${0:t}"
ROS_SETUP="${ROS_SETUP:-/opt/ros/noetic/setup.zsh}"
DIFF_PLANNER_DIR="${DIFF_PLANNER_DIR:-$HOME/Diff-planner}"
DRONE_ID_VALUE="${DRONE_ID:-0}"
STAGE="planner"
DRY_RUN=0
YES_CONTROL=0
SEND_STREAM_REQUESTS=1
FCU_URL=""
LOG_DIR="${LOG_DIR:-$HOME/uav-safe-bringup-logs/$(date +%Y%m%d-%H%M%S)}"

typeset -a LAUNCHED_PIDS

usage() {
  cat <<'EOF'
Usage:
  safe_bringup_lio.sh [options]

Safe staged LIO bring-up for the real UAV. The default stage stops before
px4ctrl/multipoint and never publishes action topics.

Options:
  --stage localization|planner|control-standby
      localization: mavros + faster_lio + ekf
      planner:      localization + diff_planner/traj_server (default)
      control-standby:
                    planner + px4ctrl + multipoint; requires --yes-control
                    or an interactive START_CONTROL_STANDBY confirmation.
  --diff-planner-dir DIR
      Diff-planner workspace path. Default: ~/Diff-planner
  --ros-setup FILE
      ROS setup.zsh path. Default: /opt/ros/noetic/setup.zsh
  --drone-id ID
      DRONE_ID exported for planner/control launch files. Default: 0
  --fcu-url URL
      Optional mavros fcu_url override. Empty uses px4.launch default.
  --log-dir DIR
      Directory for launch logs. Default: ~/uav-safe-bringup-logs/<timestamp>
  --yes-control
      Required non-interactive confirmation for --stage control-standby.
  --skip-stream-requests
      Do not send MAVLink message interval requests through mavcmd.
  --dry-run
      Print planned commands and checks without sourcing ROS or launching.
  -h, --help
      Show this help.

Examples:
  ./safe_bringup_lio.sh --stage planner
  ./safe_bringup_lio.sh --stage control-standby --yes-control
EOF
}

die() {
  print -u2 "[ERR] $*"
  exit 1
}

cleanup() {
  if (( ${#LAUNCHED_PIDS[@]} == 0 )); then
    return
  fi

  print
  print "[cleanup] stopping launched roslaunch processes..."
  local pid
  for pid in "${LAUNCHED_PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -INT "$pid" 2>/dev/null || true
    fi
  done
  for pid in "${LAUNCHED_PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
}

trap cleanup INT TERM

while (( $# > 0 )); do
  case "$1" in
    --stage)
      [[ $# -ge 2 ]] || die "--stage requires a value"
      STAGE="$2"
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
    --drone-id)
      [[ $# -ge 2 ]] || die "--drone-id requires a value"
      DRONE_ID_VALUE="$2"
      shift 2
      ;;
    --fcu-url)
      [[ $# -ge 2 ]] || die "--fcu-url requires a value"
      FCU_URL="$2"
      shift 2
      ;;
    --log-dir)
      [[ $# -ge 2 ]] || die "--log-dir requires a value"
      LOG_DIR="$2"
      shift 2
      ;;
    --yes-control)
      YES_CONTROL=1
      shift
      ;;
    --skip-stream-requests)
      SEND_STREAM_REQUESTS=0
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

case "$STAGE" in
  localization|planner|control-standby) ;;
  *) die "invalid --stage: $STAGE" ;;
esac

print "STAGE=$STAGE"
print "DIFF_PLANNER_DIR=$DIFF_PLANNER_DIR"
print "ROS_SETUP=$ROS_SETUP"
print "DRONE_ID=$DRONE_ID_VALUE"
print "LOG_DIR=$LOG_DIR"
if [[ "$STAGE" == "control-standby" && "$YES_CONTROL" == "1" ]]; then
  print "CONTROL_STANDBY_CONFIRMATION=provided"
fi

run_cmd() {
  print "+ $*"
  if (( DRY_RUN )); then
    return 0
  fi
  "$@"
}

launch_bg() {
  local name="$1"
  local delay_s="$2"
  shift 2
  local log_file="$LOG_DIR/${name}.log"

  print "+ $* > $log_file 2>&1 &"
  if (( DRY_RUN )); then
    return 0
  fi

  "$@" > "$log_file" 2>&1 &
  local pid=$!
  LAUNCHED_PIDS+=("$pid")
  print "[launch] $name pid=$pid log=$log_file"
  sleep "$delay_s"

  if ! kill -0 "$pid" 2>/dev/null; then
    print -u2 "[ERR] $name exited early. Last log lines:"
    tail -n 80 "$log_file" >&2 || true
    exit 1
  fi
}

wait_for_node() {
  local node="$1"
  local timeout_s="$2"
  print "[check] wait for node $node (${timeout_s}s)"
  if (( DRY_RUN )); then
    return 0
  fi

  local end=$(( SECONDS + timeout_s ))
  while (( SECONDS < end )); do
    if rosnode list 2>/dev/null | grep -qx "$node"; then
      return 0
    fi
    sleep 1
  done
  die "node not available: $node"
}

wait_for_topic_once() {
  local topic="$1"
  local timeout_s="$2"
  print "[check] wait for one message on $topic (${timeout_s}s)"
  if (( DRY_RUN )); then
    return 0
  fi

  timeout "${timeout_s}s" rostopic echo -n 1 "$topic" >/dev/null || die "no message on $topic within ${timeout_s}s"
}

wait_for_mavros_connected() {
  print "[check] wait for /mavros/state connected: True"
  if (( DRY_RUN )); then
    return 0
  fi

  local end=$(( SECONDS + 20 ))
  while (( SECONDS < end )); do
    if timeout 3s rostopic echo -n 1 /mavros/state 2>/dev/null | grep -q "connected: True"; then
      return 0
    fi
    sleep 1
  done
  die "mavros did not report connected: True"
}

expect_no_message() {
  local topic="$1"
  local timeout_s="$2"
  print "[check] expect no message on $topic (${timeout_s}s)"
  if (( DRY_RUN )); then
    return 0
  fi

  if timeout "${timeout_s}s" rostopic echo -n 1 "$topic" >/tmp/uav_safe_bringup_echo.$$ 2>/dev/null; then
    print -u2 "[ERR] unexpected message on $topic:"
    cat /tmp/uav_safe_bringup_echo.$$ >&2 || true
    rm -f /tmp/uav_safe_bringup_echo.$$
    exit 1
  fi
  rm -f /tmp/uav_safe_bringup_echo.$$
}

send_mavlink_stream_requests() {
  if (( SEND_STREAM_REQUESTS == 0 )); then
    return 0
  fi

  local msg_id
  for msg_id in 31 105 83 147 106; do
    run_cmd rosrun mavros mavcmd long 511 "$msg_id" 5000 0 0 0 0 0 || true
    if (( ! DRY_RUN )); then
      sleep 1
    fi
  done
}

print_control_precheck() {
  print
  print "[control precheck]"
  print "Before px4ctrl/multipoint standby, verify on the transmitter:"
  print "  CH1~CH4 approximately 1500"
  print "  CH5=1999, CH6=1999, CH7=999, CH8=1999"
  print "  /mavros/state armed: False"

  if (( DRY_RUN )); then
    return 0
  fi

  rostopic echo -n 1 /mavros/state || true
  rostopic echo -n 1 /mavros/rc/in || true

  if (( YES_CONTROL == 1 )); then
    return 0
  fi

  print -n "Type START_CONTROL_STANDBY to launch px4ctrl + multipoint, or anything else to stop here: "
  local answer
  read answer
  [[ "$answer" == "START_CONTROL_STANDBY" ]] || die "operator did not confirm control standby"
}

if (( ! DRY_RUN )); then
  [[ -f "$ROS_SETUP" ]] || die "ROS setup not found: $ROS_SETUP"
  [[ -d "$DIFF_PLANNER_DIR" ]] || die "Diff-planner dir not found: $DIFF_PLANNER_DIR"
  [[ -f "$DIFF_PLANNER_DIR/devel/setup.zsh" ]] || die "workspace setup not found: $DIFF_PLANNER_DIR/devel/setup.zsh"

  mkdir -p "$LOG_DIR" "$DIFF_PLANNER_DIR/Log"
  source "$ROS_SETUP"
  source "$DIFF_PLANNER_DIR/devel/setup.zsh"
  export DRONE_ID="$DRONE_ID_VALUE"
  cd "$DIFF_PLANNER_DIR"
else
  print "[dry-run] no ROS files are sourced and no launch commands are executed"
fi

typeset -a mavros_cmd
mavros_cmd=(roslaunch mavros px4.launch)
if [[ -n "$FCU_URL" ]]; then
  mavros_cmd+=("fcu_url:=$FCU_URL")
fi

launch_bg mavros 6 "${mavros_cmd[@]}"
wait_for_node /mavros 20
wait_for_mavros_connected
wait_for_topic_once /mavros/imu/data 10
send_mavlink_stream_requests

launch_bg faster_lio 10 roslaunch faster_lio mapping_mid360.launch
wait_for_node /laserMapping 30
wait_for_topic_once /laserMapping/odometry 20
wait_for_topic_once /laserMapping/cloud_registered 20

launch_bg ekf 5 roslaunch ekf ekf_lidar.launch
wait_for_node /ekf 20
wait_for_topic_once /ekf/ekf_odom 20

if [[ "$STAGE" == "localization" ]]; then
  print "[ready] localization stage is running. Press Ctrl-C to stop launched processes."
  (( DRY_RUN )) && exit 0
  wait
  exit 0
fi

launch_bg diff_planner 3 roslaunch diff_planner run_exp_single_lio.launch
wait_for_node /drone_0_diff_planner_node 20
wait_for_node /drone_0_traj_server 20
wait_for_topic_once /drone_0_diff_planner_node/grid_map/occupancy_inflate 20
expect_no_message /goal 5
expect_no_message /move_base_simple/goal 5
expect_no_message /back_trigger 5
expect_no_message /px4ctrl/takeoff_land 5
expect_no_message /setpoints_cmd 5

if [[ "$STAGE" == "planner" ]]; then
  print "[ready] planner stage is running. px4ctrl and multipoint were not launched."
  print "[next] For standby control only, rerun with: $SCRIPT_NAME --stage control-standby"
  (( DRY_RUN )) && exit 0
  wait
  exit 0
fi

print_control_precheck
launch_bg px4ctrl 3 roslaunch px4ctrl run_ctrl_lio.launch
wait_for_node /px4ctrl 20
expect_no_message /setpoints_cmd 5
expect_no_message /px4ctrl/takeoff_land 5

launch_bg multipoint 2 roslaunch multipoint multipointplan_exp_lio.launch
wait_for_node /multipointplan 20
expect_no_message /goal 5
expect_no_message /move_base_simple/goal 5
expect_no_message /back_trigger 5
expect_no_message /px4ctrl/takeoff_land 5
expect_no_message /setpoints_cmd 5

print "[ready] control-standby stage is running. Do not move CH8 unless the flight area is ready."
(( DRY_RUN )) && exit 0
wait
