# VisionFlow 운영 데이터 백업·복구 가이드

## 1. 목적과 보류 작업 구분

이 패치는 스마트폰, DJI 기체, CUDA GPU, `yolo26m.pt` 또는 `best.pt`가 없어도 적용하고
검증할 수 있습니다. 다음 항목은 기존 결정대로 별도 보류합니다.

- 스마트폰 HTTPS 인증서 및 실센서 검증
- HP OMEN RTX 5060의 GPU 사전 검증과 성능 A/B 비교
- `best.pt` 정확도, 클래스 매핑 및 실시간 이벤트 적용
- DJI Mini 4 Pro 기체 종속 연동

이번 단계에서는 MySQL에 누적된 비행·텔레메트리·AI 이벤트·인시던트 데이터와 파일로
저장된 AI 스냅샷·분석 영상을 하나의 검증 가능한 ZIP으로 보존합니다.

## 2. 반영 파일

저장소 루트가 `C:\VisionFlow-Drone`일 때 다음 새 파일을 복사합니다.

| 파일 | 전체 경로 |
|---|---|
| 백업·검증·복구 본체 | `C:\VisionFlow-Drone\scripts\visionflow_backup.py` |
| 백업 명령 | `C:\VisionFlow-Drone\scripts\run-visionflow-backup.bat` |
| 무결성 검증 명령 | `C:\VisionFlow-Drone\scripts\run-visionflow-backup-verify.bat` |
| 복구 명령 | `C:\VisionFlow-Drone\scripts\run-visionflow-restore.bat` |
| 단위 테스트 | `C:\VisionFlow-Drone\scripts\tests\test_visionflow_backup.py` |

루트 `.gitignore`에는 다음 한 줄을 추가합니다.

```gitignore
backups/
```

Compose 서비스 이름과 볼륨 경로는 현재 구조를 그대로 사용하므로 `compose.yaml` 변경은
없습니다.

## 3. 백업 범위

포함:

- MySQL `visionflow` 데이터베이스 논리 덤프
- `artifacts\backend-data`의 AI 탐지 스냅샷 및 백엔드 영속 파일
- `artifacts\ai-output`의 주석 영상 등 AI 출력 파일
- Git 커밋, MySQL 이미지, 생성 시각, 서비스 정지 여부
- 모든 파일의 크기와 SHA-256

제외:

- `.env.docker` 및 비밀번호
- 소스 코드와 Docker 이미지
- `.pt`, `.onnx`, `.engine` 모델
- 학습·검증 데이터셋
- MySQL Docker 볼륨의 물리 파일

백업 ZIP에는 실제 DB 레코드와 스냅샷이 들어가므로 외부 공개 저장소에 올리지 마세요.

## 4. 일반 백업

Docker Desktop과 MySQL 서비스가 실행된 상태에서 저장소 루트에서 실행합니다.

```bat
scripts\run-visionflow-backup.bat
```

MySQL은 `--single-transaction` 논리 덤프로 저장합니다. 백엔드와 AI 서비스는 중단하지
않으므로 일상적인 백업에 적합합니다. 결과는 다음 위치에 생성됩니다.

```text
C:\VisionFlow-Drone\backups\visionflow-backup-YYYYMMDDTHHMMSSZ.zip
```

## 5. 발표 직전 일관성 백업

스냅샷이나 주석 영상이 기록되는 도중 파일을 복사하지 않도록 애플리케이션 서비스의 쓰기를
잠시 중단합니다.

```bat
scripts\run-visionflow-backup.bat --consistent
```

동작 순서:

1. 현재 실행 중인 `backend-api`, `ai-server`, `frontend-web`만 확인
2. 확인된 서비스만 잠시 중지
3. MySQL 논리 덤프와 영속 파일 복사
4. manifest와 SHA-256 생성 후 ZIP 압축
5. ZIP을 다시 읽어 무결성 자동 검증
6. 처음에 실행 중이었던 서비스만 재시작

처음부터 꺼져 있던 서비스를 임의로 시작하지 않습니다.

## 6. 백업 무결성 재검증

파일을 다른 노트북이나 외장 저장장치로 옮긴 후 실행합니다.

```bat
scripts\run-visionflow-backup-verify.bat --backup backups\visionflow-backup-20260722T120000Z.zip
```

정상 결과:

```text
[PASS] VisionFlow backup integrity verified
```

검증 항목:

- ZIP 손상 여부
- 경로 탈출 및 중복 파일 차단
- manifest에 없는 추가 파일 차단
- 누락 파일과 파일 크기 확인
- 모든 파일의 SHA-256 재계산
- MySQL 논리 덤프 존재 확인

## 7. 복구

복구는 현재 MySQL 데이터베이스와 영속 파일을 백업 시점 상태로 교체합니다. 백업 검증과
DB 이름 검증을 통과하고 명시적인 확인 문자열이 있어야 실행됩니다.

```bat
scripts\run-visionflow-restore.bat --backup backups\visionflow-backup-20260722T120000Z.zip --confirm RESTORE
```

보호 절차:

1. 입력 ZIP의 전체 SHA-256 검증
2. 현재 실행 중인 애플리케이션 서비스 일시 중지
3. 현재 상태를 `backups\pre-restore`에 자동 안전 백업
4. 복원 전 파일을 `backups\displaced\{시각}`으로 이동
5. MySQL DB 재생성 후 논리 덤프 import
6. 백업 스냅샷과 AI 출력 복원
7. 처음에 실행 중이었던 서비스만 재시작

`--confirm RESTORE`가 없거나 철자가 다르면 DB 작업 전에 즉시 중단됩니다.
복구 도중 오류가 발생하면 추가 쓰기를 막기 위해 애플리케이션 서비스는 중지 상태로
유지됩니다. 오류 원인을 확인하고 `backups\pre-restore` 안전 백업으로 복구하세요.

## 8. 복구 후 검증

```bat
scripts\run-visionflow-acceptance.bat
scripts\run-visionflow-acceptance.bat -RunDemo
```

그리고 다음을 확인합니다.

- `/dashboard`와 `/drones` HTTP 200
- 기존 비행 세션과 과거 경로 조회
- AI 탐지 이벤트의 스냅샷 표시
- 인시던트 보고서 조회
- DBeaver에서 주요 테이블 레코드 확인

복구 검증이 끝나기 전에는 `backups\pre-restore`와 `backups\displaced`를 삭제하지 마세요.

## 9. 도구 자체 테스트

Docker 없이 manifest와 ZIP 무결성 로직을 검증할 수 있습니다.

```bat
python -m unittest discover -s scripts\tests -p "test_*.py" -v
python -m compileall scripts\visionflow_backup.py
```

실제 MySQL dump와 restore 통합 검증은 Docker 스택을 실행한 상태에서 별도의 테스트 데이터를
사용해 수행합니다. 중요한 기존 데이터를 대상으로 첫 복구 연습을 하지 마세요.
