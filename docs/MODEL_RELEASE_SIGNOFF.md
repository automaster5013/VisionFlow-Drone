# VisionFlow 모델 릴리스 최종 승인

## 목적

모델 승격부터 5분 소크 결정까지의 증적을 읽기 전용으로 다시 검증하고,
발표·감사·재현 확인에 사용할 최소 안전 증빙 ZIP을 생성합니다.

검증 체인:

```text
MODEL_PROMOTION_READY
  → MODEL_RELEASE_PREPARED
  → MODEL_RELEASE_ACTIVATED
  → MODEL_SOAK_PASSED
  → MODEL_RELEASE_STABILIZED
  → MODEL_RELEASE_SIGNED_OFF
```

## LG GRAM에서 계획과 테스트만 확인

```bat
cd /d C:\VisionFlow-Drone
python -m unittest scripts.tests.test_visionflow_model_release_signoff -v
scripts\run-visionflow-model-release-signoff.bat plan
```

LG GRAM에서는 실제 `create`를 실행하지 않습니다.

## HP OMEN에서 최종 승인 생성

소크 결정 결과를 확인한 뒤 실행합니다.

```bat
scripts\run-visionflow-model-release-signoff.bat create
```

최신 결정 보고서를 자동으로 찾습니다. 특정 보고서를 지정하려면 다음과 같이
실행합니다.

```bat
scripts\run-visionflow-model-release-signoff.bat create ^
  --decision artifacts\model-soak-decision\decision-<UTC>\visionflow-model-soak-decision.json
```

## 결과 상태

### 최종 승인

```text
MODEL_RELEASE_SIGNED_OFF
```

`best.pt`의 승격·활성화·5분 소크·최종 결정이 모두 검증되었습니다. 명령 종료
코드는 `0`입니다.

### 승인 거절·안전 복귀

```text
MODEL_RELEASE_REJECTED_ROLLED_BACK
```

후보 모델은 승인되지 않았지만 `yolo26n.pt`로 안전하게 복귀했습니다. 증빙 ZIP은
생성되며 명령 종료 코드는 `1`입니다.

### 승인 차단

```text
MODEL_RELEASE_SIGNOFF_BLOCKED
```

롤백 실패 또는 불완전한 결정 상태입니다. 추가 모델 변경을 중단하고 결정 보고서와
Docker 로그를 확인해야 합니다.

## 생성 파일

```text
artifacts\model-release-signoff\signoff-<UTC>\
  visionflow-model-release-signoff.json
  visionflow-model-release-signoff.html
  visionflow-model-release-signoff.zip
  visionflow-model-release-signoff.sha256
```

독립 재검증:

```bat
scripts\run-visionflow-model-release-signoff-verify.bat ^
  --report artifacts\model-release-signoff\signoff-<UTC>\visionflow-model-release-signoff.json
```

## 증빙 ZIP 포함 범위

- 모델 승격 JSON·HTML·SHA-256
- 모델 릴리스 준비 JSON·HTML
- 모델 활성화 JSON·HTML·SHA-256
- 5분 소크 JSON·HTML·SHA-256
- 소크 결정 JSON·HTML·SHA-256
- 최종 승인 JSON·HTML
- 파일별 크기와 SHA-256을 기록한 번들 manifest

다음 파일은 포함하지 않습니다.

- `best.pt`, `yolo26n.pt` 및 기타 모델 가중치
- 고정 입력 영상
- `.env.docker`와 릴리스 환경 오버레이
- 인증서·개인키·운영자 키
- 명령 출력과 절대 경로

이 명령은 Docker·DB·모델·환경파일을 변경하지 않습니다.
