# VisionFlow 런타임 데이터 정합성 감사

기준 커밋: `ad83fd0b8ab5c388b2403f3efa4836cceb3ea09c`

이 감사기는 API·DB 추적성 문서에서 식별한 물리 FK 밖의 소프트 상관관계를 실행 중인 MySQL과 스냅샷 디렉터리에서 읽기 전용으로 검사한다.

## 안전 경계

- 실행 중인 `visionflow-mysql`만 사용하며 컨테이너를 시작·재시작하지 않는다.
- 모든 DB 조회는 `SET SESSION TRANSACTION READ ONLY`와 `START TRANSACTION READ ONLY` 안에서 실행한다.
- `SELECT` 이외 SQL과 복수 statement를 코드에서 차단한다.
- MySQL 비밀번호·운영자 키·AI 내부 키를 읽거나 출력하지 않는다.
- 스냅샷 파일 내용은 읽지 않고 파일명·존재·크기만 비교한다.
- 보고서에는 원본 파일명 대신 SHA-256 앞 16자만 기록한다.
- DB·파일을 수정하거나 자동 정리하지 않는다.

## 감사 범위

총 41개 DB 상관관계·수명주기 규칙과 5개 스냅샷 규칙을 검사한다.

- 기체별 `ACTIVE` 비행 세션은 최대 한 건
- Drone·Geofence 조합별 미해결 위반 이벤트는 최대 한 건
- `session_id`: Drone 현재 세션, telemetry, AI event·alert, geofence event, Incident, Demo, 작업지시
- 세션 소유 기체: 각 참조 행의 `drone_id`와 `flight_session.drone_id` 일치
- 비FK `drone_id`: AI event·alert, geofence event, Incident, Demo의 기체 존재
- AI alert ↔ inference event의 세션·기체 일치
- Incident `source_type + source_id`: `AI_ALERT`, `GEOFENCE`, `FLIGHT_QUALITY`, `FLIGHT_GATE`
- Demo의 AI event·alert·Incident 참조와 세션·기체 일치
- 작업지시 ↔ 비행 품질 평가의 세션·기체 일치
- snapshot metadata 완결성, 안전한 파일명, 실제 파일 존재·크기·중복·미참조 파일

`audit_log.entity_type + entity_id`는 감사 증적을 보존하기 위해 원본 엔터티 삭제 후에도 남을 수 있으므로 고아 데이터로 판정하지 않는다.

## 실행

저장소 루트에서 실행한다.

```bat
scripts\run-visionflow-data-integrity-audit.bat
```

정상 출력은 다음과 같다.

```text
VisionFlow data integrity audit: DATA_INTEGRITY_HEALTHY
Rules: Database=41, Snapshots=5, Findings=0
```

보고서는 `artifacts\data-integrity-audit\audit-*`에 JSON·HTML·Markdown으로 생성된다.

## 판정

- `DATA_INTEGRITY_HEALTHY`: 모든 규칙이 허용 수량 이내
- `DATA_INTEGRITY_ADVISORY`: 미참조 snapshot 파일만 존재
- `DATA_INTEGRITY_BLOCKED`: 고아·소유 기체 불일치·소스 불일치·snapshot 참조 오류 존재
- `ERROR`: 컨테이너·스키마·SQL 결과·정책을 안전하게 해석하지 못함

Advisory도 자동화에서 실패시키려면 다음과 같이 실행한다.

```bat
scripts\run-visionflow-data-integrity-audit.bat --strict
```

발견된 문제는 자동 삭제하지 않는다. JSON 보고서를 보존하고 별도 백업·수정·복구 계획을 승인한 뒤 처리한다.
