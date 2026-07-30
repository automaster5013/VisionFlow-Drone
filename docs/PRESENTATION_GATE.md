# VisionFlow 발표 시연 원클릭 운영 게이트

발표 직전 서비스 기동부터 영속 데모, 전체 보안 인수, 릴리스 증빙과 2차 프로젝트
종결 증적까지 한 번에 확인하는 최종 운영 절차입니다.

## 원클릭 준비

프로젝트 루트 `C:\VisionFlow-Drone`에서 실행합니다.

`.env.docker`에는 RBAC에서 실제 사용 중인 다음 세 키가 있어야 합니다.

```dotenv
VISIONFLOW_VIEWER_KEY=<VIEWER 실제 키>
VISIONFLOW_OPERATOR_KEY=<OPERATOR 실제 키>
VISIONFLOW_ADMIN_KEY=<ADMIN 실제 키>
```

인수 스크립트는 셸의 `VISIONFLOW_ACCEPTANCE_*` 값이 없을 때 위 세 값을
`.env.docker`에서 메모리로만 읽습니다. 키 원문은 JSON·HTML 보고서와 콘솔에
기록하지 않습니다.

```bat
scripts\prepare-visionflow-presentation.bat
```

드론 ID가 1이 아니라면 첫 번째 인수로 지정합니다.

```bat
scripts\prepare-visionflow-presentation.bat 3
```

실행 순서는 다음과 같습니다.

1. Docker 통합 서비스 기동
2. MySQL 검증 백업 생성
3. 저장공간·보존 정책 감사
4. 격리·원위치 복구 리허설
5. AI 포함 전체 인수, 영속 데모, RBAC, 브라우저 세션·CSRF 검증
6. CSP 관찰 증적과 릴리스 준비도 생성
7. 릴리스 증빙 ZIP 및 SHA-256 생성
8. 발표 운영 게이트 JSON·HTML·SHA-256 생성
9. 전체 증적 무결성 카탈로그 갱신

정상 최종 결과:

```text
VisionFlow presentation gate: PRESENTATION_READY_WITH_DEFERRED
[PASS] VisionFlow presentation environment and evidence are ready.
```

## 판정만 다시 실행

서비스와 인수 테스트를 다시 실행하지 않고 최신 증적만 판정하려면 다음 명령을
사용합니다.

```bat
scripts\run-visionflow-presentation-gate.bat
```

이 명령은 원본 증적과 DB를 변경하지 않고
`artifacts\presentation-gate`에 다음 파일만 생성합니다.

- `visionflow-presentation-gate-<UTC 시각>.json`
- `visionflow-presentation-gate-<UTC 시각>.html`
- `visionflow-presentation-gate-<UTC 시각>.sha256`

기본 유효시간은 전체 인수 테스트, 릴리스 준비도, 릴리스 증빙 각각 2시간입니다.
발표 직전 원클릭 준비를 다시 실행하면 최신 증적으로 갱신됩니다.

## 독립 재검증

실제 생성된 JSON 파일명을 사용합니다.

```bat
scripts\run-visionflow-presentation-gate-verify.bat --report artifacts\presentation-gate\visionflow-presentation-gate-<UTC 시각>.json
```

정상 결과:

```text
VisionFlow presentation gate: VERIFIED
Status: PRESENTATION_READY_WITH_DEFERRED
```

재검증기는 JSON·HTML sidecar, 원본 증적의 크기와 SHA-256, 릴리스 증빙 ZIP 내부
manifest, 프로젝트 종결 보고서와 최종 이관 패키지, 그리고
인수 테스트 → 릴리스 준비도 → 릴리스 증빙의 연결을 다시 검사합니다.

## 보류 및 범위

다음 항목은 발표 게이트를 차단하지 않습니다.

- `DEFERRED`: 스마트폰 HTTPS 실센서 원본 텔레메트리 E2E
- `DEFERRED`: HP OMEN RTX 5060과 파인튜닝 `best.pt` 성능
- `DEFERRED`: 강제 CSP·HSTS 전환
- `OUT_OF_SCOPE`: DJI Mini 4 Pro RTSP·기체 종속 연동(3차 프로젝트)

## 처음 한 번 필요한 종결 증적

`artifacts\project-closeout`에 종결 보고서가 없다면, 최신 최종 이관 패키지가
유효한 상태에서 한 번 생성합니다.

```bat
scripts\run-visionflow-project-closeout.bat
```

종결 보고서는 발표 때마다 다시 만들 필요가 없습니다. 원본 최종 이관 ZIP과
`.sha256`은 계속 같은 위치에 보관해야 독립 재검증이 가능합니다.

## 실패 시

원클릭 준비가 실패하면 기존 진단 수집기가 자동 실행됩니다. 가장 먼저 실패한
단계의 콘솔 메시지와 다음 폴더를 확인합니다.

- `artifacts\diagnostics`
- `artifacts\visionflow-acceptance`
- `artifacts\release-readiness`
- `artifacts\presentation-gate`

실행 로그에 `VisionFlow presentation preflight`가 표시되면 이전
`prepare-visionflow-presentation.bat`가 남아 있는 것입니다. 최신 파일에는
`run-visionflow-security-release-gate.bat`와
`run-visionflow-presentation-gate.bat` 호출이 있어야 하며,
`run-visionflow-presentation-preflight.bat` 호출은 없어야 합니다.

운영자 키, `.env.docker`, 인증서 개인키, DB 백업 원본은 발표 보고서에 포함되지
않으며 외부에 공유하지 않습니다.
