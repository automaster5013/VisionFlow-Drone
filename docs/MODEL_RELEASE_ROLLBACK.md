# VisionFlow 승격 모델 릴리스와 자동 롤백

## 목적

`MODEL_PROMOTION_READY`로 승인된 `best.pt`를 HP OMEN 운영 스택에 반영하고,
기동 또는 기본 인수 테스트가 실패하면 A/B 비교에 사용했던 `yolo26n.pt`로 자동
복귀합니다.

원본 `.env.docker`와 모델 가중치는 수정하지 않습니다. 승격·롤백 환경 오버레이를
별도로 생성하고 Docker Compose 실행 시 마지막 `--env-file`로 적용합니다.
모델 릴리스 준비 보고서는 검증된 HP OMEN 기본 런타임 활성화 보고서와
경로·크기·SHA-256으로 연결됩니다.

## 필수 조건

```text
HP_OMEN_RUNTIME_READY_WITH_DEFERRED 기본 활성화 보고서
MODEL_PROMOTION_READY 보고서
03_ai-server\visionflow-ai\models\best.pt
03_ai-server\visionflow-ai\models\yolo26n.pt
.env.docker
compose.yaml
compose.gpu.yaml
```

두 모델은 승격 보고서와 A/B 비교 보고서에 기록된 SHA-256과 일치해야 합니다.

## LG GRAM에서 계획과 테스트만 확인

```bat
cd /d C:\VisionFlow-Drone
python -m unittest scripts.tests.test_visionflow_model_release -v
scripts\run-visionflow-model-release.bat plan
```

정상 테스트 결과:

```text
Ran 14 tests
OK
```

`plan`은 환경파일, 모델, DB, Docker, 서비스를 변경하지 않습니다. 실제 증적과 GPU가
없는 LG GRAM에서는 `prepare`와 `activate`를 실행하지 않습니다.

## 1. HP OMEN에서 릴리스 준비

모델 승격 판정이 `MODEL_PROMOTION_READY`로 끝난 뒤 실행합니다.
이보다 먼저 `docs\HP_OMEN_RESTORE.md`의 최초 활성화가
`HP_OMEN_RUNTIME_READY_WITH_DEFERRED`로 완료되어 있어야 합니다. 기본 활성화
보고서가 없거나 JSON·HTML·SHA-256 검증에 실패하면 `prepare`는 산출물을 만들지
않고 차단됩니다.

```bat
scripts\run-visionflow-model-release.bat prepare
```

최신 승격 보고서를 자동 선택하며 다음 파일을 생성합니다.

```text
artifacts\model-release\release-<UTC>\
  visionflow-model-release.json
  visionflow-model-release.html
  visionflow-model-release.env
  visionflow-model-rollback.env
  visionflow-model-release.sha256
```

정상 결과:

```text
VisionFlow model release: MODEL_RELEASE_PREPARED
```

준비 단계는 Docker를 실행하거나 `.env.docker`와 모델 파일을 변경하지 않습니다.

## 2. 준비 결과 독립 검증

실제 생성된 경로를 사용합니다.

```bat
scripts\run-visionflow-model-release-verify.bat ^
  --report artifacts\model-release\release-<UTC>\visionflow-model-release.json
```

정상 결과:

```text
VisionFlow model release: VERIFIED
Status: MODEL_RELEASE_PREPARED
```

## 3. 승격 모델 활성화

이 명령은 HP OMEN의 Docker 스택을 `best.pt` 설정으로 다시 빌드·기동합니다.

```bat
scripts\run-visionflow-model-release.bat activate ^
  --report artifacts\model-release\release-<UTC>\visionflow-model-release.json ^
  --confirm ACTIVATE_PROMOTED_MODEL_WITH_ROLLBACK
```

실행 순서:

1. 승격 보고서·`best.pt`·`yolo26n.pt`·오버레이 재검증
2. 연결된 HP OMEN 기본 활성화 보고서와 이전 모델 릴리스 이력 검증
3. 승격 오버레이를 포함한 Compose 구성 검증
4. `best.pt`, CUDA 필수 설정으로 전체 스택 기동
5. 기본 자동 인수 테스트
6. 실패 시 `yolo26n.pt` 오버레이로 전체 스택 자동 복구
7. 실행 JSON·HTML·SHA-256 증적 생성

