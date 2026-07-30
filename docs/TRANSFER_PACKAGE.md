# VisionFlow HP OMEN 최종 오프라인 이관 세트

## 1. 목적

LG GRAM에서 검증한 최신 마이그레이션 핸드오프, 전송 준비도 보고서, 실제 MySQL 백업을
하나의 독립 검증 가능한 ZIP으로 묶습니다. 기존 파일은 수정하거나 삭제하지 않으며
`artifacts\transfer-package`에 새 산출물만 생성합니다.

이 패키지는 실제 데이터베이스 백업을 포함하므로 소스 릴리스나 일반 발표 증빙보다 민감합니다.
공개 Git 저장소, 공개 클라우드 링크, 메신저 공개방에 업로드하면 안 됩니다.

## 2. 반영 파일

| 파일 | 전체 경로 |
|---|---|
| 생성·검증 본체 | `C:\VisionFlow-Drone\scripts\visionflow_transfer_package.py` |
| 생성 명령 | `C:\VisionFlow-Drone\scripts\run-visionflow-transfer-package.bat` |
| 독립 검증 명령 | `C:\VisionFlow-Drone\scripts\run-visionflow-transfer-package-verify.bat` |
| 단위 테스트 | `C:\VisionFlow-Drone\scripts\tests\test_visionflow_transfer_package.py` |
| 안내 문서 | `C:\VisionFlow-Drone\docs\TRANSFER_PACKAGE.md` |

## 3. 선행 조건

다음 단계가 최신 코드 기준으로 통과해야 합니다.

```bat
scripts\run-visionflow-release-gate.bat
scripts\run-visionflow-release-evidence.bat
scripts\run-visionflow-source-release.bat
scripts\run-visionflow-machine-profile.bat
scripts\run-visionflow-migration-handoff.bat
scripts\run-visionflow-cold-start-rehearsal.bat
scripts\run-visionflow-transfer-readiness.bat
```

필수 최종 상태:

```text
VisionFlow transfer readiness: TRANSFER_READY_WITH_DEFERRED
```

마이그레이션 핸드오프가 기록한 MySQL 백업 ZIP이 `backups` 폴더에 그대로 있어야 합니다.
다른 최신 백업을 임의로 선택하지 않으며 기록된 크기와 SHA-256이 정확히 일치해야 합니다.

## 4. 최종 이관 세트 생성

실제 MySQL 백업이 포함된다는 사실을 명시적으로 확인한 뒤 실행합니다.

```bat
scripts\run-visionflow-transfer-package.bat --confirm INCLUDE_VERIFIED_BACKUP
```

정상 결과:

```text
VisionFlow transfer package: CREATED
Status: TRANSFER_PACKAGE_READY_WITH_DEFERRED
Bundle: C:\VisionFlow-Drone\artifacts\transfer-package\visionflow-transfer-package-....zip
SHA-256: C:\VisionFlow-Drone\artifacts\transfer-package\visionflow-transfer-package-....sha256
[SENSITIVE] 실제 MySQL 백업이 포함됐습니다. 공개 저장소에 업로드하지 마세요.
```

최신 파일 자동 선택 대신 특정 결과를 고정할 수 있습니다.

```bat
scripts\run-visionflow-transfer-package.bat ^
  --readiness artifacts\transfer-readiness\visionflow-transfer-readiness-{실제시각}.json ^
  --handoff artifacts\migration-handoff\visionflow-migration-handoff-{실제시각}.zip ^
  --backup backups\visionflow-backup-{실제시각}.zip ^
  --confirm INCLUDE_VERIFIED_BACKUP
```

중괄호가 포함된 예시 문구를 그대로 입력하지 말고 실제 파일명으로 바꿔야 합니다.

## 5. 생성 직후 독립 재검증

생성 명령에 표시된 실제 ZIP 경로를 사용합니다.

```bat
scripts\run-visionflow-transfer-package-verify.bat ^
  --bundle artifacts\transfer-package\visionflow-transfer-package-{실제시각}.zip
```

최신 ZIP을 자동으로 선택하려면 다음 명령을 사용할 수 있습니다.

