#!/usr/bin/env bash
set -euo pipefail

CURRENT_CONTAINER="${VISIONFLOW_AWS_CURRENT_CONTAINER:-visionflow-backend-cloud}"
SMOKE_CONTAINER="${VISIONFLOW_AWS_SMOKE_CONTAINER:-visionflow-backend-cloud-smoke}"
NETWORK_NAME="${VISIONFLOW_AWS_NETWORK_NAME:-visionflow-cloud}"
PUBLIC_PORT="${VISIONFLOW_AWS_PUBLIC_PORT:-8080}"
SMOKE_PORT="${VISIONFLOW_AWS_SMOKE_PORT:-18080}"
CONTAINER_PORT="${VISIONFLOW_AWS_CONTAINER_PORT:-8080}"
ENV_FILE="${VISIONFLOW_AWS_ENV_FILE:-/home/ubuntu/visionflow-cloud/.env}"
ROLLBACK_ROOT="${VISIONFLOW_AWS_ROLLBACK_ROOT:-/home/ubuntu/visionflow-cloud/rollback}"
CURRENT_HEALTH_URL="http://127.0.0.1:${PUBLIC_PORT}/actuator/health"
SMOKE_HEALTH_URL="http://127.0.0.1:${SMOKE_PORT}/actuator/health"
EVENT_LOG_MARKER="VISIONFLOW_PHASE3_EVENT_INGEST"
DEPTH_LOG_MARKER="VISIONFLOW_PHASE3_DEPTH_ENRICH"

CANDIDATE_IMAGE="${CANDIDATE_IMAGE:-}"
EXPECTED_DIGEST="${EXPECTED_DIGEST:-}"
CANDIDATE_IMAGE_ID=""
PROMOTION_ENV_FILE=""

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'ERROR=%s\n' "$*" >&2
  exit 2
}

