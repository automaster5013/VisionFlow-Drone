# VisionFlow HP OMEN 이관 전 전체 증적 갱신

토요일 HP OMEN으로 이동하기 직전, LG GRAM의 최신 소스와 운영 증적을 하나의 고정
순서로 다시 생성하는 오케스트레이터입니다. 기본 명령은 계획만 출력하며 아무것도
변경하지 않습니다. 실제 실행에는 명시적 확인 문자열이 필요합니다.

## 적용 파일

```text
C:\VisionFlow-Drone\scripts\visionflow_pre_transfer_refresh.py
C:\VisionFlow-Drone\scripts\run-visionflow-pre-transfer-refresh.bat
C:\VisionFlow-Drone\scripts\run-visionflow-pre-transfer-refresh-verify.bat
C:\VisionFlow-Drone\scripts\tests\test_visionflow_pre_transfer_refresh.py
C:\VisionFlow-Drone\docs\PRE_TRANSFER_REFRESH.md
```

## 실행 전 준비

1. Docker의 MySQL, backend, frontend, AI 서버를 모두 실행합니다.
2. `.env.docker`가 존재하는지 확인합니다.
3. 현재 터미널에 실제 인수 테스트용 역할 키를 설정합니다.
4. 드론 `1`에 ACTIVE 비행 세션이 남아 있으면 완료하거나 중단합니다.
5. 통합 증적 카탈로그와 체크섬 정리 패치가 적용되어 있어야 합니다.

역할 키의 실제 값을 로그나 문서에 복사하지 마세요.

```bat
set VISIONFLOW_ACCEPTANCE_VIEWER_KEY=<실제 VIEWER 키>
set VISIONFLOW_ACCEPTANCE_OPERATOR_KEY=<실제 OPERATOR 키>
set VISIONFLOW_ACCEPTANCE_ADMIN_KEY=<실제 ADMIN 키>
```

## 1. 계획만 확인

이 명령은 서비스, DB, Docker, 기존 파일, 증적을 변경하지 않습니다.

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-pre-transfer-refresh.bat plan
```

## 2. 전체 갱신 실행

```bat
scripts\run-visionflow-pre-transfer-refresh.bat execute --confirm REFRESH_TRANSFER_CHAIN_WITH_BACKUP
```

기본 드론이 아닌 경우:

```bat
scripts\run-visionflow-pre-transfer-refresh.bat execute --drone-id 2 --confirm REFRESH_TRANSFER_CHAIN_WITH_BACKUP
```

정상 최종 결과:

```text
VisionFlow pre-transfer refresh: PRE_TRANSFER_REFRESH_READY
```

## AI 벤치마크 선택

기본 실행은 30일 이내 최신 AI CPU 기준선을 재사용합니다. 토요일에도 LG GRAM CPU
수치를 다시 측정하려면 영상 프레임 입력이 실제로 들어오는 상태에서 다음 옵션을
추가합니다.

```bat
scripts\run-visionflow-pre-transfer-refresh.bat execute --refresh-ai-benchmark --confirm REFRESH_TRANSFER_CHAIN_WITH_BACKUP
```

프레임 입력이 없으면 벤치마크 샘플이 생성되지 않아 전체 갱신이 중단됩니다.

## 실행 순서

1. 기존 증적·SHA-256 무결성 사전 검사
2. 운영 스크립트 전체 단위 테스트
3. Demo·RBAC·브라우저 세션 통합 인수 테스트
4. CSP Report-Only 관찰 증적
5. MySQL·영속 증적 일관 백업
6. 저장공간·DB 참조 감사
7. 격리·복원 리허설
8. AI CPU 기준선 신규 측정 또는 최신 정상본 재사용
9. 릴리스 준비도
10. 릴리스 증빙 번들
11. 안전 소스 릴리스
12. LG GRAM machine baseline
13. HP OMEN 마이그레이션 핸드오프
14. 격리 콜드 스타트 리허설
15. 최종 전송 준비도
16. 실제 MySQL 백업 포함 최종 이관 ZIP
17. 임시 오프라인 매체와 새 HP 작업공간 전체 리허설
18. 2차 프로젝트 종결 보고서
19. 최종 패키지 이후 소스 변경 0개 확인

한 단계라도 실패하거나 새 산출물이 정확히 하나 생성되지 않으면 이후 단계를 실행하지
않습니다. 실패 보고서는 보존되며 재실행 시 과거 정상 산출물로 조용히 후퇴하지 않습니다.

첫 단계는 다음 읽기 전용 명령과 같습니다.

```bat
scripts\run-visionflow-evidence-catalog.bat --check-only
```

`HEALTHY`와 `CLEANUP_RECOMMENDED`는 계속 진행합니다.
`REVIEW_REQUIRED`는 증적 누락·변경을 의미하므로 운영 테스트와 백업을
시작하기 전에 전체 갱신을 중단합니다.

## 안전과 영향

- 통합 Demo 테스트는 검증용 비행·AI 이벤트·인시던트 데이터를 MySQL에 추가합니다.
- 일관 백업은 실행 중인 backend와 AI 서비스를 잠시 멈췄다가 원래 상태로 재개할 수
  있습니다.
- 격리·복원 리허설은 보존기간 후보가 있으면 임시 격리한 후 반드시 원위치 복원을
  시도합니다.
- 오프라인 이관 리허설은 시스템 임시 폴더에 매체 복사본과 새 HP 작업공간을
  만들고 패키지·소스·백업 연결을 재검증한 뒤 성공·실패와 관계없이 제거합니다.
  DB 복원, Docker·GPU 실행, 외장 SSD 쓰기는 수행하지 않습니다.
- 영구 삭제, DB 복원, 외부 전송은 수행하지 않습니다.
- 최종 이관 ZIP은 실제 MySQL 백업을 포함하므로 민감 파일로 취급합니다.

## 결과 보고서

```text
artifacts\pre-transfer-refresh\refresh-<UTC 시각>\
  visionflow-pre-transfer-refresh.json
  visionflow-pre-transfer-refresh.html
  visionflow-pre-transfer-refresh.sha256
  <단계별 로그>
```

## 독립 재검증

실제 생성된 JSON 경로를 사용합니다.

```bat
scripts\run-visionflow-pre-transfer-refresh-verify.bat --report artifacts\pre-transfer-refresh\refresh-<UTC 시각>\visionflow-pre-transfer-refresh.json
```

정상 결과:

```text
VisionFlow pre-transfer refresh: VERIFIED
Status: PRE_TRANSFER_REFRESH_READY
```

검증기는 보고서 sidecar뿐 아니라 최종 이관 ZIP, 종결 보고서, 소스 무변경 ZIP을
각각 다시 검증하고, 오프라인 이관 리허설이 이번 최종 이관 ZIP을 사용했는지도
확인합니다.
