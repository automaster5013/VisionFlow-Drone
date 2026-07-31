# VisionFlow 발표·데모 데이터 안전 정리 도구

## 대상

- `flight_session.source_device_id = visionflow-demo-console`
- `ai_inference_event.source_id LIKE presentation-%`

다음 실제 스마트폰 완료 세션은 코드에서 보호합니다.

```text
3c0b11cc-c115-45b4-9814-9ef18ada6188
```

현재 승인된 예상 대상은 다음과 같습니다.

| 구분 | 건수 |
|---|---:|
| 비행 세션 | 40 |
| 데모 시나리오 | 40 |
| 텔레메트리 | 200 |
| AI 이벤트 | 59 |
| 탐지 | 109 |
| 경보 | 59 |
| 사고 | 59 |
| 사고 처리 이력 | 158 |
| 스냅숏 | 59 |

예상값이나 대상 ID가 바뀌면 도구가 실행을 차단합니다.

정리 성공 후 예상 전체 건수는 다음과 같습니다.

| 테이블 | 정리 전 | 정리 후 |
|---|---:|---:|
| `flight_session` | 42 | 2 |
| `demo_scenario` | 40 | 0 |
| `drone_telemetry_history` | 1,037 | 837 |
| `ai_inference_event` | 6,971 | 6,912 |
| `ai_detection` | 22,779 | 22,670 |
| `ai_alert` | 6,971 | 6,912 |
| `incident` | 6,971 | 6,912 |
| `incident_action_history` | 13,982 | 13,824 |

## 설치

ZIP 안의 다음 두 파일을 `C:\VisionFlow-Drone\scripts`에 복사합니다.

```text
visionflow_presentation_data_cleanup.py
run-visionflow-presentation-data-cleanup.bat
```

## 실행 순서

### 1. 읽기 전용 계획

```bat
scripts\run-visionflow-presentation-data-cleanup.bat plan --confirm PLAN_PRESENTATION_DATA
```

출력된 `Operation` 경로를 이후 명령에 사용합니다.

먼저 이 단계만 실행해 결과를 확인하십시오. 건수, 스냅숏 또는 외래 키
연결 상태가 확인 당시와 달라졌으면 여기서 안전하게 중단되며 DB와 파일은
변경되지 않습니다.

### 2. 백업 및 스냅숏 격리

```bat
scripts\run-visionflow-presentation-data-cleanup.bat quarantine --operation "출력된 Operation 경로" --apply --confirm QUARANTINE_PRESENTATION_59_SNAPSHOTS
```

전체 DB와 대상 테이블을 다시 백업하고 59개 스냅숏을 격리합니다. DB는 아직 삭제하지 않습니다.

### 3. DB 정리

```bat
scripts\run-visionflow-presentation-data-cleanup.bat delete --operation "출력된 Operation 경로" --apply --confirm DELETE_PRESENTATION_DATA
```

서비스를 기존 컨테이너 단위로 중지·재개하므로 NVIDIA GPU 설정을 보존합니다. 정리 후 저장소 감사를 자동 실행합니다.

### 4. 상태 확인

```bat
scripts\run-visionflow-presentation-data-cleanup.bat status --operation "출력된 Operation 경로"
```

## 복원

격리 또는 DB 삭제 후 복원할 때만 실행합니다.

```bat
scripts\run-visionflow-presentation-data-cleanup.bat restore --operation "출력된 Operation 경로" --apply --confirm RESTORE_PRESENTATION_DATA
```

## 삭제 커밋 후 사후 검증 실패 조정

DB 삭제는 완료됐지만 사후 검증 단계에서만 실패하여 operation 상태가
`DELETE_FAILED`로 남은 경우에 사용합니다. DB·파일을 다시 삭제하지 않고,
백업·격리·삭제 후 전체 건수를 모두 재검증한 뒤 상태만 확정합니다.

```bat
scripts\run-visionflow-presentation-data-cleanup.bat reconcile --operation "출력된 Operation 경로" --confirm RECONCILE_DELETED_PRESENTATION_DATA
```

## 안전 특성

- 승인 건수 불일치 시 중단
- 대상 ID fingerprint 변경 시 중단
- 전체 관련 테이블 건수 변경 시 중단
- 자동 백업·복원 범위 밖의 외래 키 연결 데이터가 있으면 중단
- 실제 스마트폰 완료 세션 포함 시 중단
- 스냅숏 이름·크기·경로 검증
- 전체 DB 및 대상 테이블별 SQL 백업
- SHA-256 백업 검증
- 파일 이동 실패 시 자동 원위치
- DB 트랜잭션 삭제
- 격리 파일 유지 및 대상별 복원 지원
- AI 컨테이너의 기존 GPU 장치 요청 보존

기존 `run-ai-event-cleanup-*` 도구는 7월 29일 대량 폭증 데이터 전용이므로 이번 발표 데이터 정리에 사용하지 않습니다.
