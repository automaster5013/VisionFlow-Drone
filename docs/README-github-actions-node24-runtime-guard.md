# VisionFlow GitHub Actions Node.js 24 런타임 가드

## 목적

API·보안·시스템 추적성 감사 workflow에서 Node.js 20 지원 종료 경고를
제거하고, 동일한 구버전 Action이 다시 유입되지 않도록 CI 정책으로 고정한다.

## 적용 범위

- `actions/checkout@v6`
- `actions/setup-python@v6`
- `actions/upload-artifact@v7`
- 시스템 추적성 정책 단위 테스트의 push·pull request 실행

Backend·Frontend 애플리케이션, AI 서버, 데이터베이스, API operation 수와
보안 권한은 변경하지 않는다.

## 정책

- 감사 workflow의 세 JavaScript Action은 Node.js 24 기반 major만 허용한다.
- `ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION` 우회는 금지한다.
- `scripts/tests/test_visionflow_system_traceability_*.py` 변경도 workflow를
  실행해야 한다.
- 정적 감사 전에 전체 시스템 추적성 정책 테스트를 실행한다.
- 감사 보고서는 성공·실패와 관계없이 14일 동안 artifact로 보관한다.

## 로컬 검증

저장소 루트에서 실행한다.

```bat
py -3 -m py_compile scripts\visionflow_system_traceability_audit.py scripts\tests\test_visionflow_system_traceability_github_actions_runtime.py
py -3 -m unittest discover -s scripts\tests -p "test_visionflow_system_traceability_*.py" -v
scripts\run-visionflow-system-traceability-audit.bat
scripts\run-visionflow-api-audit-ci.bat
```

정상 결과에는 다음 검사가 포함된다.

```text
[PASS] github-actions-node24-runtime-policy
```

push 후 GitHub Actions의 `Annotations`에 Node.js 20 deprecation 경고가
없고 모든 감사 단계가 녹색인지 확인한다.
