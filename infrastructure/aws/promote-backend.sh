#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CORE_SCRIPT="${SCRIPT_DIR}/promote-backend-core.sh"

[[ -r "$CORE_SCRIPT" ]] || {
  printf 'ERROR=Promotion core is not readable: %s\n' "$CORE_SCRIPT" >&2
  exit 2
}
command -v sed >/dev/null 2>&1 || {
  printf 'ERROR=Required command not found: sed\n' >&2
  exit 2
}

# Load the validated Day 4 helper/rollback implementation without executing
# the core entrypoint. This entrypoint overrides the promotion transaction so
# every destructive transition can restore the previous backend.
# shellcheck disable=SC1090
source <(sed '$d' "$CORE_SCRIPT")

make_runtime_env_file() {
  PROMOTION_ENV_FILE="$(mktemp /tmp/visionflow-backend-runtime.XXXXXX.env)"
  chmod 600 "$PROMOTION_ENV_FILE"
  if ! docker inspect "$CURRENT_CONTAINER" \
    --format '{{range .Config.Env}}{{println .}}{{end}}' > "$PROMOTION_ENV_FILE"; then
    cleanup_runtime_env_file
    fail "Could not capture current backend runtime environment"
  fi
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
  docker logs --tail 300 "$CURRENT_CONTAINER" \
    > "${rollback_dir}/current-container.log" 2>&1 || true
  chmod 600 "${rollback_dir}/current-container.log"
  write_container_runtime_metadata \
    "$SMOKE_CONTAINER" "${rollback_dir}/smoke-container.runtime.txt"
  docker logs --tail 300 "$SMOKE_CONTAINER" \
    > "${rollback_dir}/smoke-container.log" 2>&1 || true
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

  recover_current_original() {
    local actual_image_id actual_restart_policy

    container_exists "$CURRENT_CONTAINER" || return 1
    actual_image_id="$(
      docker inspect --format '{{.Image}}' "$CURRENT_CONTAINER" \
        2>/dev/null || true
    )"
    [[ "$actual_image_id" == "$current_image_id" ]] || return 1

    docker update --restart="$restart_policy" "$CURRENT_CONTAINER" \
      >/dev/null 2>&1 || true
    docker start "$CURRENT_CONTAINER" >/dev/null 2>&1 || true
    actual_restart_policy="$(
      docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' \
        "$CURRENT_CONTAINER" 2>/dev/null || true
    )"
    [[ "$actual_restart_policy" == "$restart_policy" ]] || return 1
    wait_for_health "$CURRENT_HEALTH_URL" 60 2
  }

  rollback_automatically() {
    local reason="$1"
    local current_recovery_image_id=""
    log "PROMOTION_FAILURE=$reason"

    if container_exists "$CURRENT_CONTAINER"; then
      current_recovery_image_id="$(
        docker inspect --format '{{.Image}}' "$CURRENT_CONTAINER" \
          2>/dev/null || true
      )"

      if [[ "$current_recovery_image_id" == "$current_image_id" ]]; then
        if recover_current_original; then
          cleanup_runtime_env_file
          trap - EXIT
          log "AWS_BACKEND_PROMOTION=ROLLED_BACK"
          log "ROLLBACK_CONTAINER=$CURRENT_CONTAINER"
          log "ROLLBACK_IMAGE=$current_image"
          log "ROLLBACK_HEALTH=UP"
          log "ROLLBACK_ARTIFACTS=$rollback_dir"
          exit 1
        fi
      else
        docker logs --tail 300 "$CURRENT_CONTAINER" \
          > "${rollback_dir}/failed-candidate.log" 2>&1 || true
        chmod 600 "${rollback_dir}/failed-candidate.log"
        docker rm -f "$CURRENT_CONTAINER" >/dev/null 2>&1 || true
      fi
    fi

    if container_exists "$backup_container"; then
      if container_exists "$CURRENT_CONTAINER"; then
        current_recovery_image_id="$(
          docker inspect --format '{{.Image}}' "$CURRENT_CONTAINER" \
            2>/dev/null || true
        )"
        if [[ "$current_recovery_image_id" != "$current_image_id" ]]; then
          docker rm -f "$CURRENT_CONTAINER" >/dev/null 2>&1 || true
        fi
      fi

      if ! container_exists "$CURRENT_CONTAINER"; then
        docker rename "$backup_container" "$CURRENT_CONTAINER" \
          >/dev/null 2>&1 || true
      fi

      if recover_current_original; then
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

  log "PROMOTION_STEP=remove_smoke"
  if ! docker rm -f "$SMOKE_CONTAINER" >/dev/null; then
    fail "Could not remove smoke backend before promotion"
  fi

  log "PROMOTION_STEP=stop_current"
  if ! docker stop --time 30 "$CURRENT_CONTAINER" >/dev/null; then
    rollback_automatically "could not stop current backend"
  fi

  log "PROMOTION_STEP=preserve_current_as_rollback"
  if ! docker rename "$CURRENT_CONTAINER" "$backup_container"; then
    rollback_automatically \
      "could not preserve current backend as rollback container"
  fi
  if ! docker update --restart=no "$backup_container" >/dev/null; then
    rollback_automatically \
      "could not disable rollback container restart policy"
  fi

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
  docker logs --tail 300 "$CURRENT_CONTAINER" \
    > "${rollback_dir}/promoted-container.log" 2>&1 || true
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

main "$@"
