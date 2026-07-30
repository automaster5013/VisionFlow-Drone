# 정비 SLA 추적 패널 SSR Hotfix

## 원인

`MaintenancePriorityPanel`이 서버 렌더링 시 우선조치 큐의 로딩 상태에서
조기 반환하여 `MaintenanceSlaIncidentTrackingPanel`이 최초 HTML에
포함되지 않았습니다. 브라우저 hydration 이후에는 표시될 수 있지만,
인수 테스트가 검사하는 서버 HTML에는 추적 패널 표식이 없었습니다.

## 수정

로딩 또는 우선조치 큐 조회 오류 상태에서도 SLA Incident 추적 패널을
독립적으로 렌더링합니다.

## 변경 파일

```text
01_frontend/visionflow-web/src/components/maintenance/maintenance-priority-panel.tsx
```

## 검증

```bat
cd /d C:\VisionFlow-Drone\01_frontend\visionflow-web
npm run lint
npm run build

cd /d C:\VisionFlow-Drone
docker compose --env-file .env.docker up -d --build
scripts\run-visionflow-maintenance-sla-tracking-acceptance.bat
```

정상 결과:

```text
VisionFlow maintenance SLA tracking: MAINTENANCE_SLA_TRACKING_READY
Checks: 4/4 passed
```
