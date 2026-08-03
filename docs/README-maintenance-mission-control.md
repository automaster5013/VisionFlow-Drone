# VisionFlow 정비 작전 현황 보드

기준 커밋: `05719fe941bb0036ecc4431f4d3a32f58bd23383`

`/maintenance` 상단에서 정비 작업의 전체 흐름을 한눈에 확인하는 Frontend 관제 보드입니다. Backend API, 데이터베이스 스키마, 컨테이너 구성은 변경하지 않습니다.

## 화면 구성

- 작전 단계: 신규 접수, 점검 진행, SLA 대응, 운항 판정
- 비행 준비 상태: 비행 가능, 점검 대기, 운항 중지를 도넛 차트로 표시
- 긴급 작업 큐: SLA 초과·임박, Incident 담당 필요, 마감 정합성 경고 중 상위 3건
- 운영 상태: 즉시 대응 필요, 주의 관제, 운영 안정
- 갱신: 30초 자동 갱신과 수동 `지금 갱신`
- 반응형: 모바일 1열, 태블릿 2열, 데스크톱 관제형 그리드

## 데이터와 보안 경계

- 브라우저는 same-origin `/api/maintenance/sla/incidents`만 호출합니다.
- Next Route Handler가 기존 운영자 인증을 Backend 요청에 전달합니다.
- 응답은 `parseMaintenanceSlaIncidentTracking`으로 검증한 뒤 표시합니다.
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

런타임 반영 후 `/maintenance`에서 상단 보드, 30초 갱신 문구, 단계 카드 4개, 비행 준비 도넛 차트, 긴급 작업 링크를 확인합니다.
