# VisionFlow 정비 SLA 인라인 대응 패치 적용 및 검증

## 1. 패치 적용

ZIP 파일의 내용을 `C:\VisionFlow-Drone`에 덮어씁니다.

이 패치는 기존 파일 두 개와 문서 두 개만 포함하며 데이터베이스
migration은 없습니다.

## 2. Frontend 정적 검증

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
3. `정비 SLA Incident 추적`의 `운영자 대응 큐`를 확인합니다.
4. `담당자 지정 필요` 항목의 `내가 담당·대응 시작`을 누릅니다.
5. 성공 메시지와 함께 해당 항목이 `대응 중`으로 바뀌고 로그인한
   운영자 이름이 담당자로 표시되는지 확인합니다.

VIEWER 또는 비로그인 상태에서는 버튼이 비활성화되는 것이 정상입니다.

## 데이터가 없을 때

정비 작업이나 `ASSIGNMENT_REQUIRED` 항목이 0건이면 자동 검증은 정상
통과할 수 있지만 버튼의 수동 동작은 확인할 수 없습니다. SLA 초과 후
자동 상향되었고 아직 담당자가 없는 Incident가 생성된 뒤 다시
확인합니다.
