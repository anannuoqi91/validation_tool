#!/usr/bin/env bash
set -Eeuo pipefail

########################################
# 配置 & 状态文件
########################################
STATE_DIR="${HOME}/.local/state/docker_force_restart"
LOG_FILE="${STATE_DIR}/force_restart.log"
PID_FILE="${STATE_DIR}/force_restart.pid"
LOCK_FILE="${STATE_DIR}/force_restart.lock"
mkdir -p "${STATE_DIR}"

log() { printf "[%s] %s\n" "$(date '+%F %T')" "$*" >>"${LOG_FILE}"; }

DOCKER_BIN="$(command -v docker || true)"
SUDO_BIN="$(command -v sudo || true)"
SUDO_MODE=0

usage() {
  cat <<EOF
用法：
  $0 start  -c <name> [-c <name2> ...] -t <sec> [--sudo]
  $0 run    -c <name> [-c <name2> ...] -t <sec> [--sudo]
  $0 stop
  $0 status

参数：
  -c, --container   容器名（可多次指定；也支持逗号分隔：-c "a,b,c"）
  -t, --interval    强制重启周期（秒）：每隔N秒“触发一次”重启（不受重启耗时影响）
  --sudo            docker 命令使用 sudo：启动时提示输入一次密码（不保存密码，使用 sudo 缓存）
  -h, --help        帮助

示例：
  $0 start -c OmniVidi_VL -c city-admin -t 300
  $0 start -c "OmniVidi_VL,city-admin" -t 120 --sudo

说明：
  - 多容器同一时刻并行触发重启（不会出现容器之间的等待间隔）
  - 严格按周期触发：不会因为 docker restart 阻塞导致周期变长
  - 为避免同一容器重启堆叠：若上一次重启未结束，会 SKIP 本轮该容器
日志：
  ${LOG_FILE}
EOF
}

########################################
# sudo 预授权 & keepalive（不保存密码）
########################################
sudo_preauth() {
  if [[ "${SUDO_MODE}" != "1" ]]; then return 0; fi
  [[ -n "${SUDO_BIN}" ]] || { echo "指定了 --sudo 但找不到 sudo"; exit 1; }
  echo "需要 sudo 权限执行 docker 命令，请输入一次 sudo 密码（不会保存密码）："
  sudo -v
}

SUDO_KEEPALIVE_PID=""
start_sudo_keepalive() {
  if [[ "${SUDO_MODE}" != "1" ]]; then return 0; fi
  (
    while true; do
      # -n 非交互，避免后台卡住；如果失效会记日志
      if ! sudo -n -v >/dev/null 2>&1; then
        log "WARN: sudo 凭证可能已失效（需要重新 start/run 并输入密码）"
      fi
      sleep 60
    done
  ) &
  SUDO_KEEPALIVE_PID="$!"
}

stop_sudo_keepalive() {
  if [[ -n "${SUDO_KEEPALIVE_PID}" ]]; then
    kill "${SUDO_KEEPALIVE_PID}" >/dev/null 2>&1 || true
  fi
}

########################################
# docker 命令封装
########################################
docker_cmd() {
  if [[ "${SUDO_MODE}" == "1" ]]; then
    # -n 确保后台不会卡住等待密码
    "${SUDO_BIN}" -n "${DOCKER_BIN}" "$@"
  else
    "${DOCKER_BIN}" "$@"
  fi
}

docker_ok() { docker_cmd info >/dev/null 2>&1; }

safe_name() { echo "$1" | sed 's/[^a-zA-Z0-9_.-]/_/g'; }

container_exists() {
  local name="$1"
  docker_cmd ps -a --format '{{.Names}}' 2>/dev/null | grep -Fxq "$name"
}

########################################
# 单容器后台重启（带锁：避免重启叠加）
########################################
restart_one_bg() {
  local name="$1"
  local safe; safe="$(safe_name "$name")"
  local c_lock="${STATE_DIR}/container.${safe}.lock"

  (
    exec 8>"$c_lock"
    if ! flock -n 8; then
      log "SKIP: ${name} 上一次重启尚未结束（锁占用）"
      exit 0
    fi

    if ! container_exists "$name"; then
      log "WARN: 容器不存在：${name}（跳过）"
      exit 0
    fi

    log "ACTION: docker restart ${name}"
    if docker_cmd restart "$name" >/dev/null 2>&1; then
      log "OK: ${name} 已重启"
    else
      log "ERROR: ${name} 重启失败（权限/daemon/requiretty/凭证过期等）"
      exit 1
    fi
  ) &
}

