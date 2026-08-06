# VisionFlow 정비 기체 관제 상세 드로어

기준 커밋: `1c2cae8d1e60948f0ee19d99394eea913f7262e5`

`/maintenance`의 함대 판정 카드에서 화면 이동 없이 기체별 정비 판단의
근거와 후속 대응을 확인하는 Frontend 상세 패널입니다. Backend API,
데이터베이스 스키마, 인증·권한 규칙은 변경하지 않습니다.

## 운영자 화면

- 함대 판정 카드의 `관제 상세` 버튼으로 우측 드로어를 엽니다.
- 현재 비행 가능·점검 대기·운항 중지 판정과 Backend 판정 사유를 가장
  위에 표시합니다.
- 비행 게이트 모드·적용 여부, 비행 허가, 정비 상태, 운항 판정을 함께
  보여줍니다.
- 함대 게이트, 작업지시, Incident·SLA, 최종 비행 판정을 4단계 근거
  타임라인으로 연결해 현재 판정이 만들어진 순서를 보여줍니다.
- 연결 작업이 있으면 Incident 상태·우선순위·담당자, SLA, 대응 상태,
  마감 정합성, 권장 대응과 마감 권고를 표시합니다.
- SLA Incident와 함대 비행 판정 시각 및 최신·지연·오래됨 상태를 드로어
  안에서도 확인할 수 있습니다.
- 기체 상세, 작업지시, Incident 보고서로 바로 이동할 수 있습니다.

## 데이터와 안전 경계

- 새 API를 호출하지 않고 Mission Control이 이미 검증한
  `/api/maintenance/sla/incidents`와 `/api/maintenance/flight-clearance`
  응답을 사용합니다.
- 함대 판정의 `workOrderId`와 SLA 추적 항목의 `workOrderId`가 같은 경우에만
  Incident·SLA 정보를 결합합니다.
- 드로어는 읽기 전용이며 POST·PUT·PATCH·DELETE 요청이나 Backend 재평가를
  수행하지 않습니다.
- 근거 타임라인은 이미 파싱된 판정 필드의 표시 순서와 색상만 결정하며
  비행 허가나 SLA 상태를 새로 계산하지 않습니다.
- 기존 same-origin 인증 프록시, RBAC, 작업 전이, DB 이력 규칙을 그대로
  유지합니다.

## 접근성

- `role="dialog"`, `aria-modal="true"`, 제목 연결을 제공합니다.
- 열릴 때 닫기 버튼으로 포커스를 이동하고 Escape와 배경 선택으로 닫습니다.
- Tab과 Shift+Tab 포커스가 열린 드로어 내부에서 순환합니다.
- 열린 동안 배경 스크롤을 잠그며 닫힌 뒤 원래 `관제 상세` 버튼으로
  포커스를 돌려보냅니다.

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

런타임 반영 후 `/maintenance`에서 함대 기체 카드의 `관제 상세`를 열고
판정·4단계 근거 타임라인·신선도·작업지시·Incident 영역, 직접 이동 링크,
Escape 닫기와 포커스 복귀를 확인합니다.
