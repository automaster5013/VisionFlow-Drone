# Patch manifest

| Project path | Action |
|---|---|
| `scripts/visionflow_maintenance_acceptance.py` | Update |
| `scripts/tests/test_visionflow_maintenance_acceptance.py` | Update |
| `scripts/visionflow_release_gate.py` | Update |
| `scripts/tests/test_visionflow_release_gate.py` | Update |
| `scripts/visionflow_release_evidence.py` | Update |
| `scripts/tests/test_visionflow_release_evidence.py` | Update |
| `docs/MAINTENANCE_KPI_ACCEPTANCE_APPLY.md` | Add |
| `docs/MAINTENANCE_KPI_ACCEPTANCE_PATCH_MANIFEST.md` | Add |

## Safety

- HTTP 검증은 GET만 사용합니다.
- DB 변경과 서비스 재시작을 수행하지 않습니다.
- 운영자 인증 키와 환경 변수 값을 보고서에 기록하지 않습니다.
- 자체 `.sha256` 파일을 추가 생성하지 않습니다.
