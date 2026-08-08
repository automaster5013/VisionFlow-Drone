# VisionFlow 공통 셸 내비게이션 접근성

기준 커밋: `37e318f004d0e75b2658e50e0cf5c1c9dce2d32d`

## 목적

공통 셸에서 현재 화면을 즉시 식별하고, 데스크톱 사이드바가 숨겨지는 작은 화면에서도 모든 허용 메뉴에 접근할 수 있도록 합니다.

## 동작

- 데스크톱 사이드바와 모바일 메뉴는 동일한 메뉴 정의를 사용합니다.
- 현재 경로 및 하위 상세 경로는 `aria-current="page"`와 시각적 강조로 표시합니다.
- `/`는 대시보드 항목으로 취급합니다.
- 세션 관리는 기존과 동일하게 `ADMIN` 또는 RBAC 비활성 모드에서만 노출됩니다.
- 모바일 메뉴는 헤더의 `메뉴` 버튼으로 열며 대화상자 의미 구조, 배경 닫기, 닫기 버튼, `Escape`, 포커스 복귀를 지원합니다.
- 메뉴 이동 시 패널을 닫고 새 경로로 이동합니다.
- 시연 모드는 데스크톱과 모바일에서 동일한 보조 강조를 유지합니다.

## 보안 및 데이터 경계

- API, Backend, AI, 데이터베이스, 세션 발급 및 권한 판정은 변경하지 않습니다.
- 메뉴 노출은 기존 `OperatorSecurityStatus`만 읽습니다.
- 브라우저 저장소, 쿠키, 키, 모델 경로 또는 사용자 데이터를 새로 저장하지 않습니다.

## 검증

```bat
npm --prefix 01_frontend\visionflow-web run lint
npm --prefix 01_frontend\visionflow-web run build
py -3 -m unittest scripts.tests.test_visionflow_system_traceability_shell_navigation -v
scripts\run-visionflow-api-audit-ci.bat
```

런타임에서는 데스크톱과 브라우저 개발자 도구의 작은 화면 폭에서 현재 메뉴 강조, 모바일 메뉴 열기·닫기, `Escape`, ADMIN 전용 세션 관리 노출을 확인합니다.
