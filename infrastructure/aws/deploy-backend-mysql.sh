#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-/home/ubuntu/visionflow-cloud/.env}"
NETWORK="visionflow-cloud"
MYSQL_VOLUME="visionflow_mysql_data"
MYSQL_CONTAINER="visionflow-mysql-cloud"
BACKEND_CONTAINER="visionflow-backend-cloud"
MYSQL_IMAGE="mysql:8.4"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ENV_FILE_NOT_FOUND=$ENV_FILE" >&2
  exit 2
fi
if [[ ! -r "$ENV_FILE" ]]; then
  echo "ENV_FILE_NOT_READABLE=$ENV_FILE" >&2
  exit 2
fi

read_env_value() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 || true)"
  printf '%s' "${line#*=}"
}

BACKEND_IMAGE="$(read_env_value VISIONFLOW_BACKEND_IMAGE)"
EXPECTED_DIGEST="$(read_env_value VISIONFLOW_BACKEND_EXPECTED_DIGEST)"
MYSQL_DATABASE="$(read_env_value MYSQL_DATABASE)"

if [[ -z "$BACKEND_IMAGE" ]]; then
  echo "VISIONFLOW_BACKEND_IMAGE_MISSING=YES" >&2
  exit 2
fi
if [[ -z "$EXPECTED_DIGEST" ]]; then
  echo "VISIONFLOW_BACKEND_EXPECTED_DIGEST_MISSING=YES" >&2
  exit 2
fi
if [[ "${MYSQL_DATABASE:-}" != "visionflow" ]]; then
  echo "MYSQL_DATABASE_MUST_BE_VISIONFLOW=YES" >&2
  exit 2
fi

echo "=== VISIONFLOW AWS BACKEND + MYSQL DEPLOY ==="

sudo docker network inspect "$NETWORK" >/dev/null 2>&1 || sudo docker network create "$NETWORK" >/dev/null
echo "DOCKER_NETWORK=PASS"

sudo docker volume inspect "$MYSQL_VOLUME" >/dev/null 2>&1 || sudo docker volume create "$MYSQL_VOLUME" >/dev/null
echo "MYSQL_VOLUME=PASS"

sudo docker pull "$MYSQL_IMAGE" >/dev/null
echo "MYSQL_IMAGE_PULL=PASS"

if sudo docker inspect "$MYSQL_CONTAINER" >/dev/null 2>&1; then
  sudo docker start "$MYSQL_CONTAINER" >/dev/null || true
else
  sudo docker run -d     --name "$MYSQL_CONTAINER"     --restart unless-stopped     --network "$NETWORK"     --env-file "$ENV_FILE"     -e TZ=Asia/Seoul     -v "$MYSQL_VOLUME:/var/lib/mysql"     "$MYSQL_IMAGE"     --character-set-server=utf8mb4     --collation-server=utf8mb4_unicode_ci >/dev/null
fi

mysql_deadline=$((SECONDS + 180))
while (( SECONDS < mysql_deadline )); do
  if sudo docker exec "$MYSQL_CONTAINER" sh -lc 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqladmin ping -h 127.0.0.1 -u root --silent' >/dev/null 2>&1; then
    echo "MYSQL_HEALTH=PASS"
    break
  fi
  sleep 3
done

if ! sudo docker exec "$MYSQL_CONTAINER" sh -lc 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqladmin ping -h 127.0.0.1 -u root --silent' >/dev/null 2>&1; then
  echo "MYSQL_HEALTH=FAIL" >&2
  exit 3
fi

sudo docker pull "$BACKEND_IMAGE" >/dev/null
echo "BACKEND_IMAGE_PULL=PASS"

repo_digest="$(sudo docker image inspect "$BACKEND_IMAGE" --format '{{range .RepoDigests}}{{println .}}{{end}}' | grep -F "@${EXPECTED_DIGEST}" | head -n 1 || true)"
if [[ -z "$repo_digest" ]]; then
  echo "BACKEND_DIGEST_VERIFY=FAIL" >&2
  sudo docker image inspect "$BACKEND_IMAGE" --format '{{range .RepoDigests}}{{println .}}{{end}}' || true
  exit 4
fi
echo "BACKEND_DIGEST_VERIFY=PASS"

if sudo docker inspect "$BACKEND_CONTAINER" >/dev/null 2>&1; then
  sudo docker rm -f "$BACKEND_CONTAINER" >/dev/null
fi

sudo docker run -d   --name "$BACKEND_CONTAINER"   --restart unless-stopped   --network "$NETWORK"   --env-file "$ENV_FILE"   -e SPRING_PROFILES_ACTIVE=docker   -e "SPRING_DATASOURCE_URL=jdbc:mysql://${MYSQL_CONTAINER}:3306/visionflow?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Seoul&characterEncoding=UTF-8"   -e TZ=Asia/Seoul   --memory=768m   --memory-swap=1536m   -p 8080:8080   "$BACKEND_IMAGE" >/dev/null

echo "BACKEND_CONTAINER_START=PASS"

backend_deadline=$((SECONDS + 180))
while (( SECONDS < backend_deadline )); do
  if curl -fsS --max-time 5 http://127.0.0.1:8080/actuator/health >/dev/null 2>&1; then
    echo "BACKEND_HEALTH=PASS"
    break
  fi
  state="$(sudo docker inspect -f '{{.State.Status}}' "$BACKEND_CONTAINER" 2>/dev/null || true)"
  if [[ "$state" == "exited" || "$state" == "dead" ]]; then
    sudo docker logs --tail 120 "$BACKEND_CONTAINER" >&2 || true
    echo "BACKEND_CONTAINER_STATE=$state" >&2
    exit 5
  fi
  sleep 3
done

if ! curl -fsS --max-time 5 http://127.0.0.1:8080/actuator/health >/dev/null 2>&1; then
  sudo docker logs --tail 120 "$BACKEND_CONTAINER" >&2 || true
  echo "BACKEND_HEALTH=FAIL" >&2
  exit 5
fi

schema_output="$(sudo docker exec "$MYSQL_CONTAINER" sh -lc 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -B -h 127.0.0.1 -u root "$MYSQL_DATABASE" -e "
SELECT CONCAT("FLYWAY_V24_SUCCESS_COUNT=", COUNT(*)) FROM flyway_schema_history WHERE version="24" AND success=1;
SELECT CONCAT("AI_PHASE3_EVENT_TABLE_COUNT=", COUNT(*)) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name="ai_phase3_event";
SELECT CONCAT("AI_PHASE3_EVENT_COLUMN_COUNT=", COUNT(*)) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name="ai_phase3_event";
"')"
printf '%s
' "$schema_output"

grep -Fxq 'FLYWAY_V24_SUCCESS_COUNT=1' <<<"$schema_output"
grep -Fxq 'AI_PHASE3_EVENT_TABLE_COUNT=1' <<<"$schema_output"
grep -Fxq 'AI_PHASE3_EVENT_COLUMN_COUNT=21' <<<"$schema_output"

echo "VISIONFLOW_AWS_BACKEND_SCHEMA_GATE=PASS"
echo "VISIONFLOW_AWS_RUNTIME_DEPLOY=PASS"
