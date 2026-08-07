# VisionFlow 운영 통계 센터

## 목적

왼쪽 사이드바의 `통계` 메뉴가 연결하는 `/statistics` 화면이다. 새로운 집계 API나
DB 테이블을 만들지 않고 기존 운영 데이터 네 소스를 읽어, 비행·AI·품질·정비
성과를 한 화면에서 비교한다.

## 데이터 소스

| 영역 | same-origin 읽기 API | 화면 표본 |
| --- | --- | --- |
| 비행 세션 | `/api/dashboard/operations` | 선택한 최근 7·30·90일 |
| 함대 신뢰도 | `/api/flight-quality/fleet-reliability` | 기체별 최신 최대 20개 평가 |
| 정비 성과 | `/api/maintenance/metrics` | 선택한 최근 7·30·90일 |
| AI 처리 | `/api/ai/metrics/status` | 현재 누적·롤링 런타임 스냅샷 |

모든 브라우저 요청은 기존 Next.js 프록시를 거친다. Backend 운영자 인증과 AI
내부 서비스 키는 서버 경계에서만 전달되며 클라이언트 번들에 포함되지 않는다.

## 화면 구성

- 종료 세션 기준 비행 완료율, 함대 평균 품질 점수, 처리 프레임 기준 AI 탐지율,
  정비 작업지시 해결률을 상단 KPI로 표시한다.
- 처리 프레임이나 정비 작업지시처럼 비율의 표본이 0건인 경우 `0%`로 오인되지
  않도록 `—`를 표시하고 실제 표본 수를 함께 안내한다.
- 세션과 작업지시 상태 분포, AI FPS·추론 지연·드롭률, 기체별 품질 추세,
  최신 함대 비행 허가를 제공한다.
- 운영 대시보드, 신뢰도 상세, 정비 관제, AI 미리보기로 이동하는 읽기 전용
  링크만 제공한다.
- 기간이 적용되지 않는 최신 평가·런타임·비행 허가에는 표본 범위를 별도로
  명시한다.

## 갱신과 부분 장애

- 네 API는 `Promise.allSettled`로 동시에 조회해 한 소스의 실패가 전체 화면을
  비우지 않게 한다.
- 응답을 각 타입 파서로 검증한 뒤에만 상태를 교체한다. 실패한 소스는 마지막
  정상값을 유지하고 상단 소스 배지와 `aria-live` 안내에 상태를 표시한다.
- 30초 자동 갱신과 수동 갱신을 지원하며 숨겨진 탭에서는 주기 조회를 건너뛴다.
- 새 조회는 기존 요청을 취소하고 요청 순번도 확인해 늦은 응답의 역전 반영을 막는다.

## 변경하지 않는 경계

- Backend·AI API와 operation 수
- DB migration, Entity, Repository, FK
- RBAC, 운영자 세션, 서비스 키 정책
- 컨테이너·서비스·예약 작업
- 모든 쓰기·상태 전이 동작

## 검증

```bat
npm --prefix 01_frontend\visionflow-web run lint
npm --prefix 01_frontend\visionflow-web run build
py -3 -m unittest scripts.tests.test_visionflow_system_traceability_operations_statistics_center -v
scripts\run-visionflow-system-traceability-audit.bat
scripts\run-visionflow-api-audit-ci.bat
```
