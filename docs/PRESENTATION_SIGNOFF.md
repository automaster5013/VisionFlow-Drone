# VisionFlow 발표 최종 사인오프

발표 운영 게이트, 3회 반복 리허설, 성능·병목 판정과 발표 당일 퀵체크를 하나의
최종 승인 계보로 재검증하고 안전한 증적 ZIP으로 묶습니다.

## 생성

프로젝트 루트 `C:\VisionFlow-Drone`에서 실행합니다.

```bat
scripts\run-visionflow-presentation-signoff.bat
```

최신 퀵체크가 `PRESENTATION_QUICK_CHECK_READY_WITH_DEFERRED`여야 하며 다음
연결을 모두 독립 재검증합니다.

1. `PRESENTATION_READY_WITH_DEFERRED`
2. `PRESENTATION_REHEARSAL_READY_WITH_DEFERRED`
3. `PRESENTATION_PERFORMANCE_READY_WITH_DEFERRED`
4. `PRESENTATION_QUICK_CHECK_READY_WITH_DEFERRED`

정상 결과:

```text
VisionFlow presentation final sign-off: PRESENTATION_SIGNOFF_READY_WITH_DEFERRED
Verified stages: 4/4
```

## 생성 파일

`artifacts\presentation-signoff\signoff-<UTC 시각>`:

- `visionflow-presentation-signoff.json`
- `visionflow-presentation-signoff.html`
- `visionflow-presentation-signoff.zip`
- `visionflow-presentation-signoff.sha256`

ZIP에는 네 단계의 JSON·HTML·SHA-256과 최종 사인오프 JSON·HTML,
`bundle-manifest.json`만 포함합니다.

다음 자료는 포함하지 않습니다.

- `yolo26n.pt`, `best.pt` 등 모델 가중치
- MySQL 백업·SQL dump
- 원본·분석 영상
- `.env.docker`와 운영자 키
- 인증서·개인키

## 독립 재검증

실제 생성된 JSON 경로를 사용합니다.

```bat
scripts\run-visionflow-presentation-signoff-verify.bat --report artifacts\presentation-signoff\signoff-<UTC 시각>\visionflow-presentation-signoff.json
```

정상 결과:

```text
VisionFlow presentation final sign-off: VERIFIED
Status: PRESENTATION_SIGNOFF_READY_WITH_DEFERRED
```

재검증기는 현재 원본 증적의 SHA-256 계보, 사인오프 JSON·HTML·ZIP sidecar,
ZIP 내부 manifest, 중복·경로 이탈·금지 파일을 다시 확인합니다.

## 휴대형 ZIP 재검증

다른 PC나 외장 매체에서는 원본 `artifacts` 폴더 없이 다음 두 파일만 함께
복사해 검증할 수 있습니다.

- `visionflow-presentation-signoff.zip`
- `visionflow-presentation-signoff.sha256`

두 파일을 예를 들어 `D:\VisionFlow-Signoff`에 복사했다면 프로젝트 루트에서
다음과 같이 실행합니다.

```bat
scripts\run-visionflow-presentation-signoff-bundle-verify.bat ^
  --bundle D:\VisionFlow-Signoff\visionflow-presentation-signoff.zip ^
  --sidecar D:\VisionFlow-Signoff\visionflow-presentation-signoff.sha256
```

ZIP과 sidecar가 같은 폴더에 있고 이름을 바꾸지 않았다면 `--sidecar`는
생략할 수 있습니다.

```bat
scripts\run-visionflow-presentation-signoff-bundle-verify.bat ^
  --bundle D:\VisionFlow-Signoff\visionflow-presentation-signoff.zip
```

정상 결과:

```text
VisionFlow presentation sign-off bundle: PORTABLE_VERIFIED
Status: PRESENTATION_SIGNOFF_READY_WITH_DEFERRED
Verified stages: 4/4
```

휴대형 검증은 외부 sidecar의 ZIP SHA-256, 내부 manifest, 15개 고정 경로,
4단계 JSON·HTML·sidecar, 단계별 식별자와 SHA-256 계보, 실행 가능한 HTML과
금지 파일 부재를 확인합니다. 서비스·DB·원본 증적에는 접근하지 않습니다.

이 절차는 읽기 전용 검증과 증적 파일 생성만 수행합니다. DB·서비스·모델을
변경하지 않으며 HP OMEN GPU·스마트폰 실센서·DJI 전용 연동을 실행하지 않습니다.
