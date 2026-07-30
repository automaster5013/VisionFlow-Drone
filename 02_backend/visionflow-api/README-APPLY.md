# VisionFlow 비행 품질 평가 MySQL/API 패치

## 적용 대상

`C:\VisionFlow-Drone\02_backend\visionflow-api`

이 ZIP의 `src` 폴더를 위 백엔드 프로젝트 루트에 덮어씁니다. 기존
파일을 삭제하지 말고 병합하십시오.

## 구현 범위

- Flyway `V16__create_flight_quality_assessment.sql`
- Hibernate 검증용 `V17__align_flight_quality_numeric_types.sql`
- 프런트엔드와 동일한 `VFQ-1.0.0` 품질 점수 계산 규칙
  - 텔레메트리 데이터 품질: 40점
  - 비행 안정성: 30점
  - AI 추론·증적: 30점
- 세션별 평가 저장 및 같은 규칙 버전 재평가 시 갱신
- 세션별 최신 평가 조회
- 드론별 평가 이력 및 등급 필터 조회
- 재평가 감사 로그
- 정상·데이터 누락·중단 비행 계산 단위 테스트

## 1. 빌드 검증

```bat
cd C:\VisionFlow-Drone\02_backend\visionflow-api
.\gradlew.bat clean build
```

## 2. 서비스 반영

프로젝트 루트에서 실행합니다.

```bat
cd C:\VisionFlow-Drone
docker compose --env-file .env.docker up --build -d
```

백엔드 시작 시 Flyway가 `V16`을 자동 적용합니다.

## 3. 실제 세션 UUID 확인

```bat
curl.exe -sS "http://localhost:8080/api/drones/1/flight-sessions?limit=20"
```

응답의 `sessionId` 실제 값을 아래 `{UUID}` 대신 사용하십시오. 중괄호를
포함한 `{UUID}` 문자열을 그대로 입력하면 안 됩니다.

## 4. 품질 평가 계산 및 MySQL 저장

RBAC 사용 중이면 OPERATOR 또는 ADMIN 키가 필요합니다.

```bat
curl.exe -i -X PUT "http://localhost:8080/api/drones/1/flight-sessions/{UUID}/quality-assessment" -H "X-VisionFlow-Operator-Key: 여기에_실제_OPERATOR_또는_ADMIN_키"
```

정상 결과는 HTTP `200`이며 `score`, `grade`, 세부 점수, 위험 건수,
`metrics`, `ruleVersion`, `evaluatedAt`이 반환됩니다.

## 5. 저장 결과 조회

세션별 최신 평가:

```bat
curl.exe -i "http://localhost:8080/api/drones/1/flight-sessions/{UUID}/quality-assessment"
```

드론별 최신 평가 이력:

```bat
curl.exe -i "http://localhost:8080/api/drones/1/flight-quality-assessments?limit=20"
```

위험 등급만 조회:

```bat
curl.exe -i "http://localhost:8080/api/drones/1/flight-quality-assessments?grade=RISK&limit=20"
```

지원 등급은 `EXCELLENT`, `GOOD`, `CAUTION`, `RISK`입니다.

## 6. DBeaver 확인 SQL

```sql
SELECT id,
       drone_id,
       session_id,
       rule_version,
       score,
       grade,
       data_score,
       flight_score,
       ai_score,
       warning_count,
       critical_count,
       evaluated_at
FROM flight_quality_assessment
ORDER BY evaluated_at DESC;
```

같은 세션을 같은 `VFQ-1.0.0` 규칙으로 다시 평가하면 행이 중복 생성되지
않고 기존 평가가 갱신됩니다.

## 참고

- 조회 GET API는 기존 공개 조회 정책을 따릅니다.
- 저장·재평가 PUT API는 기존 `SecurityConfig`의
  `/api/drones/**` OPERATOR/ADMIN 경계를 그대로 따릅니다.
- `GET`이 먼저 404를 반환하는 것은 아직 평가가 저장되지 않았다는
  의미입니다. 먼저 `PUT` 재평가를 실행하십시오.
