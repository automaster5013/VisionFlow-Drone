# VisionFlow-Drone 2차 프로젝트 종결 보고서

이 단계는 LG GRAM에서 검증을 마친 2차 프로젝트 범위를 고정하고, 최종 이관
패키지를 근거로 발표·검토용 비민감 종결 보고서를 생성합니다.

## 전제 조건

- `artifacts/transfer-package`에 최근 24시간 이내 생성하고 검증한 최종 이관 ZIP과
  `.sha256`이 있어야 합니다.
- 최종 이관 ZIP 상태는 `TRANSFER_PACKAGE_READY_WITH_DEFERRED`여야 합니다.
- 이관 ZIP에는 실제 MySQL 백업이 포함되므로 외부 공개 파일로 취급하면 안 됩니다.

## 생성

프로젝트 루트 `C:\VisionFlow-Drone`에서 실행합니다.

```bat
scripts\run-visionflow-project-closeout.bat
```

정상 결과:

```text
VisionFlow project closeout: SECOND_PROJECT_CLOSED_WITH_DEFERRED
```

다음 네 파일이 `artifacts\project-closeout`에 생성됩니다.

- `visionflow-project-closeout-<UTC 시각>.json`
- `visionflow-project-closeout-<UTC 시각>.html`
- `visionflow-project-closeout-<UTC 시각>.md`
- `visionflow-project-closeout-<UTC 시각>.sha256`

HTML과 Markdown은 발표·검토용 비민감 인덱스입니다. 실제 DB 백업, 환경변수 값,
운영자 키, 인증서 개인키, 모델 가중치는 포함하지 않습니다.

## 독립 재검증

실제 생성된 JSON 경로를 사용합니다.

```bat
scripts\run-visionflow-project-closeout-verify.bat --report artifacts\project-closeout\visionflow-project-closeout-<UTC 시각>.json
```

정상 결과:

```text
VisionFlow project closeout: VERIFIED
Status: SECOND_PROJECT_CLOSED_WITH_DEFERRED
```

검증기는 다음을 다시 확인합니다.

- JSON·HTML·Markdown의 SHA-256 sidecar
- JSON과 HTML·Markdown의 내용 일치
- 원본 최종 이관 ZIP의 경로·크기·SHA-256
- 이관 ZIP 내부 파일·교차 참조 무결성
- 완료 기능, 보류 범위, 안전 메타데이터와 집계
- HTML에 실행 가능한 콘텐츠가 없는지 여부

## 종결 범위

2차 프로젝트 구현·검증 완료:

- 스마트폰·브라우저 기반 디지털 트윈 가상 드론 관제
- 전체 드론 실시간 텔레메트리·지도 통합
- MySQL 이력·과거 경로 재생
- 지오펜스·인시던트·SLA 운영
- 브라우저 영상 입력·YOLO 추론·탐지 증적
- RBAC·세션·CSRF·보안 헤더·CSP 관찰
- Docker 통합 운영과 백업·복구·릴리스·이관 검증

후속 검증:

- `DEFERRED`: HP OMEN 작업공간·데이터 복원
- `DEFERRED`: RTX 5060과 파인튜닝 `best.pt` 이식·성능 검증
- `DEFERRED`: 스마트폰 HTTPS 실센서 원본 텔레메트리 E2E 재검증
- `OUT_OF_SCOPE`: DJI Mini 4 Pro RTSP·기체 종속 연동(3차 프로젝트)

## 주의

종결 보고서는 최종 이관 ZIP을 대체하지 않습니다. 보고서에는 원본 ZIP의 경로와
SHA-256만 기록되며, 실제 이관 시에는 ZIP과 `.sha256`을 함께 안전하게 보관합니다.
