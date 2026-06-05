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
SSH_BATCH_MODE="${UNIT_UGV_SSH_BATCH_MODE:-1}"
SSH_CONNECT_TIMEOUT_S="${UNIT_UGV_SSH_CONNECT_TIMEOUT_S:-8}"
SSH_SERVER_ALIVE_INTERVAL_S="${UNIT_UGV_SSH_SERVER_ALIVE_INTERVAL_S:-5}"
SSH_SERVER_ALIVE_COUNT_MAX="${UNIT_UGV_SSH_SERVER_ALIVE_COUNT_MAX:-1}"
SSH_IDENTITY_FILE="${UNIT_UGV_SSH_IDENTITY_FILE:-}"
SSH_PASSWORD_ENV_NAME="${UNIT_UGV_SSH_PASSWORD_ENV:-UNIT_UGV_SSH_PASSWORD}"
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
  auth-check    Non-interactive SSH authentication check
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
  runtime-probe Run vehicle-side read-only runtime probe
  logs          Print vehicle-side wrapper logs

Options:
  --remote USER@HOST          SSH target. Default: yhs@192.168.0.201
  --remote-repo DIR           Remote changxin-code path. Default: /home/yhs/changxin-code
  --remote-target-map FILE    Remote UnitUgvTargetMap.v1 path
  --remote-state-dir DIR      Remote gateway state dir
  --branch NAME               Branch for pull action. Default: codex/phase2b-no-hardware-reporting
  --local-repo DIR            Local repo to sync from. Default: script repo root
  --local-target-map FILE     Local target map copied by sync-target-map
  --ssh-identity FILE         Private key for vehicle SSH
  --ssh-password-env NAME     Env var containing SSH password. Default: UNIT_UGV_SSH_PASSWORD
  --ssh-option OPT            Extra ssh option, repeatable. Example: --ssh-option StrictHostKeyChecking=no
  --connect-timeout-s SEC     SSH connect timeout. Default: 8
  --interactive-ssh           Allow password prompts. Do not use from unattended Codex runs.
  --dry-run                   Print SSH/scp/tar commands without executing
  -h, --help                  Show this help

Everything after `--` is passed to the vehicle lifecycle script.

