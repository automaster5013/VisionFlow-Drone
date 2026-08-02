# VisionFlow Geofence 위반 이벤트 수명주기 동시성 방어

기준 커밋: `0d252db4809e0c685050e0260b3c91ca77b4ed61`

지오펜스 설정 변경과 텔레메트리 기반 위반 이벤트 평가가 동시에 실행돼도 같은 Drone·Geofence 조합에 미해결 이벤트가 중복 생성되지 않도록 직렬화한다.

## 방어 범위

- 지오펜스 수정·활성 상태 변경·텔레메트리 평가가 `DroneGeofence` 행을 `PESSIMISTIC_WRITE`로 잠근다.
- 평가는 잠금을 획득한 뒤 활성 상태를 다시 확인한다.
- 읽기 전용 상세·목록 조회는 비잠금으로 유지한다.
- Flyway V23은 `resolved_at IS NULL`인 행에만 Drone·Geofence 키를 노출하는 generated column 두 개와 UNIQUE 제약을 추가한다.
- 애플리케이션 잠금 밖에서 유입되는 경쟁 쓰기도 DB UNIQUE 제약이 최종 차단한다.
- 기존 중복 미해결 이벤트가 있으면 V23 적용 전에 41개 DB 규칙의 읽기 전용 정합성 감사가 차단한다.

## 안전 경계

- 설치기는 소스만 변경하며 DB·컨테이너·서비스·예약 작업을 변경하지 않는다.
- Flyway V23은 `backend-api`를 명시적으로 다시 빌드할 때만 적용된다.
- 운영 데이터는 자동 삭제·병합·해결하지 않는다.
- 사전 감사에서 finding이 발견되면 재빌드하지 말고 별도 승인 복구 절차를 따른다.

## 소스 검증

저장소 루트에서 실행한다.

```bat
py -3 -m py_compile scripts\visionflow_data_integrity_audit.py scripts\visionflow_system_traceability_audit.py scripts\tests\test_visionflow_data_integrity_audit.py scripts\tests\test_visionflow_system_traceability_geofence_event_lifecycle.py
py -3 -m json.tool scripts\visionflow_data_integrity_policy.json >nul
py -3 -m json.tool scripts\visionflow_ci_api_audit_policy.json >nul
py -3 -m unittest scripts.tests.test_visionflow_system_traceability_geofence_event_lifecycle scripts.tests.test_visionflow_system_traceability_ai_alert_lifecycle scripts.tests.test_visionflow_system_traceability_incident_lifecycle scripts.tests.test_visionflow_data_integrity_audit -v
02_backend\visionflow-api\gradlew.bat -p 02_backend\visionflow-api test --tests "com.visionflow.api.geofence.service.GeofenceServiceConcurrencyTests"
```

## 적용 전 읽기 전용 감사

V23 적용 전에 반드시 실행한다.

```bat
scripts\run-visionflow-data-integrity-audit.bat
```

다음 결과에서 `Findings=0`이어야 한다.

```text
VisionFlow data integrity audit: DATA_INTEGRITY_HEALTHY
Rules: Database=41, Snapshots=5, Findings=0
```

## Backend 재빌드와 확인

```bat
docker compose --env-file .env.docker -f compose.yaml -f compose.gpu.yaml -f compose.mobile-https.yaml config --quiet
docker compose --env-file .env.docker -f compose.yaml -f compose.gpu.yaml -f compose.mobile-https.yaml up -d --build --force-recreate --no-deps backend-api
```

Backend가 `running/healthy`가 된 뒤 Flyway V23 성공과 UNIQUE 제약을 확인한다.

```sql
SELECT installed_rank, version, description, script, checksum, execution_time, success
FROM flyway_schema_history
WHERE version = '23';

SELECT column_name, extra, generation_expression
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'drone_geofence_event'
  AND column_name IN ('active_drone_id', 'active_geofence_id');

SELECT index_name, non_unique, seq_in_index, column_name
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'drone_geofence_event'
  AND index_name = 'uq_geofence_event_one_active_per_drone_zone'
ORDER BY seq_in_index;
```

마지막으로 시스템 추적성, API 감사, 데이터 정합성, 수용 시험, 운영 가드를 순서대로 실행한다. 모든 감사와 수용 시험이 정상이어야 커밋한다.
