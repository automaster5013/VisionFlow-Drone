# VisionFlow CSP 관찰 증적 수집

## 목적

`/security-status`의 CSP Report-Only 관찰 결과를 발표·인수인계에서 다시 확인할 수
있도록 JSON, CSV, HTML 및 SHA-256 파일로 저장합니다. 이 단계는 강제 CSP를 적용하지
않으며 MySQL과 실행 중인 메모리 상태를 변경하지 않습니다.

## 적용 파일

프로젝트 루트가 `C:\VisionFlow-Drone`일 때 다음 파일이 추가됩니다.

- `scripts\visionflow_csp_evidence.py`
- `scripts\run-visionflow-csp-evidence.bat`
- `scripts\tests\test_visionflow_csp_evidence.py`
- `docs\CSP_OBSERVATION_EVIDENCE.md`

기존 프런트엔드, 백엔드, AI 서버 및 데이터베이스 파일은 변경하지 않습니다.

## 단위 테스트

```bat
cd /d C:\VisionFlow-Drone
python -m unittest scripts.tests.test_visionflow_csp_evidence -v
```

## 증적 생성

프런트엔드가 `http://localhost:3000`에서 실행 중인 상태에서 다음 명령을 실행합니다.

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-csp-evidence.bat
```

생성 위치:

```text
artifacts\csp-observability\visionflow-csp-observation-*.json
artifacts\csp-observability\visionflow-csp-observation-*.csv
artifacts\csp-observability\visionflow-csp-observation-*.html
artifacts\csp-observability\visionflow-csp-observation-*.sha256
```

## 판정 결과

- `CSP_OBSERVATION_CLEAN`: 전체 수신 건수가 0건
- `CSP_OBSERVATION_REVIEW_REQUIRED`: 한 건 이상의 위반 후보가 관찰됨
- `BLOCKED`: API 연결 실패, 무제한 저장 방식, 건수 불일치 또는 정제되지 않은 URL 발견

자동 수락 테스트가 전송한 가상 보고서가 남아 있으면
`CSP_OBSERVATION_REVIEW_REQUIRED`가 정상입니다. 이 상태는 애플리케이션 실패가 아니며
프로그램 종료 코드는 0입니다.

CI에서 위반 후보도 실패로 처리해야 할 때만 다음 옵션을 사용합니다.

```bat
scripts\run-visionflow-csp-evidence.bat --fail-on-violation
```

## 개인정보·보안 검증

수집기는 서버가 제공한 허용 필드만 다시 구성합니다. URL 필드에 `?` 또는 `#`가
남아 있으면 증적 생성을 차단하고, CSV 셀의 첫 문자가 수식 실행 문자이면 작은따옴표를
붙입니다. 운영자 키, 쿠키, 세션 토큰 및 원본 요청 헤더는 수집하지 않습니다.

## 계속 보류하는 범위

- 최종 HTTPS·AI 주소 확정 전 강제 CSP와 HSTS
- 스마트폰 실센서 HTTPS 검증
- HP OMEN RTX 5060 및 파인튜닝 `best.pt` 검증
- DJI Mini 4 Pro 전용 연동
