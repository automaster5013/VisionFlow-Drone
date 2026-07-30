# VisionFlow HP OMEN 복원 및 최초 구동

## 목적

LG GRAM에서 생성한 최종 이관 패키지를 HP OMEN의 새 작업공간으로 안전하게 복원하고,
RTX GPU·`best.pt`·MySQL·전체 서비스·통합 인수 테스트를 고정된 순서로 검증합니다.
GPU 검증은 콘솔 성공 여부만 확인하지 않고 JSON·HTML·SHA-256 증적을 활성화
보고서에 연결합니다.

작업은 다음 다섯 구간으로 분리됩니다.

1. `inspect`: 패키지와 모든 중첩 ZIP을 읽기 전용으로 검증
2. `prepare`: 존재하지 않는 새 폴더에 안전 소스와 검증 증적을 추출
3. `preflight`: DB·Docker를 변경하지 않고 활성화 필수 입력을 일괄 점검
4. `activate`: 명시적 확인 후 DB 복원, GPU 스택 기동, HP 검증 실행
5. `recover`: 활성화 실패 보고서에 연결된 안전 백업으로 이전 상태 복구

스마트폰 실센서 HTTPS는 HP 런타임 안정화 후 별도로 진행하고, DJI Mini 4 Pro 전용
연동은 3차 프로젝트 범위를 유지합니다.

## 적용 파일

```text
C:\VisionFlow-Drone\scripts\visionflow_hp_omen_restore.py
C:\VisionFlow-Drone\scripts\run-visionflow-hp-omen-restore.bat
C:\VisionFlow-Drone\scripts\run-visionflow-hp-omen-restore-verify.bat
C:\VisionFlow-Drone\scripts\tests\test_visionflow_hp_omen_restore.py
C:\VisionFlow-Drone\docs\HP_OMEN_RESTORE.md
```

## LG GRAM에서 지금 확인

아래 명령은 DB, Docker, 서비스, 기존 파일을 변경하지 않습니다.

```bat
cd /d C:\VisionFlow-Drone
python -m unittest scripts.tests.test_visionflow_hp_omen_restore -v
scripts\run-visionflow-hp-omen-restore.bat plan
```

정상 테스트 결과:

```text
Ran 28 tests
OK
```

HP OMEN이 준비되기 전에는 `activate`를 실행하지 않습니다.

## 이관 매체 자동 생성

이관 직전 전체 갱신이 `PRE_TRANSFER_REFRESH_READY`로 끝난 뒤 다음을 외장 SSD 등
관리 가능한 이관 매체에 복사합니다. 파일을 수동으로 고르지 말고 전용 스테이징
도구를 사용합니다.

```bat
scripts\run-visionflow-transfer-media.bat stage ^
  --destination "D:\VisionFlow-Transfer-20260725" ^
  --confirm STAGE_VERIFIED_TRANSFER_MEDIA
```

복사가 끝나면 LG GRAM에서 바로 재검증합니다.

```bat
scripts\run-visionflow-transfer-media-verify.bat ^
  --media "D:\VisionFlow-Transfer-20260725"
```

자세한 설명은 `docs\TRANSFER_MEDIA.md`를 참고하세요.

최종 이관 ZIP은 실제 MySQL 백업을 포함하므로 공개 클라우드나 공용 폴더에 올리지
마세요. `.env.docker`, 운영 키, 인증서 개인키, `best.pt`는 이 ZIP에 들어 있지
않습니다.

## 1. HP에서 패키지 읽기 전용 확인

이관 매체 루트에서 실제 경로를 사용합니다.

```bat
D:
cd \VisionFlow-Transfer-20260725
tools\scripts\run-visionflow-hp-omen-restore.bat inspect ^
  --package "package\visionflow-transfer-package-{실제시각}.zip"
```

정상 결과:

```text
VisionFlow HP OMEN transfer package: VERIFIED
Status : TRANSFER_PACKAGE_READY_WITH_DEFERRED
```