정상 결과:

```text
VisionFlow model release: MODEL_RELEASE_ACTIVATED
```

자동 복구 결과:

```text
VisionFlow model release: MODEL_RELEASE_ROLLED_BACK
```

롤백까지 실패한 경우:

```text
VisionFlow model release: MODEL_RELEASE_ACTIVATION_FAILED
```

`ROLLED_BACK`와 `ACTIVATION_FAILED`는 종료 코드 1을 반환하므로 원인을 확인한 뒤
재실행해야 합니다.

### 재실행 안전 규칙

- 동일한 `MODEL_RELEASE_PREPARED` 보고서는 성공·롤백 여부와 관계없이 한 번만
  실행할 수 있습니다.
- 자동 롤백이 성공했다면 원인을 수정한 뒤 `prepare`를 다시 실행해 새 준비
  보고서를 생성해야 합니다.
- 자동 롤백까지 실패했다면 운영 스택을 수동 복구하고 증적을 검토하기 전에는 새
  준비 보고서도 실행할 수 없습니다.
- 최신 실행 JSON·HTML·SHA-256이 손상되거나 변조되면 이전 정상 보고서로
  되돌아가지 않고 새 릴리스를 차단합니다.
- 정상적으로 새 준비 보고서를 실행하면 실행 보고서의 `activationGuard`에 직전
  실행 상태와 보고서 경로·크기·SHA-256이 기록됩니다.

## 4. 실행 결과 검증

```bat
scripts\run-visionflow-model-release-verify.bat ^
  --report artifacts\model-release\activation-<UTC>\visionflow-model-release-activation.json
```

검증기는 준비 보고서와 두 모델 SHA-256, 실행 단계 순서, 자동 롤백 결과,
HP 기본 활성화 연결, 직전 실행 이력, JSON·HTML·sidecar를 다시 확인합니다.

## 5. 배포 후 지속 안정성 확인

`MODEL_RELEASE_ACTIVATED`가 나오면 고정 더미 영상으로 5분 소크 게이트를 실행합니다.

```bat
scripts\run-visionflow-model-soak.bat run ^
  --input-file 03_ai-server\visionflow-ai\data\dummy\soak.mp4
```

정상 상태는 `MODEL_SOAK_PASSED`입니다. 자세한 입력 설정과 판정 기준은
`docs\MODEL_POST_RELEASE_SOAK.md`를 확인하세요.

소크 결과를 릴리스 확정 또는 기준 모델 자동 롤백으로 연결합니다.

```bat
scripts\run-visionflow-model-soak-decision.bat apply ^
  --confirm ROLLBACK_BLOCKED_MODEL_SOAK
```

- 소크 통과: `MODEL_RELEASE_STABILIZED`
- 소크 차단 후 기준 모델 복귀 성공: `MODEL_SOAK_ROLLED_BACK`
- 기준 모델 복귀 또는 인수 테스트 실패: `MODEL_SOAK_ROLLBACK_FAILED`

최종 결정 이후 전체 릴리스 증적을 승인·봉인합니다.

```bat
scripts\run-visionflow-model-release-signoff.bat create
```

승격 모델의 최종 정상 상태는 `MODEL_RELEASE_SIGNED_OFF`입니다.

## 안전 원칙

- `.env.docker`를 자동 편집하지 않습니다.
- `best.pt`와 `yolo26n.pt`를 복사·이동·덮어쓰지 않습니다.
- 준비 단계에서는 Docker와 DB를 변경하지 않습니다.
- 활성화 단계는 Docker 스택만 재구성하며 DB 복원·삭제를 실행하지 않습니다.
- HP 기본 활성화와 모델 릴리스를 별개로 우회 실행하지 않습니다.
- 하나의 준비 보고서를 반복 실행하지 않습니다.
- 소크 통과 확정은 읽기 전용이며, 소크 차단 롤백에만 확인 토큰과 Docker 재구성을
  요구합니다.
- 보고서에 환경값, 운영자 키, 절대 경로, 모델 원본을 기록하지 않습니다.