require_root() {
  [[ "${EUID}" -eq 0 ]] || fail "Run with sudo/root privileges"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

container_exists() {
  docker inspect "$1" >/dev/null 2>&1
}

container_running() {
  [[ "$(docker inspect --format '{{.State.Status}}' "$1" 2>/dev/null || true)" == "running" ]]
}

read_env_value() {
  local key="$1"
  local line
  [[ -r "$ENV_FILE" ]] || fail "Environment file is not readable: $ENV_FILE"
  line="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 || true)"
  printf '%s' "${line#*=}"
}

load_release_metadata() {
  if [[ -z "$CANDIDATE_IMAGE" ]]; then
    CANDIDATE_IMAGE="$(read_env_value VISIONFLOW_BACKEND_IMAGE)"
  fi
  if [[ -z "$EXPECTED_DIGEST" ]]; then
    EXPECTED_DIGEST="$(read_env_value VISIONFLOW_BACKEND_EXPECTED_DIGEST)"
  fi

  [[ -n "$CANDIDATE_IMAGE" ]] || fail "VISIONFLOW_BACKEND_IMAGE is missing"
  [[ -n "$EXPECTED_DIGEST" ]] || fail "VISIONFLOW_BACKEND_EXPECTED_DIGEST is missing"
  [[ "$CANDIDATE_IMAGE" =~ :backend-sha-[0-9a-f]{7,40}$ ]] \
    || fail "Candidate image must use an immutable backend-sha-<commit> tag: $CANDIDATE_IMAGE"
  [[ "$EXPECTED_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] \
    || fail "Expected digest must be sha256:<64 lowercase hex chars>"
}

verify_candidate_release() {
  local repo_digest

  docker pull "$CANDIDATE_IMAGE" >/dev/null
  repo_digest="$({
    docker image inspect "$CANDIDATE_IMAGE" \
      --format '{{range .RepoDigests}}{{println .}}{{end}}' 2>/dev/null || true
  } | grep -F "@${EXPECTED_DIGEST}" | head -n 1 || true)"

  [[ -n "$repo_digest" ]] || {
    docker image inspect "$CANDIDATE_IMAGE" \
      --format '{{range .RepoDigests}}{{println .}}{{end}}' >&2 || true
    fail "Candidate image digest does not match expected digest"
  }

  CANDIDATE_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$CANDIDATE_IMAGE")"
  [[ -n "$CANDIDATE_IMAGE_ID" ]] || fail "Candidate image ID could not be resolved"
}

wait_for_health() {
  local url="$1"
  local attempts="${2:-60}"
  local delay_seconds="${3:-2}"
  local i

  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS --max-time 5 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$delay_seconds"
  done
  return 1
}

make_runtime_env_file() {
  PROMOTION_ENV_FILE="$(mktemp /tmp/visionflow-backend-runtime.XXXXXX.env)"
  chmod 600 "$PROMOTION_ENV_FILE"
  docker inspect "$CURRENT_CONTAINER" \
    --format '{{range .Config.Env}}{{println .}}{{end}}' > "$PROMOTION_ENV_FILE"
}

cleanup_runtime_env_file() {
  if [[ -n "$PROMOTION_ENV_FILE" ]]; then
    rm -f "$PROMOTION_ENV_FILE"
    PROMOTION_ENV_FILE=""
  fi
}

write_container_runtime_metadata() {
  local container="$1"
  local output="$2"

  {
    printf 'CONTAINER=%s\n' "$container"
    docker inspect --format 'IMAGE_REF={{.Config.Image}}' "$container"
    docker inspect --format 'IMAGE_ID={{.Image}}' "$container"
    docker inspect --format 'STATUS={{.State.Status}}' "$container"
    docker inspect --format 'RESTART_POLICY={{.HostConfig.RestartPolicy.Name}}' "$container"
    docker inspect --format 'NETWORK={{.HostConfig.NetworkMode}}' "$container"
    docker inspect --format 'PORT_BINDINGS={{json .HostConfig.PortBindings}}' "$container"
    docker inspect --format 'MEMORY_BYTES={{.HostConfig.Memory}}' "$container"
    docker inspect --format 'MEMORY_SWAP_BYTES={{.HostConfig.MemorySwap}}' "$container"
    docker inspect --format 'MOUNT_COUNT={{len .Mounts}}' "$container"
  } > "$output"
  chmod 600 "$output"
}

write_candidate_image_metadata() {
  local output="$1"

  {
    printf 'IMAGE_REF=%s\n' "$CANDIDATE_IMAGE"
    printf 'EXPECTED_DIGEST=%s\n' "$EXPECTED_DIGEST"
    docker image inspect --format 'IMAGE_ID={{.Id}}' "$CANDIDATE_IMAGE"
    docker image inspect --format 'REPO_TAGS={{json .RepoTags}}' "$CANDIDATE_IMAGE"
    docker image inspect --format 'REPO_DIGESTS={{json .RepoDigests}}' "$CANDIDATE_IMAGE"
    docker image inspect --format 'CREATED={{.Created}}' "$CANDIDATE_IMAGE"
  } > "$output"
  chmod 600 "$output"
}

assert_supported_current_runtime() {
  local network restart_policy mount_count port_bindings

  network="$(docker inspect --format '{{.HostConfig.NetworkMode}}' "$CURRENT_CONTAINER")"
  restart_policy="$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$CURRENT_CONTAINER")"
  mount_count="$(docker inspect --format '{{len .Mounts}}' "$CURRENT_CONTAINER")"
  port_bindings="$(docker inspect --format '{{json .HostConfig.PortBindings}}' "$CURRENT_CONTAINER")"

  [[ "$network" == "$NETWORK_NAME" ]] \
    || fail "Current backend network is unsupported: $network"
  [[ "$restart_policy" == "unless-stopped" ]] \
    || fail "Current backend restart policy must be unless-stopped: $restart_policy"
  [[ "$mount_count" == "0" ]] \
    || fail "Current backend has mounts that promotion would not preserve: $mount_count"
  grep -Fq "\"HostPort\":\"${PUBLIC_PORT}\"" <<<"$port_bindings" \
    || fail "Current backend does not publish expected host port ${PUBLIC_PORT}"
}

