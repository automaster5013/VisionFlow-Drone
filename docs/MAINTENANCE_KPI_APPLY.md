# VisionFlow 정비 운영 KPI 대시보드 패치

이 패치는 기존 `maintenance_work_order`와 함대 비행 허가 데이터를 읽기 전용으로
집계해 `/maintenance` 화면에 정비 KPI를 표시합니다.

## 1. 적용

ZIP의 내용을 다음 프로젝트 루트에 덮어씁니다.

```text
C:\VisionFlow-Drone
```

기존 파일을 수정하므로 적용 전에 현재 작업 내용을 커밋하거나 백업해 두는 것을
권장합니다. 데이터베이스 마이그레이션은 추가되지 않습니다.

## 2. 주요 추가 경로

백엔드:

```text
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\java\com\visionflow\api\maintenance\controller\MaintenanceMetricsController.java
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\java\com\visionflow\api\maintenance\service\MaintenanceMetricsService.java
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\java\com\visionflow\api\maintenance\dto\MaintenanceMetricsResponse.java
C:\VisionFlow-Drone\02_backend\visionflow-api\src\test\java\com\visionflow\api\maintenance\service\MaintenanceMetricsServiceTests.java
```

프런트엔드:

```text
C:\VisionFlow-Drone\01_frontend\visionflow-web\src\app\api\maintenance\metrics\route.ts
C:\VisionFlow-Drone\01_frontend\visionflow-web\src\components\maintenance\maintenance-metrics-panel.tsx
C:\VisionFlow-Drone\01_frontend\visionflow-web\src\types\maintenance-metrics.ts
```

## 3. 빌드 검증

백엔드:

```bat
cd /d C:\VisionFlow-Drone\02_backend\visionflow-api
gradlew.bat clean build
```

프런트엔드:

```bat
cd /d C:\VisionFlow-Drone\01_frontend\visionflow-web
npm run lint
npm run build
```

## 4. API 검증

전체 서비스를 다시 시작한 후 실행합니다.

```bat
curl.exe -i "http://localhost:8080/api/maintenance/metrics?windowDays=30"
curl.exe -i "http://localhost:3000/api/maintenance/metrics?windowDays=30"
```

두 요청 모두 `HTTP 200`이어야 하며, 다음 핵심 필드가 표시되어야 합니다.

```text
totalWorkOrders
resolutionRatePercent
averageStartDelayMinutes
averageResolutionMinutes
gateMode
allowedDrones
attentionDrones
blockedDrones
```

잘못된 기간 검증:

```bat
curl.exe -i "http://localhost:3000/api/maintenance/metrics?windowDays=0"
```

정상적으로 `HTTP 400`이 반환되어야 합니다.

## 5. 화면 검증

```text
http://localhost:3000/maintenance
```

확인 항목:

1. `정비 운영 현황` 카드가 표시됩니다.
2. 7일·30일·90일 버튼을 누르면 기간별 값이 다시 조회됩니다.
3. 작업 상태 분포에 점검 대기·점검 중·재운항 승인·운항 중지가 표시됩니다.
4. 현재 함대 비행 게이트에 허용·주의·차단 대수가 표시됩니다.
5. 점검 시작·완료 또는 Incident 동기화 후 KPI가 자동 갱신됩니다.

저장된 작업이 없으면 작업 수와 완료율이 `0`이고 평균 시간은 `-`로 표시되는 것이
정상입니다.

## 집계 기준

- 조회 기간: 작업의 `openedAt` 기준
- 평균 점검 착수: `openedAt`부터 `startedAt`까지
- 평균 처리시간: `openedAt`부터 `completedAt`까지
- 처리 완료: `COMPLETED`와 `GROUNDED`를 모두 포함
- 함대 허용·주의·차단: 현재 비행 게이트의 실시간 판단
- 읽기 전용 API이며 정비 상태나 데이터베이스를 변경하지 않음
