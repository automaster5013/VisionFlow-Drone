# VisionFlow 정비 SLA 인라인 조치 완료 패치 적용 및 검증

## 1. 패치 적용

ZIP 파일 내용을 `C:\VisionFlow-Drone`에 덮어씁니다.

이 패치는 Frontend 컴포넌트와 기존 인수 스크립트만 갱신하며
데이터베이스 migration은 없습니다.

## 2. Frontend 검증

```bat
cd /d C:\VisionFlow-Drone\01_frontend\visionflow-web
npm run lint
npm run build
```

## 3. 서비스 반영

```bat
cd /d C:\VisionFlow-Drone
docker compose --env-file .env.docker up -d --build
```

## 4. 자동 검증

```bat
scripts\run-visionflow-maintenance-sla-tracking-acceptance.bat
```

정상 결과:

```text
VisionFlow maintenance SLA tracking: MAINTENANCE_SLA_TRACKING_READY
Checks: 5/5 passed
```

## 5. 화면 검증

1. `http://localhost:3000/operator-login`에서 OPERATOR 또는 ADMIN으로
   로그인합니다.
2. `http://localhost:3000/maintenance`를 엽니다.
3. `운영자 대응 큐`에서 `대응 중` 항목을 찾습니다.
4. `조치 완료`를 누르고 원인과 조치 결과를 3자 이상 입력합니다.
5. `해결 처리 확정`을 누릅니다.
6. 성공 메시지가 표시되고 항목이 `조치 종료`로 바뀌는지 확인합니다.
7. `Incident 보고서`에서 상태와 조치 이력을 확인합니다.

## 데이터가 없을 때

`대응 중` 항목이 0건이면 자동 검증은 통과할 수 있지만 조치 완료
버튼의 수동 동작은 확인할 수 없습니다. 먼저 `담당자 지정 필요`
항목에서 `내가 담당·대응 시작`을 실행한 뒤 검증합니다.

## 주의

이 버튼은 Incident를 해결 상태로 변경합니다. 정비 작업의
`COMPLETED` 상태나 비행 허가 `CLEARED` 상태를 자동으로 변경하지
않으므로, 실제 정비 완료 여부는 기존 정비 작업 절차에서 별도로
확인하고 처리합니다.
