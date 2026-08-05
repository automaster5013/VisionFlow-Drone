# VisionFlow Frontend 산출물 파일 추적 가드

기준 커밋: `ca6e377b0bd55a2c489214ad7306eed5f150c5b5`

## 목적

Next.js 16 Turbopack의 `output: "standalone"` 빌드에서 모바일 증적 loader의
동적 파일 읽기가 저장소 전체를 NFT 목록에 포함하는 경고를 제거한다. 모바일
증적의 무결성·개인정보 보호 검증과 Docker 읽기 전용 마운트는 그대로 유지한다.

## 경로 정책

- 운영 경로는 `VISIONFLOW_MOBILE_EVIDENCE_DIRECTORY`로 명시한다.
- 로컬 기본 경로는 Frontend 프로젝트 내부
  `artifacts/mobile-readiness`로 한정한다.
- 저장소 상위 디렉터리를 탐색하는 fallback은 사용하지 않는다.
- 보고서·체크섬 파일은 기존 허용 파일명, 심볼릭 링크, 크기, SHA-256 검증을
  통과한 경우에만 읽는다.
- 런타임에서 결정되는 기본 디렉터리와 두 파일 경로에는
  `turbopackIgnore: true`를 표시해 빌드 시 전체 프로젝트 추적을 방지한다.

Compose의 운영 연결은 계속 다음과 같이 읽기 전용이다.

```text
./artifacts/mobile-readiness:/app/artifacts/mobile-readiness:ro
```

## 검증

저장소 루트에서 다음을 실행한다.

```bat
npm --prefix 01_frontend\visionflow-web run lint
npm --prefix 01_frontend\visionflow-web run build
py -3 -m unittest scripts.tests.test_visionflow_system_traceability_frontend_output_file_tracing -v
scripts\run-visionflow-system-traceability-audit.bat
scripts\run-visionflow-api-audit-ci.bat
```

프로덕션 빌드의 `Creating an optimized production build` 다음에
`Encountered unexpected file in NFT list` 경고가 없어야 한다. 추적성 감사에는
다음 항목이 `PASS`로 표시되어야 한다.

```text
[PASS] frontend-output-file-tracing-policy
```

이 변경은 Frontend 소스와 정적 감사만 변경한다. Backend API, AI API, DB,
인증·인가, 컨테이너 runtime 설정과 증적 내용은 변경하지 않는다.