Examples:
  # 4060: verify remote can run shell commands.
  operate_unit_ugv_vehicle_gateway_ssh.sh auth-check

  # 4060: use password auth without writing the password into files or args.
  export UNIT_UGV_SSH_PASSWORD='<vehicle-password>'
  operate_unit_ugv_vehicle_gateway_ssh.sh auth-check
  unset UNIT_UGV_SSH_PASSWORD

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
    ping|auth-check|pull|sync-lite|sync-target-map|precheck|command|start|start-motion|stop|restart|status|signature|runtime-probe|logs)
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
    --ssh-identity)
      [[ $# -ge 2 ]] || die "--ssh-identity requires a value"
      SSH_IDENTITY_FILE="$2"
      shift 2
      ;;
    --ssh-password-env)
      [[ $# -ge 2 ]] || die "--ssh-password-env requires a value"
      SSH_PASSWORD_ENV_NAME="$2"
      shift 2
      ;;
    --ssh-option)
      [[ $# -ge 2 ]] || die "--ssh-option requires a value"
      SSH_OPTS+=(-o "$2")
      shift 2
      ;;
    --connect-timeout-s)
      [[ $# -ge 2 ]] || die "--connect-timeout-s requires a value"
      SSH_CONNECT_TIMEOUT_S="$2"
      shift 2
      ;;
    --interactive-ssh)
      SSH_BATCH_MODE=0
      shift
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
SSH_PASSWORD_VALUE="$(printenv "$SSH_PASSWORD_ENV_NAME" 2>/dev/null || true)"
USE_SSHPASS=0
if [[ -n "$SSH_PASSWORD_VALUE" ]]; then
  USE_SSHPASS=1
  SSH_BATCH_MODE=0
  if (( ! DRY_RUN )); then
    command -v sshpass >/dev/null 2>&1 || die "sshpass is required when $SSH_PASSWORD_ENV_NAME is set"
  fi
fi

BASE_SSH_OPTS=()
if (( SSH_BATCH_MODE )); then
  BASE_SSH_OPTS+=(-o BatchMode=yes)
fi
BASE_SSH_OPTS+=(
  -o "ConnectTimeout=$SSH_CONNECT_TIMEOUT_S"
  -o "ServerAliveInterval=$SSH_SERVER_ALIVE_INTERVAL_S"
  -o "ServerAliveCountMax=$SSH_SERVER_ALIVE_COUNT_MAX"
)
if [[ -n "$SSH_IDENTITY_FILE" ]]; then
  BASE_SSH_OPTS+=(-i "$SSH_IDENTITY_FILE")
fi
if (( ${#SSH_OPTS[@]} )); then
  BASE_SSH_OPTS+=("${SSH_OPTS[@]}")
fi

make_ssh_cmd() {
  local remote_command="$1"
  SSH_CMD=(ssh)
  if (( ${#BASE_SSH_OPTS[@]} )); then
    SSH_CMD+=("${BASE_SSH_OPTS[@]}")
  fi
  SSH_CMD+=("$REMOTE" "$remote_command")
  if (( USE_SSHPASS )); then
    SSH_CMD=(env "SSHPASS=$SSH_PASSWORD_VALUE" sshpass -e "${SSH_CMD[@]}")
  fi
}

make_scp_cmd() {
  local source_path="$1"
  local target_path="$2"
  SCP_CMD=(scp)
  if (( ${#BASE_SSH_OPTS[@]} )); then
    SCP_CMD+=("${BASE_SSH_OPTS[@]}")
  fi
  SCP_CMD+=("$source_path" "$target_path")
  if (( USE_SSHPASS )); then
    SCP_CMD=(env "SSHPASS=$SSH_PASSWORD_VALUE" sshpass -e "${SCP_CMD[@]}")
  fi
}

print_redacted_cmd() {
  local redacted=()
  local arg
  for arg in "$@"; do
    if [[ "$arg" == SSHPASS=* ]]; then
      redacted+=("SSHPASS=***")
    else
      redacted+=("$arg")
    fi
  done
  printf '+'
  printf ' %q' "${redacted[@]}"
  printf '\n'
}

run_ssh() {
  local remote_command="$1"
  make_ssh_cmd "$remote_command"
  if (( DRY_RUN )); then
    print_redacted_cmd "${SSH_CMD[@]}"
    return 0
  fi
  "${SSH_CMD[@]}"
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
    make_ssh_cmd "mkdir -p '$REMOTE_REPO_DIR' && tar -xzf - -C '$REMOTE_REPO_DIR'"
    printf ' |'
    local redacted=()
    local arg
    for arg in "${SSH_CMD[@]}"; do
      if [[ "$arg" == SSHPASS=* ]]; then
        redacted+=("SSHPASS=***")
      else
        redacted+=("$arg")
      fi
    done
    printf ' %q' "${redacted[@]}"
    printf '\n'
    return 0
  fi
  make_ssh_cmd "mkdir -p '$REMOTE_REPO_DIR' && tar -xzf - -C '$REMOTE_REPO_DIR'"
  tar -C "$LOCAL_REPO_DIR" -czf - "${paths[@]}" \
    | "${SSH_CMD[@]}"
}

run_target_map_sync() {
  local remote_dir
  remote_dir="$(dirname "$REMOTE_TARGET_MAP")"
  make_ssh_cmd "mkdir -p '$remote_dir'"
  make_scp_cmd "$LOCAL_TARGET_MAP" "$REMOTE:$REMOTE_TARGET_MAP"
  if (( DRY_RUN )); then
    print_redacted_cmd "${SSH_CMD[@]}"
    print_redacted_cmd "${SCP_CMD[@]}"
    return 0
  fi
  [[ -f "$LOCAL_TARGET_MAP" ]] || die "local target map not found: $LOCAL_TARGET_MAP"
  "${SSH_CMD[@]}"
  "${SCP_CMD[@]}"
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
  auth-check)
    run_ssh 'echo ssh_auth_ok; hostname; whoami; pwd'
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
  precheck|command|start|start-motion|stop|restart|status|signature|runtime-probe|logs)
    run_ssh "$(remote_vehicle_command "$ACTION")"
    ;;
  *)
    die "unsupported action: $ACTION"
    ;;
esac
