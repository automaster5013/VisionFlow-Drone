# VisionFlow Flyway V21 실패 복구

기준 커밋: `27183e961dab47164e5a656801385d302358813f`와 Drone history delete guard 적용 상태

## 원인과 확인된 상태

V21 최초 SQL은 한 `ALTER TABLE` 문 안에서 기존 FK를 삭제하면서 같은 이름으로
즉시 재생성했다. MySQL 8.4에서 첫 문장이 실패해 Flyway에 `success=0` 행이
남았으며, 이후 Backend 재시작은 validation 단계에서 차단됐다.

읽기 전용 확인 결과 세 변경 대상 FK는 모두 기존 `CASCADE`이고, V21 DDL은
어느 테이블에도 반쪽 적용되지 않았다. 교정된 V21은 FK 삭제와 재생성을 별도
`ALTER TABLE` 문으로 실행한다.

## 복구 안전 경계

복구 도구는 다음 조건이 모두 정확히 일치할 때만 실행된다.

- Backend 컨테이너 상태가 `exited`
- Flyway V21 실패 행이 정확히 한 건
- 설치 순번·버전·설명·스크립트·성공 상태가 승인 프로필과 일치
- Drone 물리 FK 네 개가 기존 `CASCADE/CASCADE/CASCADE/NO ACTION` 상태
- 현재 정의된 모든 DB 정합성 규칙의 finding이 0

적용 시 운영 테이블 행과 스키마 DDL은 변경하지 않는다. 실패한
`flyway_schema_history` 메타데이터 한 행만 백업 후 삭제한다.

```bat
scripts\run-visionflow-flyway-v21-recovery.bat plan
scripts\run-visionflow-flyway-v21-recovery.bat repair --apply --confirm REPAIR_VISIONFLOW_FLYWAY_V21
```

복구 뒤 Backend는 계속 중지 상태다. Backend를 재빌드하면 교정된 V21이 처음부터
적용되며, 이후 네 FK의 삭제 규칙과 데이터 정합성을 다시 읽기 전용으로 확인한다.