assert_supported_smoke_runtime() {
  local network restart_policy image_id port_bindings

  network="$(docker inspect --format '{{.HostConfig.NetworkMode}}' "$SMOKE_CONTAINER")"
  restart_policy="$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$SMOKE_CONTAINER")"
  image_id="$(docker inspect --format '{{.Image}}' "$SMOKE_CONTAINER")"
  port_bindings="$(docker inspect --format '{{json .HostConfig.PortBindings}}' "$SMOKE_CONTAINER")"

  [[ "$network" == "$NETWORK_NAME" ]] \
    || fail "Smoke backend network is unsupported: $network"
  [[ "$restart_policy" == "no" ]] \
    || fail "Smoke backend restart policy must be no: $restart_policy"
  [[ "$image_id" == "$CANDIDATE_IMAGE_ID" ]] \
    || fail "Smoke backend image ID does not match candidate image ID"
  grep -Fq '"HostIp":"127.0.0.1"' <<<"$port_bindings" \
    || fail "Smoke backend must bind only to 127.0.0.1"
  grep -Fq "\"HostPort\":\"${SMOKE_PORT}\"" <<<"$port_bindings" \
    || fail "Smoke backend does not publish expected host port ${SMOKE_PORT}"
}

prepare_smoke() {
  local memory memory_swap
  local -a resource_args=()

  require_root
  load_release_metadata
  verify_candidate_release

  container_exists "$CURRENT_CONTAINER" || fail "Current backend container not found: $CURRENT_CONTAINER"
  container_running "$CURRENT_CONTAINER" || fail "Current backend is not running: $CURRENT_CONTAINER"
  assert_supported_current_runtime
  wait_for_health "$CURRENT_HEALTH_URL" 60 2 \
    || fail "Current backend health did not become UP"

  if container_exists "$SMOKE_CONTAINER"; then
    fail "Smoke container already exists; remove it explicitly before preparing a new smoke: $SMOKE_CONTAINER"
  fi

  memory="$(docker inspect --format '{{.HostConfig.Memory}}' "$CURRENT_CONTAINER")"
  memory_swap="$(docker inspect --format '{{.HostConfig.MemorySwap}}' "$CURRENT_CONTAINER")"
  if [[ "$memory" != "0" ]]; then
    resource_args+=(--memory "${memory}b")
  fi
  if [[ "$memory_swap" != "0" && "$memory_swap" != "-1" ]]; then
    resource_args+=(--memory-swap "${memory_swap}b")
  fi

  make_runtime_env_file
  trap cleanup_runtime_env_file EXIT

  docker run -d \
    --name "$SMOKE_CONTAINER" \
    --restart no \
    --network "$NETWORK_NAME" \
    -p "127.0.0.1:${SMOKE_PORT}:${CONTAINER_PORT}" \
    --env-file "$PROMOTION_ENV_FILE" \
    "${resource_args[@]}" \
    "$CANDIDATE_IMAGE" >/dev/null

  if ! wait_for_health "$SMOKE_HEALTH_URL" 60 2; then
    docker logs --tail 120 "$SMOKE_CONTAINER" >&2 || true
    fail "Smoke backend health did not become UP"
  fi

  assert_supported_smoke_runtime
  cleanup_runtime_env_file
  trap - EXIT

  log "AWS_BACKEND_SMOKE_PREPARE=PASS"
  log "SMOKE_CONTAINER=$SMOKE_CONTAINER"
  log "CANDIDATE_IMAGE=$CANDIDATE_IMAGE"
  log "CANDIDATE_IMAGE_ID=$CANDIDATE_IMAGE_ID"
  log "SMOKE_HEALTH=UP"
}

preflight() {
  local current_image restart_policy smoke_logs

  require_root
  load_release_metadata
  verify_candidate_release

  container_exists "$CURRENT_CONTAINER" || fail "Current backend container not found: $CURRENT_CONTAINER"
  container_exists "$SMOKE_CONTAINER" || fail "Smoke backend container not found: $SMOKE_CONTAINER"
  container_running "$CURRENT_CONTAINER" || fail "Current backend is not running: $CURRENT_CONTAINER"
  container_running "$SMOKE_CONTAINER" || fail "Smoke backend is not running: $SMOKE_CONTAINER"

  assert_supported_current_runtime
  assert_supported_smoke_runtime

  wait_for_health "$CURRENT_HEALTH_URL" 60 2 \
    || fail "Current backend health did not become UP"
  wait_for_health "$SMOKE_HEALTH_URL" 60 2 \
    || fail "Smoke backend health did not become UP"

  smoke_logs="$(docker logs "$SMOKE_CONTAINER" 2>&1 || true)"
  grep -Fq "$EVENT_LOG_MARKER" <<<"$smoke_logs" \
    || fail "Smoke log is missing $EVENT_LOG_MARKER"
  grep -Fq "$DEPTH_LOG_MARKER" <<<"$smoke_logs" \
    || fail "Smoke log is missing $DEPTH_LOG_MARKER"

  current_image="$(docker inspect --format '{{.Config.Image}}' "$CURRENT_CONTAINER")"
  restart_policy="$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$CURRENT_CONTAINER")"

  log "AWS_BACKEND_PROMOTION_PREFLIGHT=PASS"
  log "CURRENT_CONTAINER=$CURRENT_CONTAINER"
  log "CURRENT_IMAGE=$current_image"
  log "CANDIDATE_IMAGE=$CANDIDATE_IMAGE"
  log "CANDIDATE_DIGEST=$EXPECTED_DIGEST"
  log "CANDIDATE_IMAGE_ID=$CANDIDATE_IMAGE_ID"
  log "NETWORK=$NETWORK_NAME"
  log "RESTART_POLICY=$restart_policy"
  log "CURRENT_HEALTH=UP"
  log "SMOKE_HEALTH=UP"
  log "EVENT_LOG_MARKER=PASS"
  log "DEPTH_LOG_MARKER=PASS"
}

