# VisionFlow 세션 데이터 정합성 복구

기준 커밋: `ad83fd0b8ab5c388b2403f3efa4836cceb3ea09c`

이 도구는 읽기 전용 데이터 정합성 감사에서 확인된 누락 `flight_session` 13건과 Drone 고아 세션 포인터 1건만 복구한다. 현재 데이터 프로필과 정책이 정확히 일치할 때만 실행된다.

## 확인된 원인

- `flight_session`은 2건만 남아 있지만 AI event·alert·Incident에는 14개 세션 참조가 있다.
- 이 중 13개 세션의 AI event·alert·Incident 6,325건이 각각 1:1로 보존돼 있다.
- 13개 세션은 모두 하나의 기존 Drone에 일관되게 연결된다.
- Drone 1번은 `OFFLINE`이며, 다른 근거 데이터가 없는 삭제된 세션 포인터 1건만 보유한다.

## 적용 범위

- `flight_session`: 과거 관측시간과 Drone을 근거로 13건 `INSERT`
- `drone.flight_session_id`: Drone 1번의 고아 포인터 1건 `UPDATE ... SET NULL`
- AI event·alert·Incident: 변경 0건
- `DELETE`: 0건
- 컨테이너·서비스 시작, 재시작, 재빌드: 없음

복원 세션의 상태는 `COMPLETED`, 시작·종료 시각은 해당 세션 AI 이벤트의 최초·최종 `captured_at`을 사용한다. 원본 세션 UUID를 유지하므로 기존 AI 데이터는 다시 정상 연결된다.

## 안전 장치

- 확인 토큰 없이는 변경할 수 없다.
- 현재 DB 행 수·고아 수·세션별 해시·기체·연쇄 건수·기존 세션 상태가 정책과 다르면 차단한다.
- `SERIALIZABLE` 트랜잭션에서 사전조건을 다시 검사한다.
- 예상 `13 INSERT + 1 UPDATE`와 다르면 오류를 발생시키고 전체 트랜잭션을 롤백한다.
- 적용 전 `before-state.json`과 수동 `rollback.sql`을 `artifacts/data-integrity-repair/repair-*`에 저장한다.
- MySQL 비밀번호와 운영자·AI 키는 읽거나 출력하지 않는다.
- 세션 UUID는 콘솔에 출력하지 않고 SHA-256 앞 16자리만 표시한다.

## 실행

먼저 변경 없는 계획을 확인한다.

```bat
scripts\run-visionflow-data-integrity-repair.bat plan
```

`Status: READY`일 때만 다음 명령으로 적용한다.

```bat
scripts\run-visionflow-data-integrity-repair.bat repair --apply --confirm REPAIR_VISIONFLOW_SESSION_INTEGRITY
```

적용 후 정합성 감사를 다시 실행한다.

```bat
scripts\run-visionflow-data-integrity-audit.bat
```

정상 결과는 `DATA_INTEGRITY_HEALTHY`이며, 복구 후에는 기존 정상 세션 2건을 포함해 `flight_session` 15건이 존재한다.

## 롤백 파일

생성된 `rollback.sql`은 자동 실행되지 않는다. 정상 복구를 과거 고아 상태로 되돌리는 변경이므로 장애 복구 판단과 별도 승인을 거쳐 수동으로만 사용한다.
