# VisionFlow 비행 품질 MySQL 연동 프런트 패치

## 적용 대상

`C:\VisionFlow-Drone\01_frontend\visionflow-web`

ZIP 안의 `src` 폴더를 위 경로에 복사하고 기존 파일 덮어쓰기를
허용합니다. 기존 프로젝트 구조와 환경 설정 파일은 변경하지 않습니다.

## 변경 파일

1. `src\types\flight-quality-assessment.ts`
2. `src\app\api\drones\[id]\flight-sessions\[sessionId]\quality-assessment\route.ts`
3. `src\app\api\drones\[id]\flight-quality-assessments\route.ts`
4. `src\components\drones\flight-session-report-view.tsx`
5. `src\components\dashboard\fleet-reliability-dashboard.tsx`

## 구현 내용

- 백엔드 단일 품질 평가 GET/PUT Next.js 프록시
- 기체별 품질 평가 이력 GET Next.js 프록시
- HttpOnly 운영자 세션 전달 및 동일 출처 변경 요청 보호
- 세션 종합 보고서에서 MySQL 저장 평가 우선 표시
- 저장 평가가 없거나 조회할 수 없을 때 기존 브라우저 계산으로 대체
- OPERATOR/ADMIN 전용 `품질 재평가 저장` 버튼
- 기체별 운영 신뢰도에서 MySQL 저장 이력을 우선 사용
- JSON 증적에 평가 출처와 저장 평가 원본 포함

## 검증 명령

```bat
cd /d C:\VisionFlow-Drone\01_frontend\visionflow-web
npm run lint
npm run build
```

Docker 실행 환경에 반영할 때는 프로젝트 루트에서 다음을 실행합니다.

```bat
cd /d C:\VisionFlow-Drone
docker compose --env-file .env.docker up -d --build
```

## 화면 검증

1. `/operator-login`에서 OPERATOR 또는 ADMIN으로 로그인합니다.
2. `/drones`에서 완료·중단 세션을 불러온 뒤 `종합 보고서`를 엽니다.
3. `MySQL 저장 평가` 또는 `브라우저 임시 계산` 배지를 확인합니다.
4. `품질 재평가 저장`을 누르고 MySQL 저장 성공 문구를 확인합니다.
5. 페이지를 새로 고친 뒤에도 `MySQL 저장 평가`가 유지되는지 확인합니다.
6. `/fleet-reliability`에서 MySQL 저장 평가 개수와 임시 계산 개수를
   확인합니다.

저장 평가가 아직 없는 세션에서 `브라우저 임시 계산`이 보이는 것은
정상입니다. 해당 세션의 종합 보고서에서 재평가를 저장하면 이후
MySQL 값이 우선 사용됩니다.
