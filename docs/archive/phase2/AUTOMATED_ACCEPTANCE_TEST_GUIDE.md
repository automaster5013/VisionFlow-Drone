# VisionFlow 자동 인수 테스트 패치

현재까지 구현한 2차 프로젝트 기능을 발표 전 한 명령으로 재검증하는
PowerShell 도구입니다. 애플리케이션 코드는 변경하지 않습니다.

검증 대상:

- Spring Boot 상태와 드론 목록 API
- Next.js 대시보드, 드론 관제, 발표 시연 콘솔
- Python AI 입력·스트림 상태 API (`/api/ingest/status`, `/api/streams/status`)
- Next.js AI API 프록시
- 선택 실행: 시연 시나리오 전체 단계
- AI 탐지 JPEG 증거 조회
- Incident 보고서 API
- 실행 결과 JSON·HTML 보고서 및 프로세스 종료 코드

DJI Mini 4 Pro 기체 종속 기능은 포함하지 않습니다. 기존 합의대로 실제 DJI
연동은 3차 프로젝트 범위로 유지합니다.

## 1. 파일 배치

ZIP의 `scripts` 폴더를 다음 위치에 복사합니다.

```text
C:\VisionFlow-Drone\scripts
```

최종 경로 예시:

```text
C:\VisionFlow-Drone\scripts\visionflow-acceptance.ps1
C:\VisionFlow-Drone\scripts\run-visionflow-acceptance.bat
```

## 2. 사전 준비

다음 프로세스를 각각 실행합니다.

1. Docker MySQL
2. Spring Boot 백엔드: `http://localhost:8080`
3. Python AI 서버: `http://localhost:8000`
4. Next.js 프런트엔드: `http://localhost:3000`

시연 시나리오까지 실행하려면 백엔드를 다음 설정과 함께 실행해야 합니다.

```bat
set VISIONFLOW_DEMO_ENABLED=true
cd C:\VisionFlow-Drone\02_backend\visionflow-api
gradlew.bat bootRun
```

또한 대상 드론에 기존 ACTIVE 비행 세션이 없어야 합니다. 수정된 검사
스크립트는 시연 시작 전에 ACTIVE 세션을 조회하고, 발견하면 해당 UUID를
결과 메시지로 출력합니다.

## 3. 읽기 전용 사전 점검

프로젝트 최상위 폴더에서 실행합니다.

```bat
cd C:\VisionFlow-Drone
scripts\run-visionflow-acceptance.bat
```

PowerShell에서 직접 실행할 수도 있습니다.

```powershell
.\scripts\visionflow-acceptance.ps1
```

이 스크립트는 Windows PowerShell 5.1과 PowerShell 7에서 모두 실행할 수
있도록 GET 요청 본문을 차단하고 기본 PowerShell 배열로 결과를 수집합니다.

기본 사전 점검은 데이터를 생성하거나 수정하지 않습니다.

AI 서버를 의도적으로 실행하지 않은 상태라면 다음 옵션을 사용합니다.

```bat
scripts\run-visionflow-acceptance.bat -SkipAi
```

## 4. 전체 E2E 시연 인수 테스트

```bat
cd C:\VisionFlow-Drone
scripts\run-visionflow-acceptance.bat -RunDemo
```

이 명령은 다음 데이터를 실제 MySQL과 스냅샷 저장소에 남깁니다.

- 비행 세션 1건
- 텔레메트리 이력 5건 이상
- AI 추론 이벤트·탐지 결과·JPEG 스냅샷
- AI 경보 및 Incident
- SLA 에스컬레이션·해결 조치 이력
- 완료된 발표 시연 시나리오

기본 드론 ID는 `1`, 시작 좌표는 서울시청 인근입니다. 값을 변경하려면:

```bat
scripts\run-visionflow-acceptance.bat -RunDemo -DroneId 3 -Latitude 37.5700 -Longitude 126.9850
```

## 5. 다른 포트에서 실행할 때

```powershell
.\scripts\visionflow-acceptance.ps1 `
  -FrontendUrl "http://localhost:3100" `
  -BackendUrl "http://localhost:8180" `
  -AiUrl "http://localhost:8100" `
  -RunDemo
```

요청 제한시간도 변경할 수 있습니다.

```bat
scripts\run-visionflow-acceptance.bat -TimeoutSeconds 30
```

## 6. 결과 보고서

기본 출력 폴더:

```text
C:\VisionFlow-Drone\artifacts\visionflow-acceptance
```

매 실행마다 다음 파일이 생성됩니다.

```text
visionflow-acceptance-YYYYMMDD-HHMMSS.json
visionflow-acceptance-YYYYMMDD-HHMMSS.html
```

HTML 파일은 발표 전 점검 결과를 브라우저에서 확인하기 좋고, JSON 파일은
향후 CI/CD 파이프라인에서 사용할 수 있습니다.

모든 검증에 성공하면 프로세스 종료 코드는 `0`, 한 항목이라도 실패하면
`1`입니다.

## 7. 정상 결과

AI 서버를 포함한 읽기 전용 점검은 기본적으로 9개 항목이 PASS여야 합니다.
`-RunDemo`를 추가하면 총 17개 항목이 PASS여야 합니다.

전체 시연 단계:

```text
READY → DETECTED → ESCALATED → RESOLVED → COMPLETED
```

최종 결과에는 다음 값이 포함되어야 합니다.

- `scenario.stage = COMPLETED`
- `scenario.incidentId`가 숫자
- AI 탐지 스냅샷 HTTP 200
- Incident 보고서 API HTTP 200

## 8. 실패 시 확인 순서

- `Backend health` 실패: Spring Boot 8080 실행 여부 확인
- `Frontend ...` 실패: Next.js 3000 실행 여부 확인
- `AI ...` 실패: `python -m app.main` 실행 여부와 8000 포트 확인
- `Next AI ... proxy`만 실패: `.env.local`의 AI 서버 URL 확인 후 Next.js 재시작
- `Demo start` 404: `VISIONFLOW_DEMO_ENABLED=true` 적용 후 백엔드 재시작
- `Demo start`에서 ACTIVE 세션 오류: 대상 드론의 기존 비행 세션을 완료 또는 중단
- 스냅샷 실패: 백엔드 `visionflow.ai.snapshot.storage-path`와 쓰기 권한 확인
- Incident 보고서 실패: 이전 Incident 보고서 패치와 Next.js 프록시 적용 여부 확인

실패가 발생해도 가능한 나머지 점검을 계속하고 JSON·HTML 보고서를 생성합니다.

ACTIVE 세션은 다음 API로 확인할 수 있습니다.

```bat
curl.exe "http://localhost:8080/api/drones/1/flight-sessions?limit=100"
```

응답에서 `status`가 `ACTIVE`인 실제 `sessionId`를 사용해 중단합니다.

```bat
curl.exe -i -X POST "http://localhost:8080/api/drones/1/flight-sessions/실제_UUID/abort"
```

`실제_UUID` 자리에 중괄호 없이 응답의 UUID 값을 입력해야 합니다.
