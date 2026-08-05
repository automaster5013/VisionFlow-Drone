# VisionFlow 정비 작전 현황 보드

기준 커밋: `011d25bfc632e8e030238d9b4fc87088198af376`

`/maintenance` 상단에서 정비 작업의 전체 흐름을 한눈에 확인하는 Frontend 관제 보드입니다. Backend API, 데이터베이스 스키마, 컨테이너 구성은 변경하지 않습니다.

## 화면 구성

- 작전 단계: 신규 접수, 점검 진행, SLA 대응, 운항 판정
- 비행 준비 상태: 전체 함대의 비행 가능, 점검 대기, 운항 중지를 도넛
  차트로 표시
- 함대 판정 상세: 전체·비행 가능·점검 대기·운항 중지 필터로 기체별
  판정 사유를 확인하고 기체 상세 또는 연결된 작업지시로 이동
- 긴급 작업 큐: SLA 초과·임박, Incident 담당 필요, 마감 정합성 경고 중 상위 3건
- 운영 상태: 즉시 대응 필요, 주의 관제, 운영 안정
- 갱신: 30초 자동 갱신과 수동 `지금 갱신`
- 반응형: 모바일 1열, 태블릿 2열, 데스크톱 관제형 그리드

## 데이터와 보안 경계

- 브라우저는 same-origin `/api/maintenance/sla/incidents`와
  `/api/maintenance/flight-clearance`만 호출합니다.
- Next Route Handler가 기존 운영자 인증을 Backend 요청에 전달합니다.
- SLA 응답은 `parseMaintenanceSlaIncidentTracking`, 함대 판정 응답은
  `parseMaintenanceFleetFlightClearance`로 각각 검증한 뒤 표시합니다.
- 함대 도넛은 각 기체의 `flightAllowed`와 `attentionRequired`를 조합해
  상호 배타적인 세 구간으로 집계하므로 합계가 항상 전체 기체 수와
  일치합니다.
- 도넛 범례와 상세 필터는 같은 기체별 판정 배열을 사용합니다. 필터는
  브라우저 표시 상태만 바꾸며 Backend 재평가나 작업 상태 변경을
  요청하지 않습니다.
- 비행 차단·주의 기체를 먼저 정렬하고, 각 카드에는 Backend 판정 사유와
  기체 상세 링크 및 존재하는 경우 작업지시 링크를 표시합니다.
- 이전 정상 데이터가 있으면 일시적인 갱신 실패 시 그대로 유지하고 경고만 표시합니다.
- 변경·삭제 요청을 새로 만들지 않으며 정비 작업 처리 권한 경계도 바꾸지 않습니다.

## 검증

저장소 루트에서 다음을 실행합니다.

```bat
py -3 -m py_compile scripts\visionflow_system_traceability_audit.py scripts\tests\test_visionflow_system_traceability_maintenance_mission_control.py
py -3 -m unittest scripts.tests.test_visionflow_system_traceability_maintenance_mission_control -v
py -3 -m json.tool scripts\visionflow_ci_api_audit_policy.json >nul
cd 01_frontend\visionflow-web
npm run lint
npm run build
```

전체 정적 감사는 저장소 루트에서 실행합니다.

```bat
scripts\run-visionflow-system-traceability-audit.bat
scripts\run-visionflow-api-audit-ci.bat
```

런타임 반영 후 `/maintenance`에서 상단 보드, 30초 갱신 문구, 단계 카드
4개, 비행 준비 도넛 차트, 함대 판정 상세 필터·사유·링크, 긴급 작업
링크를 확인합니다.
