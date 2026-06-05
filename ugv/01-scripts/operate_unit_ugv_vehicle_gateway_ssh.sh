#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOCAL_TARGET_MAP="${UNIT_UGV_LOCAL_TARGET_MAP:-$HOME/changxin_gateway_runtime/unit_ugv_targets.json}"
REMOTE="${UNIT_UGV_SSH_REMOTE:-yhs@192.168.0.201}"
REMOTE_REPO_DIR="${UNIT_UGV_REMOTE_REPO:-/home/yhs/changxin-code}"
REMOTE_TARGET_MAP="${UNIT_UGV_REMOTE_TARGET_MAP:-/home/yhs/changxin_gateway_runtime/unit_ugv_targets.json}"
REMOTE_STATE_DIR="${UNIT_UGV_REMOTE_STATE_DIR:-/home/yhs/changxin_gateway_runtime/gateway_state}"
BRANCH="${UNIT_UGV_REPO_BRANCH:-codex/phase2b-no-hardware-reporting}"
ACTION="status"
DRY_RUN=0
SSH_OPTS=()
REMOTE_SCRIPT_REL="ugv/01-scripts/start_unit_ugv_vehicle_gateway.sh"
VEHICLE_ARGS=()

usage() {
  cat <<'EOF'
Usage:
  operate_unit_ugv_vehicle_gateway_ssh.sh [action] [options] [-- vehicle-script-options]

4060/HMI-side SSH controller for the vehicle-side UGV gateway lifecycle. It
executes the wrapper lifecycle script on the vehicle through SSH; the gateway
process still runs on the UGV IPC / vehicle-local ROS machine.

Actions:
  ping          Check SSH connectivity
  pull          Run git fetch/checkout/pull on the vehicle repo
  sync-lite     Copy the repo subset needed for the vehicle gateway over SSH
  sync-target-map
                Copy the local HMI target map to the vehicle target-map path
  precheck      Run vehicle-side precheck
  command       Print vehicle-side wrapper command
  start         Start vehicle-side wrapper without move_base enablement by default
  start-motion  Start vehicle-side wrapper with operator approval + move_base enabled
  stop          Stop vehicle-side wrapper
  restart       Restart vehicle-side wrapper
  status        Print vehicle-side status
  signature     Capture vehicle-side service list/type/args
  logs          Print vehicle-side wrapper logs

Options:
  --remote USER@HOST          SSH target. Default: yhs@192.168.0.201
  --remote-repo DIR           Remote changxin-code path. Default: /home/yhs/changxin-code
  --remote-target-map FILE    Remote UnitUgvTargetMap.v1 path
  --remote-state-dir DIR      Remote gateway state dir
  --branch NAME               Branch for pull action. Default: codex/phase2b-no-hardware-reporting
  --local-repo DIR            Local repo to sync from. Default: script repo root
  --local-target-map FILE     Local target map copied by sync-target-map
  --ssh-option OPT            Extra ssh option, repeatable. Example: --ssh-option StrictHostKeyChecking=no
  --dry-run                   Print SSH/scp/tar commands without executing
  -h, --help                  Show this help

Everything after `--` is passed to the vehicle lifecycle script.

Examples:
  # 4060: verify remote can run shell commands.
  operate_unit_ugv_vehicle_gateway_ssh.sh ping

  # 4060: sync current gateway code to the vehicle without requiring Codex there.
  operate_unit_ugv_vehicle_gateway_ssh.sh sync-lite

  # 4060: ask vehicle to precheck imports, target map, ROS master, and move_base.
  operate_unit_ugv_vehicle_gateway_ssh.sh precheck -- --enable-move-base --require-move-base-server

  # 4060: start the vehicle-side wrapper, then call dry_run/dispatch separately.
  operate_unit_ugv_vehicle_gateway_ssh.sh start-motion
EOF
}

