# VisionFlow 스마트폰 실센서 E2E 증적 카드

## 적용 범위

- `compose.yaml`
- `01_frontend/visionflow-web/src/app/dashboard/page.tsx`
- `01_frontend/visionflow-web/src/app/api/mobile/evidence/status/route.ts`
- `01_frontend/visionflow-web/src/components/dashboard/mobile-sensor-evidence-card.tsx`
- `01_frontend/visionflow-web/src/lib/mobile-evidence.ts`
- `01_frontend/visionflow-web/src/types/mobile-evidence-status.ts`

## 동작

`artifacts/mobile-readiness`에서 가장 최근의
`visionflow-smartphone-e2e-*.json`을 선택하고 같은 이름의 `.sha256`
파일로 무결성을 검증합니다. `/dashboard`에는 정확한 좌표, 원본 장치 ID,
운영자 키, 세션 토큰, 이미지 또는 영상을 노출하지 않는 요약 카드만
표시합니다.

Compose의 `frontend-web` 서비스에는 증적 폴더가 다음 경로로 읽기
전용 연결됩니다.

```text
./artifacts/mobile-readiness:/app/artifacts/mobile-readiness:ro
```

운영 환경은 `VISIONFLOW_MOBILE_EVIDENCE_DIRECTORY`로 위 컨테이너 경로를
명시하고, 로컬 기본값은 Frontend 프로젝트 아래의
`artifacts/mobile-readiness`로 제한됩니다. 보고서와 체크섬 파일명은 허용
패턴으로 검증한 뒤 읽으며, 동적 파일 경로는 Turbopack의 산출물 추적에서
제외합니다. 따라서 `output: "standalone"` 빌드가 저장소 전체를 의도치 않게
추적하지 않으면서 런타임 읽기 전용 마운트는 그대로 사용합니다.

## 적용 후 검증

프로젝트 루트 `C:\VisionFlow-Drone`에서 실행합니다.

```bat
docker compose --env-file .env.docker up -d --build --force-recreate frontend-web
docker compose --env-file .env.docker ps
curl.exe -sS "http://localhost:3000/api/mobile/evidence/status"
```

API 결과에서 아래 값을 확인합니다.

```json
{
  "available": true,
  "status": "SMARTPHONE_E2E_PASS",
  "integrity": "VERIFIED",
  "freshness": "FRESH"
}
```

이후 `http://localhost:3000/dashboard`에서
`스마트폰 실센서 E2E 증적` 카드를 확인합니다.

`available`이 `false`이면 먼저 실제 증적을 다시 생성합니다.

```bat
scripts\run-visionflow-mobile-evidence.bat --drone-id 3 --session-id 실제_UUID
```

새 증적을 만든 뒤에는 대시보드의 `새로고침`을 누릅니다. 증적 폴더는
바인드 마운트되어 있으므로 새 JSON을 반영하기 위해 컨테이너를 다시
빌드할 필요는 없습니다.
