# VisionFlow 정비 SLA 마감 정합성 감시 패치 적용 및 검증

## 1. 패치 적용

ZIP 파일 내용을 `C:\VisionFlow-Drone`에 덮어씁니다.

이번 패치는 MySQL 스키마를 변경하지 않으므로 별도 migration 실행은
필요하지 않습니다.

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
Checks: 5/5 passed
```

## 6. 화면 검증

1. 브라우저에서 `http://localhost:3000/maintenance`를 엽니다.
2. `정비 SLA Incident 추적` 영역의 `마감 정합성` 패널을 확인합니다.
3. `정비 마감 필요`, `재운항 확인`, `운항 중지`, `수동 점검` 집계가
   목록의 상태 배지와 일치하는지 확인합니다.
4. `정비 마감 필요` 항목은 기존 순서대로 Incident 조치 완료 후
   정비 작업 마감을 실행합니다.
5. `정합성 점검 필요` 항목은 Incident 상태, 정비 작업 상태,
   비행 허가 상태를 확인합니다.

## 상태별 정상 판정

- Incident 활성 + 작업 `OPEN`/`IN_PROGRESS` + 허가
  `PENDING_INSPECTION`: `대응 진행`
- Incident 해결/종료 + 작업 `OPEN`/`IN_PROGRESS` + 허가
  `PENDING_INSPECTION`: `정비 마감 필요`
- Incident 해결/종료 + 작업 `COMPLETED` + 허가 `CLEARED`:
  `재운항 확인`
- Incident 해결/종료 + 작업 `GROUNDED` + 허가 `GROUNDED`:
  `운항 중지 확인`
- 그 밖의 조합 또는 연결 Incident 누락: `정합성 점검 필요`

## 참고

`정합성 점검 필요`는 서버가 상태를 자동 변경했다는 뜻이 아닙니다.
운영자가 데이터를 확인하도록 알려 주는 읽기 전용 진단 결과입니다.

조회 기간에 정비 작업이 없다면 모든 집계가 0으로 표시되는 것이
정상입니다.
