# Patch manifest

## Purpose

기간별 정비 작업 성과와 현재 함대 비행 게이트 상태를 하나의 `/maintenance`
운영 화면에서 확인합니다.

## Files

| Project path | Action |
|---|---|
| `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/controller/MaintenanceMetricsController.java` | Add |
| `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/dto/MaintenanceMetricsResponse.java` | Add |
| `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/service/MaintenanceMetricsService.java` | Add |
| `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/repository/MaintenanceWorkOrderRepository.java` | Update |
| `02_backend/visionflow-api/src/test/java/com/visionflow/api/maintenance/service/MaintenanceMetricsServiceTests.java` | Add |
| `01_frontend/visionflow-web/src/app/api/maintenance/metrics/route.ts` | Add |
| `01_frontend/visionflow-web/src/components/maintenance/maintenance-metrics-panel.tsx` | Add |
| `01_frontend/visionflow-web/src/components/maintenance/maintenance-work-order-board.tsx` | Update |
| `01_frontend/visionflow-web/src/types/maintenance-metrics.ts` | Add |
| `docs/MAINTENANCE_KPI_APPLY.md` | Add |
| `docs/MAINTENANCE_KPI_PATCH_MANIFEST.md` | Add |

## Local validation

- TypeScript/TSX syntax transpilation: 4 files passed
- Metrics runtime response parser: valid response accepted
- Metrics runtime response parser: inconsistent totals rejected
- Backend unit tests supplied for populated and empty windows
- ZIP integrity and generated-file exclusion checked during packaging

The supplied source archive is intentionally partial, so the complete Gradle,
ESLint and Next.js production builds must be run after applying the patch to
`C:\VisionFlow-Drone`.
