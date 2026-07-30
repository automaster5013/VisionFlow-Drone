# 적용 및 검증

## 1. 패치 적용

ZIP 파일을 `C:\VisionFlow-Drone`에 덮어씁니다.

## 2. Backend

```bat
cd /d C:\VisionFlow-Drone\02_backend\visionflow-api
gradlew.bat clean build
```

## 3. Frontend

```bat
cd /d C:\VisionFlow-Drone\01_frontend\visionflow-web
npm run lint
npm run build
```

## 4. 서비스 반영

```bat
cd /d C:\VisionFlow-Drone
docker compose --env-file .env.docker up -d --build
```

## 5. 자동 검증

```bat
scripts\run-visionflow-maintenance-sla-tracking-acceptance.bat
```

정상 결과:

```text
VisionFlow maintenance SLA tracking: MAINTENANCE_SLA_TRACKING_READY
Checks: 4/4 passed
```

## 6. 화면 검증

```text
http://localhost:3000/maintenance
```

`정비 SLA Incident 추적` 내부에 `운영자 대응 큐`가 표시되어야 합니다.
정비 작업 데이터가 없으면 모든 집계가 0건인 것이 정상입니다.

자동 상향된 활성 Incident에 담당자가 없으면 `담당자 지정 필요`,
담당자가 있으면 `대응 중`, 해결 또는 종료 상태면 `조치 종료`로
표시됩니다.