```bat
powershell -NoProfile -ExecutionPolicy Bypass -Command "$bundle=(Get-ChildItem 'C:\VisionFlow-Drone\artifacts\transfer-package\visionflow-transfer-package-*.zip'|Sort-Object LastWriteTimeUtc -Descending|Select-Object -First 1).FullName; Write-Host ('Bundle: '+$bundle); & 'C:\VisionFlow-Drone\scripts\run-visionflow-transfer-package-verify.bat' --bundle $bundle; exit $LASTEXITCODE"
```

정상 결과:

```text
VisionFlow transfer package: VERIFIED
Status: TRANSFER_PACKAGE_READY_WITH_DEFERRED
```

## 6. 패키지 구성

```text
VisionFlow-Transfer-Package/
  README.md
  TRANSFER_PACKAGE_MANIFEST.json
  handoff/
    visionflow-migration-handoff-....zip
    visionflow-migration-handoff-....sha256
  readiness/
    visionflow-transfer-readiness-....json
    visionflow-transfer-readiness-....html
    visionflow-transfer-readiness-....sha256
  database/
    visionflow-backup-....zip
    visionflow-backup-....sha256
```

마이그레이션 핸드오프 안에는 안전 소스 릴리스, 릴리스 증빙, LG GRAM baseline이 들어 있습니다.
따라서 같은 파일을 패키지 최상위에 중복 저장하지 않습니다.

## 7. 생성 시 검증 항목

- 전송 준비도가 `TRANSFER_READY` 또는 `TRANSFER_READY_WITH_DEFERRED`인지 확인
- 모든 전송 준비도 검사가 `PASS`이고 차단 항목이 0인지 확인
- 기본 24시간 유효기간과 HTML 상태 일치 확인
- 전송 준비도가 참조한 핸드오프 경로와 SHA-256 확인
- 핸드오프의 바깥 sidecar 및 전체 중첩 manifest 재검증
- 핸드오프가 기록한 정확한 MySQL 백업 크기와 SHA-256 확인
- MySQL 백업 ZIP의 내부 manifest, SQL dump, 모든 파일 크기와 SHA-256 확인
- `.env`, 인증서 개인키, 운영자 키 파일, 모델 가중치 혼입 차단
- 결과 ZIP manifest와 바깥 `.sha256` 재검증

최신 파일이 잘못됐을 때 과거 파일로 조용히 후퇴하지 않습니다. 최신 증빙을 수정하거나
정상 파일을 명시적으로 지정해야 합니다.

## 8. 포함하지 않는 항목

- `.env`, `.env.local`, `.env.docker`
- VIEWER·OPERATOR·ADMIN 인증 키
- `rootCA-key.pem` 등 인증서 개인키
- `best.pt`, `*.onnx`, `*.engine` 등 모델 가중치
- 학습 데이터셋과 원본 촬영 영상

MySQL 백업 자체에는 비행·텔레메트리·AI 이벤트·인시던트·스냅샷 등 운영 데이터가 포함될 수
있습니다. 이 때문에 최종 패키지는 반드시 민감 데이터로 취급합니다.

## 9. HP OMEN 이동 순서

1. 패키지 ZIP과 바깥 `.sha256`을 암호화된 외장 매체 또는 접근 통제 저장소로 복사합니다.
2. HP OMEN에서 최종 패키지 검증기를 실행합니다.
3. `handoff` 안의 안전 소스 ZIP을 새 작업 폴더에 압축 해제합니다.
4. `database`의 MySQL 백업을 새 프로젝트의 `backups` 폴더로 복사합니다.
5. `.env.docker.example`을 기준으로 HP OMEN 전용 `.env.docker`를 새로 작성합니다.
6. Docker와 NVIDIA 환경을 준비하고 MySQL 백업을 복원합니다.
7. target machine profile과 LG baseline을 비교합니다.
8. RTX 5060과 `best.pt` 추론·성능 검증을 수행합니다.
9. 스마트폰 HTTPS 실센서 검증은 별도 보류 절차에서 재개합니다.

DJI Mini 4 Pro 전용 RTSP 및 기체 종속 코드는 계속 3차 프로젝트 범위입니다.

## 10. 개발자 검증

```bat
python -m unittest discover -s scripts\tests -p "test_visionflow_transfer_package.py" -v
python -m compileall scripts\visionflow_transfer_package.py
```

이 도구는 외부 전송, DB 복원, Docker 실행, 기존 파일 삭제를 수행하지 않습니다.
