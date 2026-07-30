# VisionFlow 콜드 스타트 복원 리허설

## 목적

HP OMEN으로 이동하기 전에, LG GRAM에서 만든 마이그레이션 핸드오프가 빈 작업공간에 안전하게
복원 가능한지 확인합니다. 이 단계는 실제 서버나 데이터베이스를 건드리지 않는 정적·격리
리허설입니다.

## 적용 경로

ZIP 안의 파일을 `C:\VisionFlow-Drone`에 같은 상대 경로로 복사합니다.

```text
C:\VisionFlow-Drone\scripts\visionflow_cold_start_rehearsal.py
C:\VisionFlow-Drone\scripts\run-visionflow-cold-start-rehearsal.bat
C:\VisionFlow-Drone\scripts\tests\test_visionflow_cold_start_rehearsal.py
C:\VisionFlow-Drone\docs\COLD_START_REHEARSAL.md
```

## 실행

먼저 마이그레이션 핸드오프가 생성돼 있어야 합니다.

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-cold-start-rehearsal.bat
```

최신 핸드오프 대신 특정 파일을 검사하려면 실제 타임스탬프를 지정합니다.

```bat
scripts\run-visionflow-cold-start-rehearsal.bat ^
  --handoff artifacts\migration-handoff\visionflow-migration-handoff-{TIMESTAMP}.zip
```

정상 결과:

```text
VisionFlow cold-start rehearsal: COLD_START_READY_WITH_DEFERRED
JSON report: C:\VisionFlow-Drone\artifacts\cold-start-rehearsal\visionflow-cold-start-rehearsal-....json
HTML report: C:\VisionFlow-Drone\artifacts\cold-start-rehearsal\visionflow-cold-start-rehearsal-....html
SHA-256: C:\VisionFlow-Drone\artifacts\cold-start-rehearsal\visionflow-cold-start-rehearsal-....sha256
```

## 검증 범위

- 핸드오프 ZIP 바깥 `.sha256`
- `HANDOFF_MANIFEST.json`의 전체 포함 파일 크기와 SHA-256
- 안전 소스 ZIP의 `SOURCE_MANIFEST.json`
- source manifest에 기록된 모든 파일의 크기와 SHA-256
- ZIP 경로 탈출, 중복 경로, 심볼릭 링크 차단
- 런타임 `.env`, 모델 가중치, 촬영·분석 이미지/영상, DB 백업 혼입 차단
- 2MB 이하의 프론트엔드 `public` 정적 이미지는 UI 소스 자산으로 허용
- 핸드오프가 기록한 source manifest SHA-256과 실제 소스 비교
- 격리 추출 전후 원본 핸드오프 ZIP SHA-256 동일성

## 재구축 필수 파일

다음 항목 중 하나라도 없으면 보고서는 생성되지만 상태가 `BLOCKED`가 되고 실행 종료 코드는
`1`입니다.

- 루트 Compose 파일
- `01_frontend\visionflow-web\package.json`
- `01_frontend\visionflow-web\package-lock.json`
- 백엔드 `build.gradle` 또는 `build.gradle.kts`
- 백엔드 `gradlew.bat`
- Gradle Wrapper properties와 JAR
- AI 서버 `requirements.txt` 또는 `pyproject.toml`
- 자동 인수 테스트 실행기
- 안전 소스 릴리스 실행기
- machine profile 실행기
- 마이그레이션 핸드오프 실행기

## 격리 작업공간

기본 실행은 `artifacts\cold-start-rehearsal` 아래에 임시 작업공간을 만든 뒤 보고서 생성 전 자동
정리합니다. 파일을 직접 살펴봐야 할 때만 다음 옵션을 사용합니다.

```bat
scripts\run-visionflow-cold-start-rehearsal.bat --keep-workspace
```

이 경우 보고서의 `workspace.path`에 보존 경로가 기록됩니다. 보존된 작업공간은 안전 소스의 복사본일
뿐이며 기존 프로젝트를 덮어쓰지 않습니다.

## 의도적으로 수행하지 않는 작업

- Docker 이미지 빌드 및 서비스 시작
- npm, Gradle, pip 네트워크 의존성 다운로드
- MySQL 백업 복원 또는 DB 변경
- `best.pt` 배치와 GPU 추론
- 스마트폰 HTTPS 실센서 검증
- DJI Mini 4 Pro 전용 연동

실제 실행·복원은 HP OMEN으로 이동한 뒤 target machine profile 단계에서 진행합니다.

## 개발자 테스트

```bat
python -m unittest discover -s scripts\tests -p "test_visionflow_cold_start_rehearsal.py" -v
```
