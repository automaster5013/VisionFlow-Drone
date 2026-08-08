# VisionFlow 운영 설정 센터

기준 커밋: `2bfeac151a17de24d60e4692756cdff5db2e7de1`

`/settings`는 왼쪽 사이드바의 **설정** 메뉴를 브라우저별 관제 기본값 화면으로
연결합니다. 서버의 운영 설정이나 보안 정책을 변경하지 않고, 반복적으로 사용하는
읽기 전용 관제 화면의 시작 상태만 현재 브라우저에 저장합니다.

## 설정 범위

- 통합 이벤트 관제의 15초 자동 갱신 기본값
- 통합 이벤트 관제의 초기 시간 범위: 1시간·6시간·24시간·7일·전체 기간
- 운영 통계 센터의 30초 자동 갱신 기본값
- 운영 통계 센터의 초기 표본 기간: 7일·30일·90일
- AI 모델 운영 센터의 30초 자동 갱신 기본값

설정은 각 화면에 새로 진입할 때 초기값으로 적용됩니다. 해당 화면에서 자동 갱신이나
범위를 임시 변경해도 저장된 기본값을 덮어쓰지 않습니다.

## 저장과 검증

저장 키는 `visionflow.operator-console-settings.v1`이며 현재 브라우저의
`localStorage`만 사용합니다. 저장 구조에는 schema version, 저장 시각과 허용된 다섯
설정값만 포함됩니다.

- 읽을 때 모든 필드의 타입과 허용 범위를 검사합니다.
- 손상되거나 구버전인 값은 사용하지 않고 제품 기본값으로 복구합니다.
- 기본값 복원은 저장 키를 제거합니다.
- Server Component 환경에서는 저장소에 접근하지 않고 제품 기본값을 반환합니다.

## 보안과 데이터 경계

- 설정 화면은 `fetch` 요청을 만들지 않습니다.
- Backend·AI API, DB migration, 테이블과 보안 규칙을 변경하지 않습니다.
- API key, 비밀번호, 비밀값, 모델 경로와 운영 데이터는 저장하지 않습니다.
- 브라우저 프로필을 바꾸거나 저장소를 삭제하면 해당 브라우저 설정은 초기화됩니다.
- 운영자 인증 상태는 현재 사용자를 안내하는 용도로만 읽고 권한을 변경하지 않습니다.

## 적용 화면

`/events`, `/statistics`, `/models`는 마운트 시 검증된 설정을 한 번 읽어 각각의
초기 자동 갱신과 조회 범위를 정합니다. 기존의 수동 갱신, 부분 소스 장애 격리,
마지막 정상 데이터 유지와 읽기 전용 경계는 그대로 유지합니다.

## 추적성 회귀 방어

`operator-console-settings-ui-policy`는 다음을 검사합니다.

- `/settings` 페이지와 설정 센터 마운트
- 허용 목록 기반 저장 파서와 저장·복원 동작
- 이벤트·통계·AI 모델 화면의 설정 적용
- 네트워크 요청·서버 변경·민감값 저장 부재
- pull request와 `main` push의 workflow 경로 추적

## 검증

```bat
npm --prefix 01_frontend\visionflow-web run lint
npm --prefix 01_frontend\visionflow-web run build
py -3 -m unittest scripts.tests.test_visionflow_system_traceability_operator_console_settings -v
scripts\run-visionflow-api-audit-ci.bat
```

정상 기준은 Frontend operation 72개와
`operator-console-settings-ui-policy: PASS`입니다.
