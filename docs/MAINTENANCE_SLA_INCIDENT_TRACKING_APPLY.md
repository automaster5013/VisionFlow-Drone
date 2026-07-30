# 적용 및 검증

## 1. 압축 적용

패치 ZIP의 `01_frontend`, `02_backend`, `scripts`, `docs` 폴더를
`C:\VisionFlow-Drone`에 덮어씁니다.

## 2. Backend 검증

```bat
cd /d C:\VisionFlow-Drone\02_backend\visionflow-api
gradlew.bat clean build
```

## 3. Frontend 검증

```bat
cd /d C:\VisionFlow-Drone\01_frontend\visionflow-web
npm run lint
npm run build
```

## 4. 서비스 반영

Docker 전체 스택을 사용하는 경우:

```bat
cd /d C:\VisionFlow-Drone
docker compose --env-file .env.docker up -d --build
```

로컬 프로세스로 실행 중이라면 백엔드와 프런트엔드를 각각
재시작합니다.

## 5. API 확인

Backend:

```bat
curl.exe -i "http://localhost:8080/api/maintenance/sla/incidents?windowDays=30"
```

Next.js proxy:

```bat
curl.exe -i "http://localhost:3000/api/maintenance/sla/incidents?windowDays=30"
```

기간 검증:

```bat
curl.exe -i "http://localhost:8080/api/maintenance/sla/incidents?windowDays=0"
```

앞의 두 요청은 `HTTP 200`, 기간이 0인 요청은 `HTTP 400`이 정상입니다.
최근 작업이 없으면 `items: []`와 0 집계가 반환되는 것도 정상입니다.

## 6. 화면 확인

브라우저에서 다음 주소로 이동합니다.

```text
http://localhost:3000/maintenance
```

`정비 우선조치 큐` 아래에 `정비 SLA Incident 추적` 패널이 표시되어야
합니다. 자동 상향된 항목은 `자동 상향 완료` 배지가 나타나며
`Incident 보고서` 버튼으로 종합 보고서를 열 수 있습니다.

## 7. 자동 인수 테스트

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-maintenance-sla-tracking-acceptance.bat
```

정상 결과:

```text
VisionFlow maintenance SLA tracking: MAINTENANCE_SLA_TRACKING_READY
Checks: 4/4 passed
```

증적은 다음 폴더에 생성됩니다.

```text
C:\VisionFlow-Drone\artifacts\maintenance-sla-tracking-acceptance
```
