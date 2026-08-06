# VisionFlow 정비 비행 판정 근거 타임라인

기준 커밋: `da68c81029ab6646d8e7d9777a5b726061f36999`

`/maintenance`의 기체 관제 상세 드로어에서 최종 비행 허가가 만들어진
운영 근거를 순서대로 보여주는 Frontend 시각화입니다. Backend API,
데이터베이스, 인증·권한과 작업 상태 전이는 변경하지 않습니다.

## 화면 구성

타임라인은 다음 네 단계를 세로 흐름으로 표시합니다.

1. `Fleet Flight Gate`: 비활성·주의·강제 차단 모드와 실제 적용 여부
2. `Maintenance Work Order`: 연결 작업 없음, 점검 대기·진행, 재운항 승인,
   운항 중지 상태
3. `Incident & SLA`: 담당자·대응 상태·SLA 정상·임박·초과와 수동 검토 필요
4. `Final Readiness`: 비행 가능·점검 대기·운항 중지와 Backend 판정 사유

단계 번호, 연결선, 상태 배지와 중립·진행·정상·주의·긴급 색상을 함께
사용합니다. 색상만으로 의미를 전달하지 않고 모든 단계에 제목·상태·설명을
표시합니다.

## 데이터와 안전 경계

- Mission Control이 이미 파싱한 `/api/maintenance/flight-clearance`와
  `/api/maintenance/sla/incidents` 결과만 사용합니다.
- 타임라인 컴포넌트는 추가 `fetch` 또는 변경 요청을 만들지 않습니다.
- 표시용 단계와 색상만 파생하며 비행 허가, 정비 상태, Incident 또는 SLA를
  브라우저에서 재판정하지 않습니다.
- 기존 `workOrderId` 결합, same-origin 인증 프록시, RBAC와 Backend 판정
  결과를 그대로 유지합니다.

## 접근성

- 의미 있는 순서 목록과 단계별 텍스트 설명을 제공합니다.
- 타임라인 제목을 `aria-labelledby`로 연결하고 전체 흐름의 대체 설명을
  제공합니다.
- 기존 드로어의 modal 의미 구조, Escape, 포커스 트랩·복귀와 스크롤 잠금을
  유지합니다.

## 검증

저장소 루트에서 다음을 실행합니다.

```bat
npm --prefix 01_frontend\visionflow-web run lint
npm --prefix 01_frontend\visionflow-web run build
py -3 -m py_compile scripts\visionflow_system_traceability_audit.py scripts\tests\test_visionflow_system_traceability_maintenance_mission_control.py
py -3 -m unittest discover -s scripts\tests -p "test_visionflow_system_traceability_*.py" -v
scripts\run-visionflow-system-traceability-audit.bat
scripts\run-visionflow-api-audit-ci.bat
```

런타임 반영 후 정상 기체와 작업·Incident가 연결된 기체의 `관제 상세`를
각각 열어 네 단계의 제목·설명·배지가 Backend 응답과 일치하는지 확인합니다.