`inspect`는 파일을 생성하거나 DB·Docker를 변경하지 않습니다.

## 2. 새 HP 작업공간 준비

대상 경로는 존재하지 않아야 합니다. 기존 폴더는 비어 있어도 덮어쓰지 않습니다.
`C:\VisionFlow-Drone`이 이미 존재한다면 삭제하지 말고
`C:\VisionFlow-Drone-HP` 같은 새 경로를 사용합니다.

```bat
scripts\run-visionflow-hp-omen-restore.bat prepare ^
  --package "D:\VisionFlow-Transfer\visionflow-transfer-package-{실제시각}.zip" ^
  --destination "C:\VisionFlow-Drone" ^
  --confirm PREPARE_HP_OMEN_WORKSPACE
```

정상 상태:

```text
HP_OMEN_WORKSPACE_PREPARED_WITH_DEFERRED
```

준비 단계가 자동으로 수행하는 작업:

- 최종 패키지와 바깥 sidecar 검증
- 내부 핸드오프·전송 준비도·MySQL 백업 검증
- 핸드오프 안의 안전 소스·릴리스 증빙·LG baseline 검증
- 안전 소스를 새 작업공간에만 추출
- 원본 패키지와 핵심 증적을 표준 `artifacts`, `backups` 경로에 배치
- 추출된 전체 소스를 `SOURCE_MANIFEST.json`과 다시 비교

준비 단계는 DB 복원, Docker 실행, 기존 대상 덮어쓰기, 영구 삭제를 수행하지
않습니다.

## 3. 준비 결과 재검증

HP 작업공간으로 이동해 실제 보고서 이름을 사용합니다.

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-hp-omen-restore-verify.bat ^
  --report artifacts\hp-omen-restore\visionflow-hp-omen-prepare-{실제시각}.json
```

정상 결과:

```text
VisionFlow HP OMEN restore report: VERIFIED
Status: HP_OMEN_WORKSPACE_PREPARED_WITH_DEFERRED
```

## 4. HP 전용 파일과 런타임 준비

다음 항목은 최종 패키지에 의도적으로 포함되지 않습니다.

1. `.env.docker.example`을 참고해 HP 전용 `.env.docker` 작성
2. `best.pt`를 다음 위치에 별도 복사
3. NVIDIA 최신 드라이버와 Docker Desktop 설치·실행
4. `nvidia-smi`와 `docker version`이 정상인지 확인
5. GPU용 `compose.gpu.yaml`과 GPU preflight 모듈이 최신 소스에 있는지 확인

모델의 고정 경로:

```text
C:\VisionFlow-Drone\03_ai-server\visionflow-ai\models\best.pt
```

환경파일과 운영 키 값을 보고서나 채팅에 붙여넣지 마세요.

## 5. 역할 키를 현재 터미널에만 설정

```bat
set VISIONFLOW_ACCEPTANCE_VIEWER_KEY=<실제 VIEWER 키>
set VISIONFLOW_ACCEPTANCE_OPERATOR_KEY=<실제 OPERATOR 키>
set VISIONFLOW_ACCEPTANCE_ADMIN_KEY=<실제 ADMIN 키>
```

## 6. 활성화 직전 안전 사전점검

역할 키를 설정한 동일한 명령 프롬프트에서 다음 명령을 먼저 실행합니다.

```bat
scripts\run-visionflow-hp-omen-restore.bat preflight
```

특정 준비 보고서나 모델 경로를 고정하려면 다음처럼 실행합니다.

```bat
scripts\run-visionflow-hp-omen-restore.bat preflight ^
  --prepare-report artifacts\hp-omen-restore\visionflow-hp-omen-prepare-{실제시각}.json ^
  --model 03_ai-server\visionflow-ai\models\best.pt
