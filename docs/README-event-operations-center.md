# VisionFlow 통합 이벤트 관제 센터

기준 커밋: `99f3a68c56b3c842d64dddf6df07c011dd4fdf5e`

## 목적

좌측 사이드바의 기존 `/events` 경로를 실제 운영 화면으로 연결한다. AI 추론,
AI 경보, 지오펜스 위반과 Incident를 별도 화면에서 찾아다니지 않고 하나의
읽기 전용 타임라인에서 확인하고 후속 관제로 이동할 수 있게 한다.

## 데이터 경계

- `/api/drones`
- `/api/ai/events?limit=100`
- `/api/ai/alerts?limit=200`
- `/api/geofences/events?activeOnly=false&limit=100`
- `/api/incidents?limit=200`

위 API는 모두 이미 존재하는 same-origin Route Handler다. 브라우저는 Backend
주소나 운영 키에 직접 접근하지 않고, Route Handler가 기존 운영자 인증을
전달한다. 이 기능은 새 API, 변경 요청, DB migration 또는 권한 변경을 만들지
않는다.

## 화면 동작

- 미확인 AI 경보, 대응 중 Incident, 활성 지오펜스, 최근 1시간 AI 추론 KPI
- 네 소스의 정상·부분 장애 상태와 마지막 정상 갱신 시각
- 소스·기체·위험도·대응 상태·시간 범위·검색 조합 필터
- 발생 시각 최신 순 통합 타임라인과 최대 100건 표시 제한
- 15초 자동 갱신, 수동 갱신, 숨겨진 탭 자동 조회 생략
- AbortController와 요청 순번을 통한 오래된 응답 덮어쓰기 방지
- `Promise.allSettled` 기반 소스별 장애 격리와 마지막 유효 데이터 유지
- 이벤트 상세 드로어에서 원본 상태·근거·탐지 증적과 기체·리플레이·Incident
  직접 링크 제공

## 접근성

상세 드로어는 modal dialog 의미 구조, Escape 닫기, 내부 Tab 포커스 순환,
배경 스크롤 잠금, 닫은 뒤 열기 버튼으로의 포커스 복귀를 제공한다. 부분 장애
알림과 로딩 상태는 보조 기술에 전달된다.

## 회귀 방지

`event-operations-center-ui-policy`는 페이지 mount, 네 소스 조회·응답 검증,
15초 갱신, 부분 장애 격리, 필터·타임라인, 읽기 전용 상세 드로어, 접근성,
직접 링크와 GitHub Actions push·pull request 경로 trigger를 함께 검사한다.

로컬 검사는 다음 순서로 실행한다.

```bat
npm --prefix 01_frontend\visionflow-web run lint
py -3 -m unittest discover -s scripts\tests -p "test_visionflow_system_traceability_*.py" -v
scripts\run-visionflow-system-traceability-audit.bat
scripts\run-visionflow-api-audit-ci.bat
```