promote() {
  local timestamp rollback_dir backup_container current_image current_image_id
  local restart_policy running_image_id memory memory_swap
  local -a resource_args=()

  preflight

  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  rollback_dir="${ROLLBACK_ROOT}/${timestamp}"
  backup_container="${CURRENT_CONTAINER}-rollback-${timestamp}"
  mkdir -p "$rollback_dir"
  chmod 700 "$rollback_dir"

  current_image="$(docker inspect --format '{{.Config.Image}}' "$CURRENT_CONTAINER")"
  current_image_id="$(docker inspect --format '{{.Image}}' "$CURRENT_CONTAINER")"
  restart_policy="$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$CURRENT_CONTAINER")"
  memory="$(docker inspect --format '{{.HostConfig.Memory}}' "$CURRENT_CONTAINER")"
  memory_swap="$(docker inspect --format '{{.HostConfig.MemorySwap}}' "$CURRENT_CONTAINER")"
  if [[ "$memory" != "0" ]]; then
    resource_args+=(--memory "${memory}b")
  fi
  if [[ "$memory_swap" != "0" && "$memory_swap" != "-1" ]]; then
    resource_args+=(--memory-swap "${memory_swap}b")
  fi

  write_container_runtime_metadata \
    "$CURRENT_CONTAINER" "${rollback_dir}/current-container.runtime.txt"
  docker logs --tail 300 "$CURRENT_CONTAINER" > "${rollback_dir}/current-container.log" 2>&1 || true
  chmod 600 "${rollback_dir}/current-container.log"
  write_container_runtime_metadata \
    "$SMOKE_CONTAINER" "${rollback_dir}/smoke-container.runtime.txt"
  docker logs --tail 300 "$SMOKE_CONTAINER" > "${rollback_dir}/smoke-container.log" 2>&1 || true
  chmod 600 "${rollback_dir}/smoke-container.log"
  write_candidate_image_metadata "${rollback_dir}/candidate-image.release.txt"
  cat > "${rollback_dir}/deployment.env" <<META