```

정상 상태:

```text
HP_OMEN_ACTIVATION_PREFLIGHT_READY
```

사전점검은 다음 일곱 항목을 한 번에 확인합니다.

1. Windows HP OMEN 대상 환경
2. 준비 보고서·추출 소스·이관 패키지·백업의 무결성
3. HP 전용 `.env.docker`
4. `compose.gpu.yaml`
5. 고정 경로의 `best.pt`와 SHA-256
6. 최초 구동 필수 배치 스크립트
7. VIEWER·OPERATOR·ADMIN 역할 키의 존재 여부

환경값과 역할 키의 실제 값, 모델 원본은 보고서에 기록하지 않습니다. 이 명령은
MySQL 복원, Docker·서비스 기동, 영구 삭제를 수행하지 않습니다. 결과 JSON·HTML·
SHA-256은 `artifacts\hp-omen-restore`에 생성됩니다.

생성된 실제 JSON 이름으로 독립 재검증할 수 있습니다.

```bat
scripts\run-visionflow-hp-omen-restore-verify.bat ^
  --report artifacts\hp-omen-restore\visionflow-hp-omen-preflight-{실제시각}.json
```

사전점검이 `BLOCKED`이면 보고서의 실패 항목을 수정한 뒤 다시 실행합니다.
`READY`가 되기 전에는 `activate`로 넘어가지 않습니다.

## 7. DB 복원과 최초 구동

이 명령은 실제 MySQL과 영속 증적을 복원하고 GPU Docker 스택을 시작합니다. 복원
직전 HP의 현재 상태를 별도 안전 백업으로 먼저 저장합니다.

```bat
scripts\run-visionflow-hp-omen-restore.bat activate ^
  --confirm ACTIVATE_HP_OMEN_WITH_DB_RESTORE
```

기본 실행 순서:

1. 복원 전 HP 상태 안전 백업
2. 검증된 MySQL·영속 증적 복원
3. RTX GPU와 `best.pt` 로딩 및 호스트·컨테이너 SHA-256 동일성 확인
4. `GPU_MODEL_READY` JSON·HTML·SHA-256 증적 생성
5. GPU Compose 전체 스택 빌드·기동
6. HP target 프로필 생성
7. LG baseline과 HP target 비교
8. Demo·RBAC·브라우저 세션 통합 인수 테스트
9. GPU 벤치마크는 별도 입력 영상이 준비될 때까지 보류

정상 상태:

```text
HP_OMEN_RUNTIME_READY_WITH_DEFERRED
```

### 활성화 재실행 이력 게이트

`activate`는 명령을 실행하기 전에 `artifacts\hp-omen-restore`의 최신 활성화·복구
보고서를 검증합니다. 다음 규칙은 옵션 없이 자동 적용됩니다.

- 활성화 이력이 없으면 최초 활성화를 허용합니다.
- 최신 활성화가 성공 상태이면 중복 DB 복원과 스택 재기동을 차단합니다.
- 최신 활성화가 실패 상태이고 복구 보고서가 없으면 재시도를 차단합니다.
- 최신 실패 보고서와 경로·SHA-256으로 정확히 연결된 성공 복구 보고서가 있을
  때만 한 번의 재시도를 허용합니다.
- 최신 복구 보고서가 실패 상태이거나 JSON·HTML·SHA-256이 변조됐으면 이전의
  정상 복구 보고서로 되돌아가지 않고 재시도를 차단합니다.

복구 후 재시도가 성공하면 활성화 보고서의 `activationLineage`에 이전 실패
활성화 보고서와 성공 복구 보고서의 경로·크기·SHA-256이 함께 기록됩니다. 재시도가
다시 실패하면 그 새 실패 보고서에 대해 `recover`를 다시 완료해야 합니다.
성공 후 모델을 바꿀 때는 `activate`를 다시 실행하지 말고 별도 모델 릴리스·전환
절차를 사용합니다.

## GPU 벤치마크까지 함께 실행

고정 입력 영상 또는 브라우저 프레임이 실제로 들어오는 상태에서만 옵션을 추가합니다.

```bat
scripts\run-visionflow-hp-omen-restore.bat activate ^
  --run-benchmark ^
  --confirm ACTIVATE_HP_OMEN_WITH_DB_RESTORE
