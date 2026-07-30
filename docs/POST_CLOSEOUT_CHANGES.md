# VisionFlow 종결 이후 변경분 관리

2차 프로젝트 종결 보고서 생성 후 HP OMEN 이관일까지 계속 수정한 소스를 추적하는
도구입니다. 기존 최종 이관 ZIP은 기준선으로 보존하고, 추가·수정 파일만 새 변경분
ZIP에 포함합니다. 삭제 파일은 manifest에만 기록하며 실제 파일을 삭제하지 않습니다.

## 전제 조건

- `artifacts\transfer-package`에 검증된 종결 기준 이관 ZIP과 `.sha256`이 있어야
  합니다.
- 이관 ZIP 내부의 핸드오프와 안전 소스 ZIP도 모두 무결성 검증을 통과해야 합니다.
- 이전 단계에서 `scripts\visionflow_transfer_package.py`가 적용되어 있어야 합니다.

## 변경분 생성

프로젝트 루트 `C:\VisionFlow-Drone`에서 실행합니다.

```bat
scripts\run-visionflow-post-closeout-changes.bat
```

변경 파일이 있으면 다음 상태가 표시됩니다.

```text
VisionFlow post-closeout changes: CREATED
Status: POST_CLOSEOUT_CHANGES_READY
```

변경 파일이 없으면 다음 상태가 표시됩니다.

```text
Status: POST_CLOSEOUT_NO_CHANGES
```

결과 파일:

```text
artifacts\post-closeout-changes\visionflow-post-closeout-changes-<UTC 시각>.zip
artifacts\post-closeout-changes\visionflow-post-closeout-changes-<UTC 시각>.sha256
```

## 독립 재검증

실제 생성된 ZIP 경로를 입력합니다.

```bat
scripts\run-visionflow-post-closeout-changes-verify.bat --bundle artifacts\post-closeout-changes\visionflow-post-closeout-changes-<UTC 시각>.zip
```

정상 결과:

```text
VisionFlow post-closeout changes: VERIFIED
Status: POST_CLOSEOUT_CHANGES_READY
```

## 포함·제외 정책

포함:

- 종결 기준에 없던 안전 소스 파일
- 종결 기준과 SHA-256 또는 크기가 달라진 안전 소스 파일
- 삭제 파일의 경로와 종결 기준 메타데이터(manifest에만 기록)

제외:

- `.env`와 실행 환경 설정값
- 운영자 키, 인증서 개인키, 고신뢰 비밀정보 패턴
- MySQL DB·백업·SQL dump
- 런타임 로그·캐시·빌드 결과
- 영상·일반 런타임 이미지
- `best.pt`를 포함한 AI 모델 가중치

Flyway migration SQL, Gradle wrapper JAR, 제한 크기 이하의 프론트엔드 공개 이미지는
기존 안전 소스 릴리스 정책에 따라 포함할 수 있습니다.

## 토요일 HP OMEN 이관 시 주의

이 변경분 ZIP은 누락 확인과 임시 보관을 위한 증분 자료입니다. 최종 이관을 대체하지
않습니다. 이관 직전에는 최신 소스 상태로 전체 테스트와 다음 증적 체인을 다시
생성해야 합니다.

1. 안전 소스 릴리스
2. LG GRAM machine baseline
3. 릴리스 준비도·증빙
4. 마이그레이션 핸드오프
5. 전송 준비도
6. 최종 이관 패키지
7. 2차 프로젝트 종결 보고서