PROMOTION_TIMESTAMP=$timestamp
CURRENT_CONTAINER=$CURRENT_CONTAINER
CURRENT_IMAGE=$current_image
CURRENT_IMAGE_ID=$current_image_id
CANDIDATE_IMAGE=$CANDIDATE_IMAGE
CANDIDATE_EXPECTED_DIGEST=$EXPECTED_DIGEST
CANDIDATE_IMAGE_ID=$CANDIDATE_IMAGE_ID
NETWORK=$NETWORK_NAME
RESTART_POLICY=$restart_policy
MEMORY_BYTES=$memory
MEMORY_SWAP_BYTES=$memory_swap
META
  chmod 600 "${rollback_dir}/deployment.env"

  make_runtime_env_file
  trap cleanup_runtime_env_file EXIT

  log "PROMOTION_STEP=remove_smoke"
  docker rm -f "$SMOKE_CONTAINER" >/dev/null

  log "PROMOTION_STEP=stop_current"
  docker stop --time 30 "$CURRENT_CONTAINER" >/dev/null

  log "PROMOTION_STEP=preserve_current_as_rollback"
  docker rename "$CURRENT_CONTAINER" "$backup_container"
  docker update --restart=no "$backup_container" >/dev/null

  rollback_automatically() {
    local reason="$1"
    log "PROMOTION_FAILURE=$reason"

    if container_exists "$CURRENT_CONTAINER"; then
      docker logs --tail 300 "$CURRENT_CONTAINER" \
        > "${rollback_dir}/failed-candidate.log" 2>&1 || true
      chmod 600 "${rollback_dir}/failed-candidate.log"
      docker rm -f "$CURRENT_CONTAINER" >/dev/null 2>&1 || true
    fi

    if container_exists "$backup_container"; then
      docker rename "$backup_container" "$CURRENT_CONTAINER"
      docker update --restart="$restart_policy" "$CURRENT_CONTAINER" >/dev/null
      docker start "$CURRENT_CONTAINER" >/dev/null

      if wait_for_health "$CURRENT_HEALTH_URL" 60 2; then
        cleanup_runtime_env_file
        trap - EXIT
        log "AWS_BACKEND_PROMOTION=ROLLED_BACK"
        log "ROLLBACK_CONTAINER=$CURRENT_CONTAINER"
        log "ROLLBACK_IMAGE=$current_image"
        log "ROLLBACK_HEALTH=UP"
        log "ROLLBACK_ARTIFACTS=$rollback_dir"
        exit 1
      fi
    fi

    cleanup_runtime_env_file
    trap - EXIT
    log "AWS_BACKEND_PROMOTION=ROLLBACK_FAILED"
    log "ROLLBACK_ARTIFACTS=$rollback_dir"
    exit 2
  }

  log "PROMOTION_STEP=start_candidate_on_8080"
  if ! docker run -d \
    --name "$CURRENT_CONTAINER" \
    --restart "$restart_policy" \
    --network "$NETWORK_NAME" \
    -p "${PUBLIC_PORT}:${CONTAINER_PORT}" \
    --env-file "$PROMOTION_ENV_FILE" \
    "${resource_args[@]}" \
    "$CANDIDATE_IMAGE" >/dev/null; then
    rollback_automatically "docker run failed"
  fi

  if ! wait_for_health "$CURRENT_HEALTH_URL" 60 2; then
    rollback_automatically "candidate health did not become UP"
  fi

  running_image_id="$(docker inspect --format '{{.Image}}' "$CURRENT_CONTAINER")"
  if [[ "$running_image_id" != "$CANDIDATE_IMAGE_ID" ]]; then
    rollback_automatically "running image ID does not match candidate"
  fi

  write_container_runtime_metadata \
    "$CURRENT_CONTAINER" "${rollback_dir}/promoted-container.runtime.txt"
  docker logs --tail 300 "$CURRENT_CONTAINER" > "${rollback_dir}/promoted-container.log" 2>&1 || true
  chmod 600 "${rollback_dir}/promoted-container.log"

  cleanup_runtime_env_file
  trap - EXIT

  log "AWS_BACKEND_PROMOTION=PASS"
  log "CURRENT_CONTAINER=$CURRENT_CONTAINER"
  log "CURRENT_IMAGE=$CANDIDATE_IMAGE"
  log "CURRENT_IMAGE_ID=$running_image_id"
  log "CURRENT_HEALTH=UP"
  log "BACKUP_CONTAINER=$backup_container"
  log "BACKUP_IMAGE=$current_image"
  log "BACKUP_STATE=stopped"
  log "ROLLBACK_ARTIFACTS=$rollback_dir"
}