########################################
# 严格周期调度：每隔 N 秒触发一次（不受重启耗时影响）
########################################
loop_restart_strict() {
  local interval="$1"; shift
  local -a containers=("$@")

  log "START: containers=${containers[*]} interval=${interval}s sudo=${SUDO_MODE}"

  local start_ts next_tick now sleep_sec
  start_ts="$(date +%s)"
  next_tick="$start_ts"

  trap 'stop_sudo_keepalive' EXIT
  start_sudo_keepalive

  while true; do
    now="$(date +%s)"
    if (( now >= next_tick )); then
      # 追赶：避免系统阻塞错过多个 tick 导致漂移
      while (( next_tick <= now )); do
        next_tick=$(( next_tick + interval ))
      done

      if ! docker_ok; then
        log "WARN: docker 不可用（docker info失败），本轮只计时不重启"
      else
        log "TICK: $(date '+%F %T') trigger"
        for c in "${containers[@]}"; do
          restart_one_bg "$c"
        done
      fi
    fi

    now="$(date +%s)"
    sleep_sec=$(( next_tick - now ))
    (( sleep_sec < 1 )) && sleep_sec=1
    sleep "$sleep_sec"
  done
}

########################################
# 前后台控制
########################################
stop_bg() {
  if [[ ! -f "${PID_FILE}" ]]; then
    echo "未运行"
    exit 0
  fi
  local pid
  pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
    kill "${pid}" || true
    echo "已停止，PID=${pid}"
  else
    echo "PID=${pid} 不存在或已退出"
  fi
  rm -f "${PID_FILE}"
}

status_bg() {
  if [[ -f "${PID_FILE}" ]]; then
    local pid
    pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
      echo "运行中，PID=${pid}"
      echo "日志: ${LOG_FILE}"
      exit 0
    fi
  fi
  echo "未运行"
  echo "日志: ${LOG_FILE}"
}

start_bg() {
  local interval="$1"; shift
  local -a containers=("$@")

  # 先前台拿到 sudo 凭证（若需要），避免后台无TTY无法输入密码
  sudo_preauth

  # 防重复启动
  if [[ -f "${PID_FILE}" ]]; then
    local oldpid
    oldpid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    if [[ -n "${oldpid}" ]] && kill -0 "${oldpid}" >/dev/null 2>&1; then
      echo "已在运行，PID=${oldpid}"
      echo "日志: ${LOG_FILE}"
      exit 0
    fi
  fi

  # 全局锁，避免多实例
  exec 9>"${LOCK_FILE}"
  if ! flock -n 9; then
    echo "启动失败：已有实例持有锁 ${LOCK_FILE}"
    exit 1
  fi

  # 组装参数（数组传参不丢引号）
  local -a args=(run -t "${interval}")
  for c in "${containers[@]}"; do args+=(-c "$c"); done
  [[ "${SUDO_MODE}" == "1" ]] && args+=(--sudo)

  nohup "$0" "${args[@]}" >>"${LOG_FILE}" 2>&1 &
  local pid=$!
  echo "${pid}" > "${PID_FILE}"
  disown "${pid}" 2>/dev/null || true
  echo "已后台启动，PID=${pid}"
  echo "日志: ${LOG_FILE}"
}

########################################
# main：stop/status 先处理（不解析 -c/-t）
########################################
MODE="${1:-}"
shift || true

case "${MODE}" in
  stop)
    stop_bg
    exit 0
    ;;
  status)
    status_bg
    exit 0
    ;;
  -h|--help|"")
    usage
    exit 0
    ;;
  start|run)
    : ;;  # 继续往下解析参数
  *)
    echo "未知命令：${MODE}"
    usage
    exit 1
    ;;
esac

# 只有 start/run 才会走到这里：解析参数
declare -a CONTAINERS=()
INTERVAL_SEC=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -c|--container)
      [[ $# -lt 2 ]] && { echo "缺少参数：$1"; usage; exit 1; }
      IFS=',' read -r -a tmp <<< "$2"
      for x in "${tmp[@]}"; do
        x="${x// /}"
        [[ -n "$x" ]] && CONTAINERS+=("$x")
      done
      shift 2
      ;;
    -t|--interval)
      [[ $# -lt 2 ]] && { echo "缺少参数：$1"; usage; exit 1; }
      INTERVAL_SEC="$2"
      shift 2
      ;;
    --sudo)
      SUDO_MODE=1
      shift
      ;;
    *)
      echo "未知参数：$1"
      usage
      exit 1
      ;;
  esac
done

# 参数校验
[[ -n "${DOCKER_BIN}" ]] || { echo "找不到 docker 命令"; exit 1; }
if [[ "${#CONTAINERS[@]}" -eq 0 ]]; then
  echo "必须指定至少一个容器：-c <name>"
  usage
  exit 1
fi
if [[ -z "${INTERVAL_SEC}" ]] || ! [[ "${INTERVAL_SEC}" =~ ^[0-9]+$ ]] || (( INTERVAL_SEC < 1 )); then
  echo "必须指定 -t 为正整数秒"
  usage
  exit 1
fi
if [[ "${SUDO_MODE}" == "1" ]] && [[ -z "${SUDO_BIN}" ]]; then
  echo "指定了 --sudo 但找不到 sudo 命令"
  exit 1
fi

case "${MODE}" in
  start)
    start_bg "${INTERVAL_SEC}" "${CONTAINERS[@]}"
    ;;
  run)
    sudo_preauth
    exec 9>"${LOCK_FILE}"
    flock -n 9 || { echo "已有实例在运行（锁：${LOCK_FILE}）"; exit 1; }
    loop_restart_strict "${INTERVAL_SEC}" "${CONTAINERS[@]}"
    ;;
esac