die() {
  echo "[ERR] $*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    ping|pull|sync-lite|sync-target-map|precheck|command|start|start-motion|stop|restart|status|signature|logs)
      ACTION="$1"
      shift
      ;;
    --remote)
      [[ $# -ge 2 ]] || die "--remote requires a value"
      REMOTE="$2"
      shift 2
      ;;
    --remote-repo)
      [[ $# -ge 2 ]] || die "--remote-repo requires a value"
      REMOTE_REPO_DIR="$2"
      shift 2
      ;;
    --remote-target-map)
      [[ $# -ge 2 ]] || die "--remote-target-map requires a value"
      REMOTE_TARGET_MAP="$2"
      shift 2
      ;;
    --remote-state-dir)
      [[ $# -ge 2 ]] || die "--remote-state-dir requires a value"
      REMOTE_STATE_DIR="$2"
      shift 2
      ;;
    --branch)
      [[ $# -ge 2 ]] || die "--branch requires a value"
      BRANCH="$2"
      shift 2
      ;;
    --local-repo)
      [[ $# -ge 2 ]] || die "--local-repo requires a value"
      LOCAL_REPO_DIR="$2"
      shift 2
      ;;
    --local-target-map)
      [[ $# -ge 2 ]] || die "--local-target-map requires a value"
      LOCAL_TARGET_MAP="$2"
      shift 2
      ;;
    --ssh-option)
      [[ $# -ge 2 ]] || die "--ssh-option requires a value"
      SSH_OPTS+=(-o "$2")
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --)
      shift
      VEHICLE_ARGS+=("$@")
      break
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      VEHICLE_ARGS+=("$1")
      shift
      ;;
  esac
done

REMOTE_SCRIPT="$REMOTE_REPO_DIR/$REMOTE_SCRIPT_REL"

run_ssh() {
  local remote_command="$1"
  local ssh_cmd=(ssh)
  if (( ${#SSH_OPTS[@]} )); then
    ssh_cmd+=("${SSH_OPTS[@]}")
  fi
  ssh_cmd+=("$REMOTE" "$remote_command")
  if (( DRY_RUN )); then
    printf '+'
    printf ' %q' "${ssh_cmd[@]}"
    printf '\n'
    return 0
  fi
  "${ssh_cmd[@]}"
}

run_tar_sync() {
  local paths=(
    AGENTS.md
    docs/superpowers/specs/2026-05-26-unit-execution-agent-runbook.md
    platform_gateway
    task_planning
    tools
    ugv/01-scripts
  )
  if (( DRY_RUN )); then
    printf '+ tar -C %q -czf -' "$LOCAL_REPO_DIR"
    printf ' %q' "${paths[@]}"
    local ssh_cmd=(ssh)
    if (( ${#SSH_OPTS[@]} )); then
      ssh_cmd+=("${SSH_OPTS[@]}")
    fi
    ssh_cmd+=("$REMOTE" "mkdir -p '$REMOTE_REPO_DIR' && tar -xzf - -C '$REMOTE_REPO_DIR'")
    printf ' |'
    printf ' %q' "${ssh_cmd[@]}"
    printf '\n'
    return 0
  fi
  local ssh_cmd=(ssh)
  if (( ${#SSH_OPTS[@]} )); then
    ssh_cmd+=("${SSH_OPTS[@]}")
  fi
  ssh_cmd+=("$REMOTE" "mkdir -p '$REMOTE_REPO_DIR' && tar -xzf - -C '$REMOTE_REPO_DIR'")
  tar -C "$LOCAL_REPO_DIR" -czf - "${paths[@]}" \
    | "${ssh_cmd[@]}"
}

run_target_map_sync() {
  local remote_dir
  remote_dir="$(dirname "$REMOTE_TARGET_MAP")"
  local ssh_cmd=(ssh)
  local scp_cmd=(scp)
  if (( ${#SSH_OPTS[@]} )); then
    ssh_cmd+=("${SSH_OPTS[@]}")
    scp_cmd+=("${SSH_OPTS[@]}")
  fi
  ssh_cmd+=("$REMOTE" "mkdir -p '$remote_dir'")
  scp_cmd+=("$LOCAL_TARGET_MAP" "$REMOTE:$REMOTE_TARGET_MAP")
  if (( DRY_RUN )); then
    printf '+'
    printf ' %q' "${ssh_cmd[@]}"
    printf '\n+'
    printf ' %q' "${scp_cmd[@]}"
    printf '\n'
    return 0
  fi
  [[ -f "$LOCAL_TARGET_MAP" ]] || die "local target map not found: $LOCAL_TARGET_MAP"
  "${ssh_cmd[@]}"
  "${scp_cmd[@]}"
}

remote_vehicle_command() {
  local action="$1"
  shift || true
  local cmd=(
    "$REMOTE_SCRIPT"
    "$action"
    --repo-dir "$REMOTE_REPO_DIR"
    --target-map "$REMOTE_TARGET_MAP"
    --state-dir "$REMOTE_STATE_DIR"
  )
  if (( $# )); then
    cmd+=("$@")
  fi
  if (( ${#VEHICLE_ARGS[@]} )); then
    cmd+=("${VEHICLE_ARGS[@]}")
  fi
  printf 'bash -lc '
  printf '%q' "$(printf '%q ' "${cmd[@]}")"
}

case "$ACTION" in
  ping)
    run_ssh 'hostname; whoami; pwd'
    ;;
  pull)
    run_ssh "cd '$REMOTE_REPO_DIR' && git fetch origin && git checkout '$BRANCH' && git pull --ff-only origin '$BRANCH'"
    ;;
  sync-lite)
    run_tar_sync
    ;;
  sync-target-map)
    run_target_map_sync
    ;;
  precheck|command|start|start-motion|stop|restart|status|signature|logs)
    run_ssh "$(remote_vehicle_command "$ACTION")"
    ;;
  *)
    die "unsupported action: $ACTION"
    ;;
esac