```

입력 프레임이 없으면 벤치마크 샘플이 만들어지지 않아 해당 단계가 실패합니다.

## 8. 최초 구동 결과 재검증

```bat
scripts\run-visionflow-hp-omen-restore-verify.bat ^
  --report artifacts\hp-omen-restore\activation-{실제시각}\visionflow-hp-omen-activation.json
```

검증기는 다음 연결을 다시 확인합니다.

- 준비 보고서와 원본 최종 이관 패키지
- 추출 소스와 `SOURCE_MANIFEST.json`
- 복원 전 안전 백업
- GPU 사전점검 JSON·HTML·SHA-256과 현재 `best.pt`
- `best.pt` 경로·크기·SHA-256
- HP target `TARGET_READY`
- LG/HP 소스 manifest `MATCH`
- 통합 인수 테스트 전체 PASS
- 선택 실행한 GPU 벤치마크
- 최초 활성화 또는 실패·복구·재시도 실행 이력 연결

## 실패 시 원칙

- 실패한 단계 뒤의 작업은 실행하지 않습니다.
- 단계별 로그와 실패 JSON·HTML 보고서를 보존합니다.
- DB 복원 단계에서 안전 백업이 생성됐다면 실패 보고서의 `artifacts`에 즉시
  연결합니다. 뒤 단계가 실패해도 복구 원본 경로와 SHA-256이 사라지지 않습니다.
- 기존 작업공간을 자동 삭제하거나 덮어쓰지 않습니다.
- DB 복원 실패 시 기존 백업 도구의 안전 정책에 따라 애플리케이션 서비스가 중지된
  상태로 남을 수 있으므로 실패 보고서와 Docker 상태를 먼저 확인합니다.
- `best.pt`, 환경값, 운영 키 원문은 보고서에 기록하지 않습니다.

## 9. 활성화 실패 후 이전 상태 복구

복구는 다음 조건을 모두 충족한 실패 보고서에만 허용됩니다.

- 상태가 `HP_OMEN_RUNTIME_ACTIVATION_FAILED`
- DB 복원 시도 전에 생성된 안전 백업이 보고서에 연결됨
- 실패 보고서 JSON·HTML·SHA-256이 일치함
- 연결된 안전 백업 ZIP의 manifest와 모든 파일 SHA-256이 유효함

성공한 활성화 보고서, 안전 백업이 없는 실패 보고서 또는 변조된 백업은 복구
원본으로 사용할 수 없습니다.

실패 보고서의 실제 경로를 지정하고 명시적으로 확인합니다.

```bat
scripts\run-visionflow-hp-omen-restore.bat recover ^
  --report artifacts\hp-omen-restore\activation-{실제시각}\visionflow-hp-omen-activation.json ^
  --confirm RECOVER_FAILED_HP_OMEN_ACTIVATION
```

복구 명령은 실패 이전 안전 백업을 다시 검증한 후 MySQL과 영속 증적을 되돌립니다.
이 복구 자체를 실행하기 직전에도 현재 상태를 새로운 `backups\pre-restore` 안전
백업으로 보존합니다.

정상 상태:

```text
HP_OMEN_PRE_ACTIVATION_STATE_RECOVERED
```

생성된 복구 보고서는 다음처럼 독립 재검증합니다.

```bat
scripts\run-visionflow-hp-omen-restore-verify.bat ^
  --report artifacts\hp-omen-restore\recovery-{실제시각}\visionflow-hp-omen-recovery.json
```

복구 보고서는 실패 활성화 보고서, 원래 롤백 백업, 복구 직전 새 안전 백업의
경로·크기·SHA-256을 교차 검증합니다. 자동 복구는 수행하지 않으며 정확한 확인
문자열이 있어야만 DB 변경을 시작합니다.