rollback() {
  local backup_container="${1:-}"
  local restart_policy timestamp rescue_container

  require_root
  [[ -n "$backup_container" ]] \
    || fail "Usage: sudo bash $0 rollback <backup-container-name>"
  [[ "$backup_container" == "${CURRENT_CONTAINER}-rollback-"* ]] \
    || fail "Backup container name is outside the managed rollback namespace: $backup_container"
  container_exists "$backup_container" \
    || fail "Backup container not found: $backup_container"
  container_exists "$CURRENT_CONTAINER" \
    || fail "Current backend container not found: $CURRENT_CONTAINER"
  container_running "$CURRENT_CONTAINER" \
    || fail "Current backend is not running: $CURRENT_CONTAINER"
  container_running "$backup_container" \
    && fail "Backup container must be stopped before rollback: $backup_container"

  assert_supported_current_runtime
  wait_for_health "$CURRENT_HEALTH_URL" 60 2 \
    || fail "Current backend health did not become UP before rollback"

  restart_policy="$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$CURRENT_CONTAINER")"
  [[ -n "$restart_policy" && "$restart_policy" != "no" ]] || restart_policy="unless-stopped"
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  rescue_container="${CURRENT_CONTAINER}-rollback-rescue-${timestamp}"
  container_exists "$rescue_container" \
    && fail "Rollback rescue container already exists: $rescue_container"

  restore_rescue_after_failed_rollback() {
    local reason="$1"
    log "MANUAL_ROLLBACK_FAILURE=$reason"

    if container_exists "$CURRENT_CONTAINER"; then
      docker stop --time 30 "$CURRENT_CONTAINER" >/dev/null 2>&1 || true
      if ! container_exists "$backup_container"; then
        docker rename "$CURRENT_CONTAINER" "$backup_container" >/dev/null 2>&1 || true
        docker update --restart=no "$backup_container" >/dev/null 2>&1 || true
      fi
    fi

    if container_exists "$rescue_container"; then
      docker rename "$rescue_container" "$CURRENT_CONTAINER" >/dev/null 2>&1 || true
      docker update --restart="$restart_policy" "$CURRENT_CONTAINER" >/dev/null 2>&1 || true
      docker start "$CURRENT_CONTAINER" >/dev/null 2>&1 || true

      if wait_for_health "$CURRENT_HEALTH_URL" 60 2; then
        log "AWS_BACKEND_MANUAL_ROLLBACK=RECOVERED"
        log "CURRENT_CONTAINER=$CURRENT_CONTAINER"
        log "CURRENT_HEALTH=UP"
        log "ROLLBACK_BACKUP=$backup_container"
        exit 1
      fi
    fi

    log "AWS_BACKEND_MANUAL_ROLLBACK=RECOVERY_FAILED"
    exit 2
  }

  log "ROLLBACK_STEP=preserve_current_as_rescue"
  if ! docker stop --time 30 "$CURRENT_CONTAINER" >/dev/null; then
    fail "Could not stop current backend before rollback"
  fi
  if ! docker rename "$CURRENT_CONTAINER" "$rescue_container"; then
    docker start "$CURRENT_CONTAINER" >/dev/null 2>&1 || true
    fail "Could not preserve current backend as rollback rescue"
  fi
  if ! docker update --restart=no "$rescue_container" >/dev/null; then
    restore_rescue_after_failed_rollback "could not disable rescue restart policy"
  fi

  log "ROLLBACK_STEP=activate_backup"
  if ! docker rename "$backup_container" "$CURRENT_CONTAINER"; then
    restore_rescue_after_failed_rollback "could not activate backup container"
  fi
  if ! docker update --restart="$restart_policy" "$CURRENT_CONTAINER" >/dev/null; then
    restore_rescue_after_failed_rollback "could not restore backend restart policy"
  fi
  if ! docker start "$CURRENT_CONTAINER" >/dev/null; then
    restore_rescue_after_failed_rollback "could not start rollback container"
  fi

  if ! wait_for_health "$CURRENT_HEALTH_URL" 60 2; then
    restore_rescue_after_failed_rollback "rollback container health did not become UP"
  fi

  log "AWS_BACKEND_MANUAL_ROLLBACK=PASS"
  log "CURRENT_CONTAINER=$CURRENT_CONTAINER"
  log "CURRENT_HEALTH=UP"
  log "FORWARD_RECOVERY_CONTAINER=$rescue_container"
  log "FORWARD_RECOVERY_STATE=stopped"
}

usage() {
  cat <<USAGE
Usage:
  sudo bash $0 prepare-smoke
  sudo bash $0 preflight
  sudo bash $0 promote
  sudo bash $0 rollback <backup-container-name>

Release metadata is read from:
  VISIONFLOW_BACKEND_IMAGE
  VISIONFLOW_BACKEND_EXPECTED_DIGEST
in $ENV_FILE. CANDIDATE_IMAGE and EXPECTED_DIGEST may override them for a bounded operator run.
USAGE
}

main() {
  require_command docker
  require_command curl
  require_command grep
  require_command mktemp
  require_command date

  case "${1:-}" in
    prepare-smoke)
      prepare_smoke
      ;;
    preflight)
      preflight
      ;;
    promote)
      promote
      ;;
    rollback)
      rollback "${2:-}"
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
