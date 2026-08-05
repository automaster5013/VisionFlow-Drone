from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from visionflow_ai_openapi_snapshot import build_openapi, collect_routes
from visionflow_api_contract_audit import (
    atomic_write_text,
    configure_console,
    current_git_commit,
    parse_backend_operations,
    parse_frontend_operations,
    parse_openapi_operations,
)


CREATE_TABLE_PATTERN = re.compile(
    r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([A-Za-z0-9_]+)`?",
    re.IGNORECASE,
)
ALTER_TABLE_PATTERN = re.compile(
    r"\bALTER\s+TABLE\s+`?([A-Za-z0-9_]+)`?",
    re.IGNORECASE,
)
FOREIGN_KEY_PATTERN = re.compile(
    r"(?:CONSTRAINT\s+`?[A-Za-z0-9_]+`?\s+)?"
    r"FOREIGN\s+KEY\s*\(\s*`?([A-Za-z0-9_]+)`?\s*\)\s*"
    r"REFERENCES\s+`?([A-Za-z0-9_]+)`?\s*"
    r"\(\s*`?([A-Za-z0-9_]+)`?\s*\)",
    re.IGNORECASE | re.DOTALL,
)
CLASS_PATTERN = re.compile(r"(?:public\s+)?class\s+([A-Za-z0-9_]+)")
REPOSITORY_PATTERN = re.compile(
    r"(?:public\s+)?interface\s+([A-Za-z0-9_]+)\s+extends\s+"
    r"JpaRepository\s*<\s*([A-Za-z0-9_]+)\s*,"
)


def drone_mutation_concurrency_policy_drift(root: Path) -> list[str]:
    backend_root = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
    )
    paths = {
        "repository": backend_root
        / "java/com/visionflow/api/drone/repository/DroneRepository.java",
        "service": backend_root
        / "java/com/visionflow/api/drone/service/DroneService.java",
        "migration": backend_root
        / "resources/db/migration/V2__create_drone_table.sql",
    }
    sources: dict[str, str] = {}
    drift: list[str] = []
    for key, path in paths.items():
        if not path.is_file():
            drift.append(f"missing:{key}:{path.relative_to(root)}")
            continue
        sources[key] = path.read_text(encoding="utf-8")

    required_tokens = {
        "repository": [
            "LockModeType.PESSIMISTIC_WRITE",
            "findByIdForUpdate(",
        ],
        "service": [
            "findDroneForUpdate(id)",
            "findDroneById(id)",
            "drone.updateBasicInformation(",
            "drone.updateStatus(",
            "sessionCorrelationGuard.requireOptionalOwnedSession(",
            "drone.updateTelemetry(",
            "droneRepository.countDeletionDependencies(id)",
        ],
        "migration": [
            "UNIQUE (drone_code)",
            "UNIQUE (serial_number)",
        ],
    }
    for key, tokens in required_tokens.items():
        source = sources.get(key)
        if source is None:
            continue
        for token in tokens:
            if token not in source:
                drift.append(f"missing-token:{key}:{token}")

    repository = sources.get("repository")
    if repository is not None:
        method_at = repository.find("findByIdForUpdate(")
        annotation_at = repository.rfind(
            "@Lock(LockModeType.PESSIMISTIC_WRITE)",
            0,
            method_at,
        )
        if not (0 <= annotation_at < method_at):
            drift.append("usage:repository:lock-drone-id")

    service = sources.get("service")
    if service is not None:
        if service.count("findDroneForUpdate(id)") < 4:
            drift.append(
                "usage:service:lock-basic-status-delete-telemetry"
            )

        transitions = (
            (
                "updateDrone",
                "public DroneResponse updateDrone(",
                "public DroneResponse updateStatus(",
                "drone.updateBasicInformation(",
            ),
            (
                "updateStatus",
                "public DroneResponse updateStatus(",
                "public void deleteDrone(",
                "drone.updateStatus(",
            ),
            (
                "deleteDrone",
                "public void deleteDrone(",
                "private Drone findDroneById(",
                "droneRepository.countDeletionDependencies(id)",
            ),
        )
        for method, start_token, end_token, mutation_token in transitions:
            method_at = service.find(start_token)
            next_at = service.find(end_token, method_at + 1)
            method_source = (
                service[method_at:next_at]
                if 0 <= method_at < next_at
                else ""
            )
            lock_at = method_source.find("findDroneForUpdate(id)")
            mutation_at = method_source.find(mutation_token)
            if not (0 <= lock_at < mutation_at):
                drift.append(
                    f"ordering:service:{method}-lock-before-mutation"
                )

        telemetry_at = service.find("public DroneResponse updateTelemetry(")
        telemetry_source = (
            service[telemetry_at:] if telemetry_at >= 0 else ""
        )
        telemetry_lock_at = telemetry_source.find(
            "findDroneForUpdate(id)"
        )
        correlation_at = telemetry_source.find(
            "sessionCorrelationGuard.requireOptionalOwnedSession("
        )
        telemetry_mutation_at = telemetry_source.find(
            "drone.updateTelemetry("
        )
        persistence_at = telemetry_source.find(
            "droneRepository.flush()"
        )
        if not (
            0 <= telemetry_lock_at
            < correlation_at
            < telemetry_mutation_at
            < persistence_at
        ):
            drift.append(
                "ordering:service:updateTelemetry-lock-before-correlation-and-write"
            )

        get_at = service.find("public DroneResponse getDrone(")
        update_at = service.find("public DroneResponse updateDrone(")
        get_source = (
            service[get_at:update_at]
            if 0 <= get_at < update_at
            else ""
        )
        if (
            "findDroneById(id)" not in get_source
            or "findDroneForUpdate(id)" in get_source
        ):
            drift.append("usage:service:read-remains-non-locking")
    return drift


def ai_alert_creation_concurrency_policy_drift(
    root: Path,
) -> list[str]:
    backend_root = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
    )
    paths = {
        "event-repository": backend_root
        / "java/com/visionflow/api/ai/repository"
        / "AiInferenceEventRepository.java",
        "alert-repository": backend_root
        / "java/com/visionflow/api/ai/repository"
        / "AiAlertRepository.java",
        "alert-service": backend_root
        / "java/com/visionflow/api/ai/service"
        / "AiAlertService.java",
        "migration": backend_root
        / "resources/db/migration"
        / "V10__create_ai_alert.sql",
    }
    sources: dict[str, str] = {}
    drift: list[str] = []
    for key, path in paths.items():
        if not path.is_file():
            drift.append(f"missing:{key}:{path.relative_to(root)}")
            continue
        sources[key] = path.read_text(encoding="utf-8")

    required_tokens = {
        "event-repository": [
            "LockModeType.PESSIMISTIC_WRITE",
            "findByIdForUpdate(",
        ],
        "alert-repository": [
            "findByEventId(",
        ],
        "alert-service": [
            "findEventForUpdate(event.getId())",
            "alertRepository.findByEventId(lockedEvent.getId())",
            "riskEvaluator.evaluate(detections)",
            "AiAlert.create(",
            "alertRepository.saveAndFlush(alert)",
            "incidentService.createFromAiAlert(alert)",
            "AiAlertRealtimeAction.CREATED",
            "eventRepository.findByIdForUpdate(eventId)",
            "eventRepository.findById(eventId)",
        ],
        "migration": [
            "UNIQUE KEY uk_ai_alert_event (event_id)",
        ],
    }
    for key, tokens in required_tokens.items():
        source = sources.get(key)
        if source is None:
            continue
        for token in tokens:
            if token not in source:
                drift.append(f"missing-token:{key}:{token}")

    event_repository = sources.get("event-repository")
    if event_repository is not None:
        method_at = event_repository.find("findByIdForUpdate(")
        annotation_at = event_repository.rfind(
            "@Lock(LockModeType.PESSIMISTIC_WRITE)",
            0,
            method_at,
        )
        if not (0 <= annotation_at < method_at):
            drift.append("usage:event-repository:lock-event-id")

    alert_service = sources.get("alert-service")
    if alert_service is not None:
        create_at = alert_service.find("public void createForEvent(")
        read_at = alert_service.find(
            "public List<AiAlertResponse> findAlerts(",
            create_at + 1,
        )
        create_source = (
            alert_service[create_at:read_at]
            if 0 <= create_at < read_at
            else ""
        )
        lock_at = create_source.find(
            "findEventForUpdate(event.getId())"
        )
        idempotency_at = create_source.find(
            "alertRepository.findByEventId(lockedEvent.getId())"
        )
        evaluate_at = create_source.find(
            "riskEvaluator.evaluate(detections)"
        )
        save_at = create_source.find(
            "alertRepository.saveAndFlush(alert)"
        )
        incident_at = create_source.find(
            "incidentService.createFromAiAlert(alert)"
        )
        realtime_at = create_source.find(
            "realtimePublisher.publishAfterCommit("
        )
        if not (
            0 <= lock_at
            < idempotency_at
            < evaluate_at
            < save_at
            < incident_at
            < realtime_at
        ):
            drift.append(
                "ordering:alert-service:"
                "event-lock-before-idempotency-and-side-effects"
            )

        helper_at = alert_service.find(
            "private AiAlert findAlert(",
            read_at + 1,
        )
        read_source = (
            alert_service[read_at:helper_at]
            if 0 <= read_at < helper_at
            else ""
        )
        if "findEventForUpdate(" in read_source:
            drift.append(
                "usage:alert-service:alert-reads-remain-non-locking"
            )

        locked_helper_at = alert_service.find(
            "private AiInferenceEvent findEventForUpdate("
        )
        locked_helper_source = (
            alert_service[locked_helper_at:]
            if locked_helper_at >= 0
            else ""
        )
        if "eventRepository.findByIdForUpdate(eventId)" not in (
            locked_helper_source
        ):
            drift.append(
                "usage:alert-service:locked-helper-uses-event-lock"
            )
    return drift


def ai_snapshot_concurrency_policy_drift(root: Path) -> list[str]:
    backend_root = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
        / "java"
        / "com"
        / "visionflow"
        / "api"
        / "ai"
    )
    paths = {
        "repository": backend_root
        / "repository/AiInferenceEventRepository.java",
        "service": backend_root
        / "service/AiInferenceEventService.java",
    }
    sources: dict[str, str] = {}
    drift: list[str] = []
    for key, path in paths.items():
        if not path.is_file():
            drift.append(f"missing:{key}:{path.relative_to(root)}")
            continue
        sources[key] = path.read_text(encoding="utf-8")

    required_tokens = {
        "repository": [
            "LockModeType.PESSIMISTIC_WRITE",
            "findByIdForUpdate(",
        ],
        "service": [
            "findEventForUpdate(eventId)",
            "snapshotStorageService.store(eventId, file)",
            "event.attachSnapshot(",
            "eventRepository.saveAndFlush(event)",
            "findEvent(eventId)",
        ],
    }
    for key, tokens in required_tokens.items():
        source = sources.get(key)
        if source is None:
            continue
        for token in tokens:
            if token not in source:
                drift.append(f"missing-token:{key}:{token}")

    repository = sources.get("repository")
    if repository is not None:
        method_at = repository.find("findByIdForUpdate(")
        annotation_at = repository.rfind(
            "@Lock(LockModeType.PESSIMISTIC_WRITE)",
            0,
            method_at,
        )
        if not (0 <= annotation_at < method_at):
            drift.append("usage:repository:lock-ai-event-id")

    service = sources.get("service")
    if service is not None:
        attach_at = service.find(
            "public AiInferenceEventResponse attachSnapshot("
        )
        read_at = service.find(
            "public AiSnapshotDownload findSnapshot(",
            attach_at + 1,
        )
        attach_source = (
            service[attach_at:read_at]
            if 0 <= attach_at < read_at
            else ""
        )
        lock_at = attach_source.find("findEventForUpdate(eventId)")
        store_at = attach_source.find(
            "snapshotStorageService.store(eventId, file)"
        )
        mutation_at = attach_source.find("event.attachSnapshot(")
        persistence_at = attach_source.find(
            "eventRepository.saveAndFlush(event)"
        )
        if not (
            0 <= lock_at < store_at < mutation_at < persistence_at
        ):
            drift.append(
                "ordering:service:attachSnapshot-lock-before-storage-and-write"
            )

        helper_at = service.find(
            "private AiInferenceEvent findEvent(",
            read_at + 1,
        )
        read_source = (
            service[read_at:helper_at]
            if 0 <= read_at < helper_at
            else ""
        )
        if (
            "findEvent(eventId)" not in read_source
            or "findEventForUpdate(eventId)" in read_source
        ):
            drift.append("usage:service:snapshot-read-remains-non-locking")

        locked_helper_at = service.find(
            "private AiInferenceEvent findEventForUpdate("
        )
        locked_helper_source = (
            service[locked_helper_at:]
            if locked_helper_at >= 0
            else ""
        )
        if "eventRepository.findByIdForUpdate(eventId)" not in (
            locked_helper_source
        ):
            drift.append("usage:service:locked-helper-uses-repository-lock")
    return drift


def audit_retention_concurrency_policy_drift(root: Path) -> list[str]:
    backend_root = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
        / "java"
        / "com"
        / "visionflow"
        / "api"
        / "audit"
    )
    paths = {
        "repository": backend_root
        / "repository/AuditLogRepository.java",
        "service": backend_root
        / "service/AuditRetentionService.java",
        "scheduler": backend_root
        / "scheduler/AuditRetentionScheduler.java",
        "controller": backend_root
        / "controller/AuditLogController.java",
    }
    sources: dict[str, str] = {}
    drift: list[str] = []
    for key, path in paths.items():
        if not path.is_file():
            drift.append(f"missing:{key}:{path.relative_to(root)}")
            continue
        sources[key] = path.read_text(encoding="utf-8")

    required_tokens = {
        "repository": [
            "LockModeType.PESSIMISTIC_WRITE",
            "findRetentionCandidatesForUpdate(",
            "SELECT auditLog",
            "ORDER BY auditLog.occurredAt ASC, auditLog.id ASC",
        ],
        "service": [
            "findRetentionCandidatesForUpdate(",
            ".map(AuditLog::getId)",
            "deleteAllByIdInBatch(ids)",
            "countByOccurredAtBefore(",
        ],
        "scheduler": ['retentionService.cleanup("SCHEDULED")'],
        "controller": ['retentionService.cleanup("MANUAL")'],
    }
    for key, tokens in required_tokens.items():
        source = sources.get(key)
        if source is None:
            continue
        for token in tokens:
            if token not in source:
                drift.append(f"missing-token:{key}:{token}")

    repository = sources.get("repository")
    if repository is not None:
        method_at = repository.find(
            "findRetentionCandidatesForUpdate("
        )
        annotation_at = repository.rfind(
            "@Lock(LockModeType.PESSIMISTIC_WRITE)",
            0,
            method_at,
        )
        if not (0 <= annotation_at < method_at):
            drift.append("usage:repository:lock-retention-candidates")

    service = sources.get("service")
    if service is not None:
        cleanup_at = service.find(
            "public AuditRetentionExecutionResponse cleanup("
        )
        helper_at = service.find(
            "private void requireEnabled()",
            cleanup_at + 1,
        )
        cleanup_source = (
            service[cleanup_at:helper_at]
            if 0 <= cleanup_at < helper_at
            else ""
        )
        lock_at = cleanup_source.find(
            "findRetentionCandidatesForUpdate("
        )
        id_at = cleanup_source.find(".map(AuditLog::getId)")
        delete_at = cleanup_source.find("deleteAllByIdInBatch(ids)")
        flush_at = cleanup_source.find("auditLogRepository.flush()")
        remaining_at = cleanup_source.find(
            "countByOccurredAtBefore("
        )
        if not (
            0 <= lock_at < id_at < delete_at < flush_at < remaining_at
        ):
            drift.append(
                "ordering:service:lock-before-retention-delete-and-count"
            )

        inspect_at = service.find(
            "public AuditRetentionStatusResponse inspect()"
        )
        inspect_source = (
            service[inspect_at:cleanup_at]
            if 0 <= inspect_at < cleanup_at
            else ""
        )
        if (
            "countByOccurredAtBefore(" not in inspect_source
            or "findRetentionCandidatesForUpdate(" in inspect_source
        ):
            drift.append(
                "usage:service:retention-inspection-remains-non-locking"
            )
    return drift


def session_correlation_policy_drift(root: Path) -> list[str]:
    backend_root = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
        / "java"
        / "com"
        / "visionflow"
        / "api"
    )
    paths = {
        "guard": backend_root
        / "flight"
        / "service"
        / "FlightSessionCorrelationGuard.java",
        "exception": backend_root
        / "flight"
        / "exception"
        / "FlightSessionDroneMismatchException.java",
        "telemetry": backend_root
        / "drone"
        / "service"
        / "DroneService.java",
        "ai-event": backend_root
        / "ai"
        / "service"
        / "AiInferenceEventService.java",
    }
    sources: dict[str, str] = {}
    drift: list[str] = []
    for key, path in paths.items():
        if not path.is_file():
            drift.append(f"missing:{key}:{path.relative_to(root)}")
            continue
        sources[key] = path.read_text(encoding="utf-8")

    required_tokens = {
        "guard": [
            "findById(normalizedSessionId)",
            "Objects.equals(session.getDroneId(), droneId)",
            "requireOptionalOwnedSession(",
        ],
        "exception": ["FLIGHT_SESSION_DRONE_MISMATCH"],
        "telemetry": [
            "sessionCorrelationGuard.requireOptionalOwnedSession(",
            "drone.updateTelemetry(",
        ],
        "ai-event": [
            "eventRepository",
            ".findBySourceIdAndSessionIdAndFrameIndex(",
        ],
    }
    for key, tokens in required_tokens.items():
        source = sources.get(key)
        if source is None:
            continue
        for token in tokens:
            if token not in source:
                drift.append(f"missing-token:{key}:{token}")

    telemetry = sources.get("telemetry")
    if telemetry is not None:
        guard_index = telemetry.find(
            "sessionCorrelationGuard.requireOptionalOwnedSession("
        )
        persistence_index = telemetry.find("drone.updateTelemetry(")
        if (
            guard_index < 0
            or persistence_index < 0
            or guard_index > persistence_index
        ):
            drift.append(
                "ordering:telemetry:guard-before-persistence"
            )

    ai_event = sources.get("ai-event")
    if ai_event is not None:
        guard_indexes = [
            index
            for token in (
                "sessionCorrelationGuard.requireOwnedSessionForUpdate(",
                "sessionCorrelationGuard.requireOwnedSession(",
            )
            if (index := ai_event.find(token)) >= 0
        ]
        if not guard_indexes:
            drift.append(
                "missing-token:ai-event:"
                "sessionCorrelationGuard.requireOwnedSession("
            )
        guard_index = min(guard_indexes, default=-1)
        persistence_index = ai_event.find(
            ".findBySourceIdAndSessionIdAndFrameIndex("
        )
        if (
            guard_index < 0
            or persistence_index < 0
            or guard_index > persistence_index
        ):
            drift.append(
                "ordering:ai-event:guard-before-persistence"
            )
    return drift


def ai_inference_ingest_concurrency_policy_drift(
    root: Path,
) -> list[str]:
    backend_root = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
    )
    paths = {
        "session-repository": backend_root
        / "java/com/visionflow/api/flight/repository"
        / "FlightSessionRepository.java",
        "correlation-guard": backend_root
        / "java/com/visionflow/api/flight/service"
        / "FlightSessionCorrelationGuard.java",
        "event-repository": backend_root
        / "java/com/visionflow/api/ai/repository"
        / "AiInferenceEventRepository.java",
        "event-service": backend_root
        / "java/com/visionflow/api/ai/service"
        / "AiInferenceEventService.java",
        "migration": backend_root
        / "resources/db/migration"
        / "V5__create_ai_inference_event_tables.sql",
    }
    sources: dict[str, str] = {}
    drift: list[str] = []
    for key, path in paths.items():
        if not path.is_file():
            drift.append(f"missing:{key}:{path.relative_to(root)}")
            continue
        sources[key] = path.read_text(encoding="utf-8")

    required_tokens = {
        "session-repository": [
            "LockModeType.PESSIMISTIC_WRITE",
            "findBySessionIdAndDroneIdForUpdate(",
        ],
        "correlation-guard": [
            "requireOwnedSessionForUpdate(",
            "findBySessionIdAndDroneIdForUpdate(",
            "requireOwnedSession(",
        ],
        "event-repository": [
            "findBySourceIdAndSessionIdAndFrameIndex(",
        ],
        "event-service": [
            "sessionCorrelationGuard.requireOwnedSessionForUpdate(",
            ".findBySourceIdAndSessionIdAndFrameIndex(",
            ".orElseGet(() -> createNew(request, sessionId))",
            "eventRepository.saveAndFlush(event)",
        ],
        "migration": [
            "UNIQUE KEY uk_ai_event_frame",
            "source_id",
            "session_id",
            "frame_index",
        ],
    }
    for key, tokens in required_tokens.items():
        source = sources.get(key)
        if source is None:
            continue
        for token in tokens:
            if token not in source:
                drift.append(f"missing-token:{key}:{token}")

    session_repository = sources.get("session-repository")
    if session_repository is not None:
        method_at = session_repository.find(
            "findBySessionIdAndDroneIdForUpdate("
        )
        annotation_at = session_repository.rfind(
            "@Lock(LockModeType.PESSIMISTIC_WRITE)",
            0,
            method_at,
        )
        if not (0 <= annotation_at < method_at):
            drift.append("usage:session-repository:lock-owned-session")

    correlation_guard = sources.get("correlation-guard")
    if correlation_guard is not None:
        locked_at = correlation_guard.find(
            "public String requireOwnedSessionForUpdate("
        )
        optional_at = correlation_guard.find(
            "public String requireOptionalOwnedSession(",
            locked_at + 1,
        )
        locked_source = (
            correlation_guard[locked_at:optional_at]
            if 0 <= locked_at < optional_at
            else ""
        )
        repository_lock_at = locked_source.find(
            "findBySessionIdAndDroneIdForUpdate("
        )
        fallback_at = locked_source.find("requireOwnedSession(")
        if not (0 <= repository_lock_at < fallback_at):
            drift.append(
                "ordering:correlation-guard:session-lock-before-fallback"
            )

    event_service = sources.get("event-service")
    if event_service is not None:
        create_at = event_service.find(
            "public AiInferenceEventResponse create("
        )
        read_at = event_service.find(
            "public List<AiInferenceEventResponse> findRecent(",
            create_at + 1,
        )
        create_source = (
            event_service[create_at:read_at]
            if 0 <= create_at < read_at
            else ""
        )
        session_lock_at = create_source.find(
            "sessionCorrelationGuard.requireOwnedSessionForUpdate("
        )
        idempotency_at = create_source.find(
            ".findBySourceIdAndSessionIdAndFrameIndex("
        )
        create_new_at = create_source.find(
            ".orElseGet(() -> createNew(request, sessionId))"
        )
        if not (
            0 <= session_lock_at < idempotency_at < create_new_at
        ):
            drift.append(
                "ordering:event-service:session-lock-before-idempotency-and-insert"
            )

        read_source = (
            event_service[read_at:]
            if read_at >= 0
            else ""
        )
        if "requireOwnedSessionForUpdate(" in read_source:
            drift.append(
                "usage:event-service:event-reads-remain-non-locking"
            )
    return drift


def flight_session_lifecycle_policy_drift(root: Path) -> list[str]:
    backend_root = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
    )
    paths = {
        "management": backend_root
        / "java"
        / "com"
        / "visionflow"
        / "api"
        / "flight"
        / "service"
        / "FlightSessionManagementService.java",
        "session-repository": backend_root
        / "java"
        / "com"
        / "visionflow"
        / "api"
        / "flight"
        / "repository"
        / "FlightSessionRepository.java",
        "drone-repository": backend_root
        / "java"
        / "com"
        / "visionflow"
        / "api"
        / "drone"
        / "repository"
        / "DroneRepository.java",
        "exception": backend_root
        / "java"
        / "com"
        / "visionflow"
        / "api"
        / "flight"
        / "exception"
        / "ActiveFlightSessionExistsException.java",
        "migration": backend_root
        / "resources"
        / "db"
        / "migration"
        / "V22__enforce_single_active_flight_session.sql",
        "integrity-audit": root
        / "scripts"
        / "visionflow_data_integrity_audit.py",
        "integrity-policy": root
        / "scripts"
        / "visionflow_data_integrity_policy.json",
    }
    sources: dict[str, str] = {}
    drift: list[str] = []
    for key, path in paths.items():
        if not path.is_file():
            drift.append(f"missing:{key}:{path.relative_to(root)}")
            continue
        sources[key] = path.read_text(encoding="utf-8")

    required_tokens = {
        "management": [
            "droneRepository.findByIdForUpdate(droneId)",
            "new ActiveFlightSessionExistsException(droneId)",
            "sessionRepository.saveAndFlush(session)",
            "uq_flight_session_one_active_per_drone",
            "isActiveSessionUniquenessViolation(exception)",
            "findManagedSessionForUpdate(",
        ],
        "session-repository": [
            "LockModeType.PESSIMISTIC_WRITE",
            "findBySessionIdAndDroneIdForUpdate(",
        ],
        "drone-repository": [
            "LockModeType.PESSIMISTIC_WRITE",
            "findByIdForUpdate(",
        ],
        "exception": ["ACTIVE_FLIGHT_SESSION_EXISTS"],
        "migration": [
            "GENERATED ALWAYS AS",
            "status = 'ACTIVE'",
            "UNIQUE (active_drone_id)",
        ],
        "integrity-audit": [
            '"flight-session-multiple-active-per-drone"',
            "HAVING COUNT(*) > 1",
        ],
        "integrity-policy": [
            '"key": "flight-session-multiple-active-per-drone"',
            '"severity": "CRITICAL"',
        ],
    }
    for key, tokens in required_tokens.items():
        source = sources.get(key)
        if source is None:
            continue
        for token in tokens:
            if token not in source:
                drift.append(f"missing-token:{key}:{token}")

    management = sources.get("management")
    if management is not None:
        lock_at = management.find(
            "droneRepository.findByIdForUpdate(droneId)"
        )
        active_check_at = management.find(
            ".findFirstByDroneIdAndStatusOrderByStartedAtDesc("
        )
        persistence_at = management.find(
            "sessionRepository.saveAndFlush(session)"
        )
        if not (
            0 <= lock_at < active_check_at < persistence_at
        ):
            drift.append(
                "ordering:management:drone-lock-before-active-check-before-insert"
            )
        if management.count("findManagedSessionForUpdate(") < 4:
            drift.append(
                "usage:management:lock-update-complete-abort"
            )
    return drift


def incident_lifecycle_concurrency_policy_drift(root: Path) -> list[str]:
    backend_root = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
        / "java"
        / "com"
        / "visionflow"
        / "api"
    )
    paths = {
        "repository": backend_root
        / "incident/repository/IncidentRepository.java",
        "operator": backend_root
        / "incident/service/IncidentService.java",
        "incident-sla": backend_root
        / "incident/service/IncidentSlaEscalationService.java",
        "quality-automation": backend_root
        / "flight/quality/service/FlightQualityIncidentAutomationService.java",
        "gate-automation": backend_root
        / "maintenance/service/FlightGateIncidentAutomationService.java",
        "maintenance-sla": backend_root
        / "maintenance/service/MaintenanceSlaIncidentEscalationService.java",
        "demo": backend_root / "demo/service/DemoScenarioService.java",
    }
    sources: dict[str, str] = {}
    drift: list[str] = []
    for key, path in paths.items():
        if not path.is_file():
            drift.append(f"missing:{key}:{path.relative_to(root)}")
            continue
        sources[key] = path.read_text(encoding="utf-8")

    required_tokens = {
        "repository": [
            "LockModeType.PESSIMISTIC_WRITE",
            "findByIdForUpdate(",
            "findBySourceTypeAndSourceIdForUpdate(",
            "findOverdueForEscalationForUpdate(",
        ],
        "operator": [
            "findIncidentForUpdate(incidentId)",
            "findBySourceTypeAndSourceIdForUpdate(",
        ],
        "incident-sla": [
            "findOverdueForEscalationForUpdate(",
            "findByIdForUpdate(incidentId)",
        ],
        "quality-automation": [
            "droneRepository.findByIdForUpdate(",
            "findBySourceTypeAndSourceIdForUpdate(",
        ],
        "gate-automation": [
            "droneRepository.findByIdForUpdate(",
            "findBySourceTypeAndSourceIdForUpdate(",
        ],
        "maintenance-sla": [
            "findByIdForUpdate(incidentId.get())",
            "existsByIncidentIdAndActionTypeAndActor(",
        ],
        "demo": [
            "lockIncidentForDemoEscalation(incidentId)",
            "SELECT id FROM incident WHERE id = ? FOR UPDATE",
            "UPDATE incident",
        ],
    }
    for key, tokens in required_tokens.items():
        source = sources.get(key)
        if source is None:
            continue
        for token in tokens:
            if token not in source:
                drift.append(f"missing-token:{key}:{token}")

    repository = sources.get("repository")
    if repository is not None and repository.count(
        "@Lock(LockModeType.PESSIMISTIC_WRITE)"
    ) < 3:
        drift.append("usage:repository:lock-id-source-overdue")

    operator = sources.get("operator")
    if operator is not None:
        if operator.count("findIncidentForUpdate(incidentId)") < 4:
            drift.append("usage:operator:lock-assign-priority-status-note")
        if operator.count(
            "findBySourceTypeAndSourceIdForUpdate("
        ) < 3:
            drift.append("usage:operator:lock-source-create-and-sync")

    gate = sources.get("gate-automation")
    if gate is not None and gate.count(
        "findBySourceTypeAndSourceIdForUpdate("
    ) < 2:
        drift.append("usage:gate-automation:lock-open-and-resolve")

    maintenance_sla = sources.get("maintenance-sla")
    if maintenance_sla is not None:
        lock_at = maintenance_sla.find(
            "findByIdForUpdate(incidentId.get())"
        )
        dedup_at = maintenance_sla.find(
            "existsByIncidentIdAndActionTypeAndActor("
        )
        if not (0 <= lock_at < dedup_at):
            drift.append(
                "ordering:maintenance-sla:incident-lock-before-history-dedup"
            )
    demo = sources.get("demo")
    if demo is not None:
        lock_at = demo.find(
            "lockIncidentForDemoEscalation(incidentId)"
        )
        update_at = demo.find("jdbcTemplate.update(")
        if not (0 <= lock_at < update_at):
            drift.append("ordering:demo:incident-lock-before-update")
    return drift


def maintenance_work_order_lifecycle_concurrency_policy_drift(
    root: Path,
) -> list[str]:
    backend_root = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
    )
    paths = {
        "work-order-repository": backend_root
        / "java/com/visionflow/api/maintenance/repository"
        / "MaintenanceWorkOrderRepository.java",
        "incident-repository": backend_root
        / "java/com/visionflow/api/incident/repository"
        / "IncidentRepository.java",
        "work-order-service": backend_root
        / "java/com/visionflow/api/maintenance/service"
        / "MaintenanceWorkOrderService.java",
        "sla-service": backend_root
        / "java/com/visionflow/api/maintenance/service"
        / "MaintenanceSlaIncidentEscalationService.java",
        "migration": backend_root
        / "resources/db/migration"
        / "V19__create_maintenance_work_order.sql",
    }
    sources: dict[str, str] = {}
    drift: list[str] = []
    for key, path in paths.items():
        if not path.is_file():
            drift.append(f"missing:{key}:{path.relative_to(root)}")
            continue
        sources[key] = path.read_text(encoding="utf-8")

    required_tokens = {
        "work-order-repository": [
            "LockModeType.PESSIMISTIC_WRITE",
            "findByIdForUpdate(",
            "findByIncidentIdForUpdate(",
            "SELECT workOrder.id",
            "findActiveIdsForSlaEvaluation(",
            "SELECT workOrder.incidentId",
            "findIncidentIdById(",
        ],
        "incident-repository": [
            "LockModeType.PESSIMISTIC_WRITE",
            "findByIdForUpdate(",
        ],
        "work-order-service": [
            "findByIncidentIdForUpdate(",
            "requireWorkOrderForUpdate(workOrderId)",
            "order.startInspection(",
            "order.complete(",
            "workOrderRepository.findById(workOrderId)",
        ],
        "sla-service": [
            "findActiveIdsForSlaEvaluation(",
            "findIncidentIdById(workOrderId)",
            "findByIdForUpdate(incidentId.get())",
            "findByIdForUpdate(workOrderId)",
            "!isActive(order.getStatus())",
            "MaintenanceSlaPolicy.evaluate(order, evaluatedAt)",
            "existsByIncidentIdAndActionTypeAndActor(",
        ],
        "migration": [
            "UNIQUE KEY uk_maintenance_work_order_incident (incident_id)",
        ],
    }
    for key, tokens in required_tokens.items():
        source = sources.get(key)
        if source is None:
            continue
        for token in tokens:
            if token not in source:
                drift.append(f"missing-token:{key}:{token}")

    repository = sources.get("work-order-repository")
    if repository is not None:
        if repository.count(
            "@Lock(LockModeType.PESSIMISTIC_WRITE)"
        ) < 2:
            drift.append(
                "usage:work-order-repository:lock-id-and-incident"
            )
        candidate_at = repository.find(
            "findActiveIdsForSlaEvaluation("
        )
        previous_method_at = repository.find(
            "findLatestForAllDrones();"
        )
        candidate_source = (
            repository[previous_method_at:candidate_at]
            if 0 <= previous_method_at < candidate_at
            else ""
        )
        if "@Lock(LockModeType.PESSIMISTIC_WRITE)" in (
            candidate_source
        ):
            drift.append(
                "usage:work-order-repository:"
                "candidate-id-scan-remains-non-locking"
            )

    work_order_service = sources.get("work-order-service")
    if work_order_service is not None:
        synchronize_at = work_order_service.find(
            "public MaintenanceWorkOrderResponse synchronizeRequired("
        )
        find_many_at = work_order_service.find(
            "public List<MaintenanceWorkOrderResponse> findWorkOrders("
        )
        synchronize_source = (
            work_order_service[synchronize_at:find_many_at]
            if 0 <= synchronize_at < find_many_at
            else ""
        )
        sync_lock_at = synchronize_source.find(
            "findByIncidentIdForUpdate("
        )
        sync_create_at = synchronize_source.find(
            "MaintenanceWorkOrder.open("
        )
        if not (0 <= sync_lock_at < sync_create_at):
            drift.append(
                "ordering:work-order-service:"
                "incident-work-order-lock-before-create-or-sync"
            )

        transitions = (
            (
                "startInspection",
                "public MaintenanceWorkOrderResponse startInspection(",
                "public MaintenanceWorkOrderResponse completeInspection(",
                "order.startInspection(",
            ),
            (
                "completeInspection",
                "public MaintenanceWorkOrderResponse completeInspection(",
                "private MaintenanceWorkOrder requireWorkOrder(",
                "order.complete(",
            ),
        )
        for method, start_token, end_token, mutation_token in transitions:
            method_at = work_order_service.find(start_token)
            next_at = work_order_service.find(end_token, method_at + 1)
            method_source = (
                work_order_service[method_at:next_at]
                if 0 <= method_at < next_at
                else ""
            )
            lock_at = method_source.find(
                "requireWorkOrderForUpdate(workOrderId)"
            )
            mutation_at = method_source.find(mutation_token)
            if not (0 <= lock_at < mutation_at):
                drift.append(
                    f"ordering:work-order-service:"
                    f"{method}-lock-before-mutation"
                )

        read_at = work_order_service.find(
            "public List<MaintenanceWorkOrderResponse> findWorkOrders("
        )
        start_at = work_order_service.find(
            "public MaintenanceWorkOrderResponse startInspection("
        )
        read_source = (
            work_order_service[read_at:start_at]
            if 0 <= read_at < start_at
            else ""
        )
        if "requireWorkOrderForUpdate(" in read_source:
            drift.append(
                "usage:work-order-service:reads-remain-non-locking"
            )

    sla_service = sources.get("sla-service")
    if sla_service is not None:
        candidate_at = sla_service.find(
            "findActiveIdsForSlaEvaluation("
        )
        incident_id_at = sla_service.find(
            "findIncidentIdById(workOrderId)"
        )
        incident_lock_at = sla_service.find(
            "findByIdForUpdate(incidentId.get())"
        )
        work_order_lock_at = sla_service.find(
            "findByIdForUpdate(workOrderId)"
        )
        active_check_at = sla_service.find(
            "!isActive(order.getStatus())"
        )
        evaluation_at = sla_service.find(
            "MaintenanceSlaPolicy.evaluate(order, evaluatedAt)"
        )
        dedup_at = sla_service.find(
            "existsByIncidentIdAndActionTypeAndActor("
        )
        if not (
            0 <= candidate_at
            < incident_id_at
            < incident_lock_at
            < work_order_lock_at
            < active_check_at
            < evaluation_at
            < dedup_at
        ):
            drift.append(
                "ordering:sla-service:"
                "incident-before-work-order-lock-before-reevaluation"
            )
    return drift


def maintenance_mission_control_ui_policy_drift(
    root: Path,
) -> list[str]:
    frontend_root = root / "01_frontend" / "visionflow-web" / "src"
    paths = {
        "mission-control": frontend_root
        / "components/maintenance/maintenance-mission-control.tsx",
        "work-order-board": frontend_root
        / "components/maintenance/maintenance-work-order-board.tsx",
        "tracking-types": frontend_root
        / "types/maintenance-sla-incident-tracking.ts",
        "clearance-types": frontend_root
        / "types/maintenance-flight-clearance.ts",
        "tracking-route": frontend_root
        / "app/api/maintenance/sla/incidents/route.ts",
        "clearance-route": frontend_root
        / "app/api/maintenance/flight-clearance/route.ts",
        "proxy": frontend_root
        / "lib/server/maintenance-work-order-proxy.ts",
    }
    sources: dict[str, str] = {}
    drift: list[str] = []
    for key, path in paths.items():
        if not path.is_file():
            drift.append(f"missing:{key}:{path.relative_to(root)}")
            continue
        sources[key] = path.read_text(encoding="utf-8")

    required_tokens = {
        "mission-control": [
            '"use client";',
            "data-maintenance-mission-control",
            'fetch("/api/maintenance/sla/incidents"',
            'fetch("/api/maintenance/flight-clearance"',
            "parseMaintenanceSlaIncidentTracking(trackingBody)",
            "parseMaintenanceFleetFlightClearance(clearanceBody)",
            "const AUTO_REFRESH_MS = 30_000",
            "window.setInterval(",
            'aria-live="polite"',
            "작전 단계 현황",
            "비행 준비 상태",
            "긴급 작업 큐",
            "summarizeMission(tracking, fleetClearance)",
            "clearance.flightAllowed && !clearance.attentionRequired",
            "fleetClearance.blockedDrones > 0",
            "compareUrgency",
            "/maintenance?droneId=",
        ],
        "work-order-board": [
            'import { MaintenanceMissionControl } from '
            '"@/components/maintenance/maintenance-mission-control";',
            "<MaintenanceMissionControl refreshKey={metricsRevision} />",
        ],
        "tracking-types": [
            "export function parseMaintenanceSlaIncidentTracking(",
            "MaintenanceSlaIncidentTrackingItem",
            "flightClearanceStatus",
            "closureStatus",
        ],
        "clearance-types": [
            "export interface MaintenanceFleetFlightClearance",
            "export function parseMaintenanceFleetFlightClearance(",
            "totalDrones",
            "clearances",
        ],
        "tracking-route": [
            "proxyMaintenanceRequest(",
            "/api/maintenance/sla/incidents?windowDays=",
            'method: "GET"',
        ],
        "clearance-route": [
            "proxyMaintenanceRequest(",
            '"/api/maintenance/flight-clearance"',
            'method: "GET"',
        ],
        "proxy": [
            'import "server-only";',
            "withBackendOperatorAuth(",
            'cache: "no-store"',
        ],
    }
    for key, tokens in required_tokens.items():
        source = sources.get(key)
        if source is None:
            continue
        for token in tokens:
            if token not in source:
                drift.append(f"missing-token:{key}:{token}")

    mission_control = sources.get("mission-control")
    if mission_control is not None:
        tracking_fetch_at = mission_control.find(
            'fetch("/api/maintenance/sla/incidents"'
        )
        clearance_fetch_at = mission_control.find(
            'fetch("/api/maintenance/flight-clearance"'
        )
        tracking_parse_at = mission_control.find(
            "parseMaintenanceSlaIncidentTracking(trackingBody)"
        )
        clearance_parse_at = mission_control.find(
            "parseMaintenanceFleetFlightClearance(clearanceBody)"
        )
        summarize_at = mission_control.find(
            "summarizeMission(tracking, fleetClearance)"
        )
        render_at = mission_control.find(
            'data-maintenance-mission-control'
        )
        if not (
            0
            <= tracking_fetch_at
            < clearance_fetch_at
            < tracking_parse_at
            < clearance_parse_at
            < summarize_at
            < render_at
        ):
            drift.append(
                "ordering:mission-control:"
                "tracking-and-fleet-fetch-before-parse-before-summary"
                "-before-render"
            )

    board = sources.get("work-order-board")
    if board is not None:
        header_at = board.find("</header>")
        mission_at = board.find(
            "<MaintenanceMissionControl refreshKey={metricsRevision} />"
        )
        metrics_at = board.find(
            "<MaintenanceMetricsPanel refreshKey={metricsRevision} />"
        )
        if not (0 <= header_at < mission_at < metrics_at):
            drift.append(
                "ordering:work-order-board:"
                "mission-control-before-detail-panels"
            )
    return drift


def ai_alert_lifecycle_concurrency_policy_drift(root: Path) -> list[str]:
    backend_root = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
        / "java"
        / "com"
        / "visionflow"
        / "api"
        / "ai"
    )
    paths = {
        "repository": backend_root
        / "repository/AiAlertRepository.java",
        "service": backend_root / "service/AiAlertService.java",
    }
    sources: dict[str, str] = {}
    drift: list[str] = []
    for key, path in paths.items():
        if not path.is_file():
            drift.append(f"missing:{key}:{path.relative_to(root)}")
            continue
        sources[key] = path.read_text(encoding="utf-8")

    required_tokens = {
        "repository": [
            "LockModeType.PESSIMISTIC_WRITE",
            "findByIdForUpdate(",
        ],
        "service": [
            "findAlertForUpdate(alertId)",
            "alert.acknowledge(",
            "alert.resolve(",
            "alertRepository.findById(alertId)",
        ],
    }
    for key, tokens in required_tokens.items():
        source = sources.get(key)
        if source is None:
            continue
        for token in tokens:
            if token not in source:
                drift.append(f"missing-token:{key}:{token}")

    repository = sources.get("repository")
    if repository is not None and repository.count(
        "@Lock(LockModeType.PESSIMISTIC_WRITE)"
    ) < 1:
        drift.append("usage:repository:lock-alert-id")

    service = sources.get("service")
    if service is not None:
        if service.count("findAlertForUpdate(alertId)") < 2:
            drift.append("usage:service:lock-acknowledge-resolve")
        acknowledge_at = service.find("findAlertForUpdate(alertId)")
        acknowledge_mutation_at = service.find("alert.acknowledge(")
        resolve_at = service.find(
            "findAlertForUpdate(alertId)",
            acknowledge_at + 1,
        )
        resolve_mutation_at = service.find("alert.resolve(")
        if not (
            0 <= acknowledge_at < acknowledge_mutation_at
            and 0 <= resolve_at < resolve_mutation_at
        ):
            drift.append(
                "ordering:service:alert-lock-before-lifecycle-mutation"
            )
    return drift


def geofence_event_lifecycle_concurrency_policy_drift(
    root: Path,
) -> list[str]:
    backend_root = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
    )
    paths = {
        "repository": backend_root
        / "java/com/visionflow/api/geofence/repository"
        / "DroneGeofenceRepository.java",
        "service": backend_root
        / "java/com/visionflow/api/geofence/service/GeofenceService.java",
        "migration": backend_root
        / "resources/db/migration"
        / "V23__enforce_single_active_geofence_event.sql",
        "integrity-audit": root
        / "scripts/visionflow_data_integrity_audit.py",
        "integrity-policy": root
        / "scripts/visionflow_data_integrity_policy.json",
    }
    sources: dict[str, str] = {}
    drift: list[str] = []
    for key, path in paths.items():
        if not path.is_file():
            drift.append(f"missing:{key}:{path.relative_to(root)}")
            continue
        sources[key] = path.read_text(encoding="utf-8")

    required_tokens = {
        "repository": [
            "LockModeType.PESSIMISTIC_WRITE",
            "findByIdForUpdate(",
        ],
        "service": [
            "findGeofenceForUpdate(id)",
            "candidate.getId()",
            "if (!geofence.isActive())",
            ".findFirstByDroneIdAndGeofenceIdAndResolvedAtIsNullOrderByDetectedAtDesc(",
        ],
        "migration": [
            "active_drone_id BIGINT",
            "active_geofence_id BIGINT",
            "resolved_at IS NULL",
            "uq_geofence_event_one_active_per_drone_zone",
            "UNIQUE (active_drone_id, active_geofence_id)",
        ],
        "integrity-audit": [
            '"geofence-event-multiple-active-per-drone-zone"',
            "GROUP BY event.drone_id, event.geofence_id",
            "HAVING COUNT(*) > 1",
        ],
        "integrity-policy": [
            '"key": "geofence-event-multiple-active-per-drone-zone"',
            '"severity": "CRITICAL"',
        ],
    }
    for key, tokens in required_tokens.items():
        source = sources.get(key)
        if source is None:
            continue
        for token in tokens:
            if token not in source:
                drift.append(f"missing-token:{key}:{token}")

    repository = sources.get("repository")
    if repository is not None and repository.count(
        "@Lock(LockModeType.PESSIMISTIC_WRITE)"
    ) < 1:
        drift.append("usage:repository:lock-geofence-id")

    service = sources.get("service")
    if service is not None:
        if service.count("findGeofenceForUpdate(id)") < 2:
            drift.append("usage:service:lock-update-and-active-change")
        evaluate_start = service.find("public void evaluate(")
        evaluate_source = (
            service[evaluate_start:] if evaluate_start >= 0 else ""
        )
        lock_at = evaluate_source.find("candidate.getId()")
        active_check_at = evaluate_source.find(
            "if (!geofence.isActive())"
        )
        event_lookup_at = evaluate_source.find(
            ".findFirstByDroneIdAndGeofenceIdAndResolvedAtIsNullOrderByDetectedAtDesc("
        )
        if not (0 <= lock_at < active_check_at < event_lookup_at):
            drift.append(
                "ordering:service:geofence-lock-before-active-event-lookup"
            )
    return drift


def demo_scenario_lifecycle_concurrency_policy_drift(
    root: Path,
) -> list[str]:
    backend_root = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
        / "java/com/visionflow/api/demo"
    )
    paths = {
        "repository": backend_root
        / "repository/DemoScenarioRepository.java",
        "service": backend_root
        / "service/DemoScenarioService.java",
    }
    sources: dict[str, str] = {}
    drift: list[str] = []
    for key, path in paths.items():
        if not path.is_file():
            drift.append(f"missing:{key}:{path.relative_to(root)}")
            continue
        sources[key] = path.read_text(encoding="utf-8")

    required_tokens = {
        "repository": [
            "LockModeType.PESSIMISTIC_WRITE",
            "findByIdForUpdate(",
        ],
        "service": [
            "findScenarioForUpdate(scenarioId)",
            "inferenceEventService.create(",
            "lockIncidentForDemoEscalation(incidentId)",
            "alertService.resolve(",
            "flightSessionService.complete(",
            "scenarioRepository.findById(normalized)",
        ],
    }
    for key, tokens in required_tokens.items():
        source = sources.get(key)
        if source is None:
            continue
        for token in tokens:
            if token not in source:
                drift.append(f"missing-token:{key}:{token}")

    repository = sources.get("repository")
    if repository is not None and repository.count(
        "@Lock(LockModeType.PESSIMISTIC_WRITE)"
    ) < 1:
        drift.append("usage:repository:lock-demo-scenario-id")

    service = sources.get("service")
    if service is not None:
        if service.count("findScenarioForUpdate(scenarioId)") < 4:
            drift.append(
                "usage:service:lock-detect-escalate-resolve-complete"
            )
        transition_tokens = {
            "detect": "inferenceEventService.create(",
            "escalate": "lockIncidentForDemoEscalation(incidentId)",
            "resolve": "alertService.resolve(",
            "complete": "flightSessionService.complete(",
        }
        for method, mutation_token in transition_tokens.items():
            method_at = service.find(
                f"public DemoScenarioResponse {method}("
            )
            next_method_at = service.find(
                "\n    @Transactional",
                method_at + 1,
            )
            method_source = (
                service[method_at:next_method_at]
                if method_at >= 0 and next_method_at >= 0
                else service[method_at:]
                if method_at >= 0
                else ""
            )
            lock_at = method_source.find(
                "findScenarioForUpdate(scenarioId)"
            )
            mutation_at = method_source.find(mutation_token)
            if not (0 <= lock_at < mutation_at):
                drift.append(
                    f"ordering:service:{method}-lock-before-mutation"
                )

        find_at = service.find("public DemoScenarioResponse find(")
        detect_at = service.find("public DemoScenarioResponse detect(")
        find_source = (
            service[find_at:detect_at]
            if 0 <= find_at < detect_at
            else ""
        )
        if (
            "findScenario(scenarioId)" not in find_source
            or "findScenarioForUpdate(scenarioId)" in find_source
        ):
            drift.append("usage:service:read-remains-non-locking")
    return drift


def flight_quality_assessment_concurrency_policy_drift(
    root: Path,
) -> list[str]:
    backend_root = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
    )
    paths = {
        "session-repository": backend_root
        / "java/com/visionflow/api/flight/repository"
        / "FlightSessionRepository.java",
        "assessment-service": backend_root
        / "java/com/visionflow/api/flight/quality/service"
        / "FlightQualityAssessmentService.java",
        "close-automation": backend_root
        / "java/com/visionflow/api/flight/quality/service"
        / "FlightQualityAssessmentAutomationService.java",
        "backfill": backend_root
        / "java/com/visionflow/api/flight/quality/service"
        / "FlightQualityBackfillService.java",
        "migration": backend_root
        / "resources/db/migration"
        / "V16__create_flight_quality_assessment.sql",
    }
    sources: dict[str, str] = {}
    drift: list[str] = []
    for key, path in paths.items():
        if not path.is_file():
            drift.append(f"missing:{key}:{path.relative_to(root)}")
            continue
        sources[key] = path.read_text(encoding="utf-8")

    required_tokens = {
        "session-repository": [
            "LockModeType.PESSIMISTIC_WRITE",
            "findBySessionIdAndDroneIdForUpdate(",
        ],
        "assessment-service": [
            "requireSessionForUpdate(",
            ".findBySessionIdAndDroneIdForUpdate(sessionId, droneId)",
            ".findBySessionIdAndDroneId(sessionId, droneId)",
            ".findBySessionIdAndRuleVersion(",
            "assessmentRepository.saveAndFlush(assessment)",
        ],
        "close-automation": [
            "assessmentService.recalculate(",
        ],
        "backfill": [
            "assessmentService.recalculate(droneId, sessionId)",
        ],
        "migration": [
            "CONSTRAINT uk_flight_quality_session_rule",
            "UNIQUE (session_id, rule_version)",
        ],
    }
    for key, tokens in required_tokens.items():
        source = sources.get(key)
        if source is None:
            continue
        for token in tokens:
            if token not in source:
                drift.append(f"missing-token:{key}:{token}")

    repository = sources.get("session-repository")
    if repository is not None:
        method_at = repository.find(
            "findBySessionIdAndDroneIdForUpdate("
        )
        annotation_at = repository.rfind(
            "@Lock(LockModeType.PESSIMISTIC_WRITE)",
            0,
            method_at,
        )
        if not (0 <= annotation_at < method_at):
            drift.append("usage:session-repository:lock-session-id")

    service = sources.get("assessment-service")
    if service is not None:
        recalculate_at = service.find(
            "public FlightQualityAssessmentResponse recalculate("
        )
        find_at = service.find(
            "public FlightQualityAssessmentResponse find("
        )
        history_at = service.find(
            "public List<FlightQualityAssessmentResponse> findHistory("
        )
        recalculate_source = (
            service[recalculate_at:find_at]
            if 0 <= recalculate_at < find_at
            else ""
        )
        lock_at = recalculate_source.find(
            "requireSessionForUpdate("
        )
        sample_at = recalculate_source.find(
            "countByDroneIdAndFlightSessionId("
        )
        assessment_at = recalculate_source.find(
            ".findBySessionIdAndRuleVersion("
        )
        save_at = recalculate_source.find(
            "assessmentRepository.saveAndFlush(assessment)"
        )
        if not (
            0 <= lock_at < sample_at < assessment_at < save_at
        ):
            drift.append(
                "ordering:assessment-service:session-lock-before-recalculation-write"
            )

        find_source = (
            service[find_at:history_at]
            if 0 <= find_at < history_at
            else ""
        )
        if (
            "requireSession(droneId, sessionId)" not in find_source
            or "requireSessionForUpdate(" in find_source
        ):
            drift.append(
                "usage:assessment-service:read-remains-non-locking"
            )
    return drift


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 최상위 값이 객체가 아닙니다: {path}")
    return value


def migration_sort_key(path: Path) -> tuple[int, str]:
    match = re.match(r"V(\d+)__", path.name)
    return (int(match.group(1)) if match else 999999, path.name)


def parse_migrations(root: Path) -> tuple[dict[str, str], list[dict[str, str]]]:
    migration_root = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
        / "resources"
        / "db"
        / "migration"
    )
    files = sorted(migration_root.glob("V*.sql"), key=migration_sort_key)
    if not files:
        raise FileNotFoundError(f"Flyway migration을 찾지 못했습니다: {migration_root}")

    table_sources: dict[str, str] = {}
    foreign_keys: list[dict[str, str]] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        creates = list(CREATE_TABLE_PATTERN.finditer(text))
        alters = list(ALTER_TABLE_PATTERN.finditer(text))
        for create in creates:
            name = create.group(1).lower()
            if name in table_sources:
                raise ValueError(f"중복 CREATE TABLE: {name}")
            table_sources[name] = path.name

        for foreign_key in FOREIGN_KEY_PATTERN.finditer(text):
            preceding = [
                (item.start(), item.group(1).lower())
                for item in creates
                if item.start() < foreign_key.start()
            ] + [
                (item.start(), item.group(1).lower())
                for item in alters
                if item.start() < foreign_key.start()
            ]
            if not preceding:
                raise ValueError(f"FK의 원본 테이블을 찾지 못했습니다: {path.name}")
            source_table = max(preceding, key=lambda item: item[0])[1]
            clause = text[foreign_key.end():].split(",", 1)[0]
            delete_match = re.search(
                r"\bON\s+DELETE\s+(CASCADE|RESTRICT|SET\s+NULL|NO\s+ACTION)",
                clause,
                re.IGNORECASE,
            )
            delete_rule = (
                re.sub(r"\s+", " ", delete_match.group(1).upper())
                if delete_match
                else "RESTRICT"
            )
            foreign_keys.append(
                {
                    "fromTable": source_table,
                    "fromColumn": foreign_key.group(1).lower(),
                    "toTable": foreign_key.group(2).lower(),
                    "toColumn": foreign_key.group(3).lower(),
                    "source": path.name,
                    "deleteRule": delete_rule,
                }
            )
    effective_foreign_keys: dict[tuple[str, str], dict[str, str]] = {}
    for foreign_key in foreign_keys:
        effective_foreign_keys[
            (foreign_key["fromTable"], foreign_key["fromColumn"])
        ] = foreign_key
    return table_sources, sorted(
        effective_foreign_keys.values(),
        key=lambda item: (
            item["fromTable"],
            item["fromColumn"],
            item["toTable"],
            item["toColumn"],
        ),
    )


def parse_entities(root: Path) -> dict[str, dict[str, str]]:
    java_root = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
        / "java"
    )
    entities: dict[str, dict[str, str]] = {}
    for path in sorted(java_root.rglob("*.java")):
        text = path.read_text(encoding="utf-8")
        entity_at = text.find("@Entity")
        table_at = text.find("@Table", entity_at + 1)
        class_match = CLASS_PATTERN.search(text, entity_at + 1)
        if entity_at < 0:
            continue
        if table_at < 0 or class_match is None:
            raise ValueError(f"@Entity의 @Table 또는 class를 해석하지 못했습니다: {path}")
        table_section = text[table_at : class_match.start()]
        table_match = re.search(r'\bname\s*=\s*"([^"]+)"', table_section)
        if table_match is None:
            raise ValueError(f"@Table name을 해석하지 못했습니다: {path}")
        table = table_match.group(1).lower()
        if table in entities:
            raise ValueError(f"중복 Entity table mapping: {table}")
        entities[table] = {
            "entity": class_match.group(1),
            "source": str(path.relative_to(root)).replace("\\", "/"),
        }
    return entities


def parse_repositories(root: Path) -> dict[str, dict[str, str]]:
    java_root = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
        / "java"
    )
    repositories: dict[str, dict[str, str]] = {}
    for path in sorted(java_root.rglob("*Repository.java")):
        text = path.read_text(encoding="utf-8")
        match = REPOSITORY_PATTERN.search(text)
        if match is None:
            raise ValueError(f"JpaRepository 선언을 해석하지 못했습니다: {path}")
        repository, entity = match.groups()
        if entity in repositories:
            raise ValueError(f"Entity의 Repository가 중복됩니다: {entity}")
        repositories[entity] = {
            "repository": repository,
            "source": str(path.relative_to(root)).replace("\\", "/"),
        }
    return repositories


def operation_text(operation: Any) -> str:
    return f"{operation.method} {operation.path}"


def check(status: str, key: str, title: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"key": key, "title": title, "status": status, "detail": detail, **extra}


def foreign_key_key(value: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(value.get("fromTable", "")),
        str(value.get("fromColumn", "")),
        str(value.get("toTable", "")),
        str(value.get("toColumn", "")),
    )


def assign_flows(
    operations: dict[str, list[Any]],
    flows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[str]], list[dict[str, str]]]:
    assignments: dict[str, list[str]] = defaultdict(list)
    unused_patterns: list[dict[str, str]] = []
    flow_rows: list[dict[str, Any]] = []
    layer_fields = {
        "backend": "backendPatterns",
        "frontend": "frontendPatterns",
        "ai": "aiPatterns",
    }
    for flow in flows:
        key = str(flow.get("key", ""))
        if not key:
            raise ValueError("flow key가 비어 있습니다.")
        row = {
            "key": key,
            "title": str(flow.get("title", key)),
            "description": str(flow.get("description", "")),
            "tables": [str(value) for value in flow.get("tables", [])],
            "runtimeStores": [str(value) for value in flow.get("runtimeStores", [])],
            "operations": {},
        }
        for layer, field in layer_fields.items():
            matched: set[str] = set()
            patterns = flow.get(field, [])
            if not isinstance(patterns, list):
                raise ValueError(f"{key}.{field} 값이 배열이 아닙니다.")
            for raw_pattern in patterns:
                pattern = re.compile(str(raw_pattern))
                pattern_matches = {
                    operation_text(item)
                    for item in operations[layer]
                    if pattern.fullmatch(operation_text(item))
                }
                if not pattern_matches:
                    unused_patterns.append(
                        {"flow": key, "layer": layer, "pattern": str(raw_pattern)}
                    )
                matched.update(pattern_matches)
            row["operations"][layer] = sorted(matched)
            for operation in matched:
                assignments[f"{layer}:{operation}"].append(key)
        flow_rows.append(row)
    return flow_rows, dict(assignments), unused_patterns


def audit(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    root = args.root.resolve()
    baseline_path = args.baseline.resolve()
    baseline = read_object(baseline_path)

    backend, backend_issues = parse_backend_operations(root)
    frontend = parse_frontend_operations(root)
    ai_source = root / "03_ai-server" / "visionflow-ai" / "app" / "streaming.py"
    ai_document = build_openapi(collect_routes(ai_source), ai_source.relative_to(root))
    ai = parse_openapi_operations(ai_document, str(ai_source.relative_to(root)))
    operations = {"backend": backend, "frontend": frontend, "ai": ai}

    tables, foreign_keys = parse_migrations(root)
    entities = parse_entities(root)
    repositories = parse_repositories(root)
    expected_counts = baseline.get("expectedCounts", {})
    actual_counts = {
        "backend": len(backend),
        "frontend": len(frontend),
        "ai": len(ai),
        "tables": len(tables),
        "entities": len(entities),
        "repositories": len(repositories),
        "foreignKeys": len(foreign_keys),
    }

    checks: list[dict[str, Any]] = []
    checks.append(
        check(
            "BLOCKED" if backend_issues else "PASS",
            "source-inventory",
            "API 소스 inventory",
            "Backend·Frontend·AI operation을 정상 해석했습니다."
            if not backend_issues
            else "Backend Controller 해석 문제가 있습니다.",
            issues=backend_issues,
        )
    )

    expected_drone_restrict_relations = {
        ("drone_telemetry_history", "drone_id"),
        ("flight_session", "drone_id"),
        ("flight_quality_assessment", "drone_id"),
        ("maintenance_work_order", "drone_id"),
    }
    actual_drone_relations = {
        (item["fromTable"], item["fromColumn"]): item
        for item in foreign_keys
        if item["toTable"] == "drone" and item["toColumn"] == "id"
    }
    destructive_fk_drift = []
    for relation in sorted(expected_drone_restrict_relations):
        actual = actual_drone_relations.get(relation)
        if actual is None or actual.get("deleteRule") != "RESTRICT":
            destructive_fk_drift.append(
                {
                    "relation": (
                        f"{relation[0]}.{relation[1]} -> drone.id"
                    ),
                    "expectedDeleteRule": "RESTRICT",
                    "actualDeleteRule": (
                        actual.get("deleteRule") if actual is not None else None
                    ),
                }
            )
    checks.append(
        check(
            "BLOCKED" if destructive_fk_drift else "PASS",
            "drone-history-delete-policy",
            "Drone 이력 삭제 정책",
            "Drone 소유 물리 이력 4개 FK의 삭제 연쇄가 RESTRICT로 차단됩니다."
            if not destructive_fk_drift
            else "Drone 삭제 시 물리 이력이 연쇄 삭제될 수 있습니다.",
            drift=destructive_fk_drift,
        )
    )

    drone_mutation_drift = drone_mutation_concurrency_policy_drift(root)
    checks.append(
        check(
            "BLOCKED" if drone_mutation_drift else "PASS",
            "drone-mutation-concurrency-policy",
            "Drone 변경 동시성 정책",
            "기본정보·상태·삭제·텔레메트리 변경이 Drone 행 잠금으로 직렬화되며 읽기 조회는 비잠금으로 유지됩니다."
            if not drone_mutation_drift
            else "Drone 변경 경로의 행 잠금 또는 비잠금 읽기 경계가 누락됐습니다.",
            drift=drone_mutation_drift,
        )
    )

    session_correlation_drift = session_correlation_policy_drift(root)
    checks.append(
        check(
            "BLOCKED" if session_correlation_drift else "PASS",
            "session-correlation-write-policy",
            "비행 세션 상관관계 쓰기 정책",
            "텔레메트리·AI 이벤트 입력이 세션 존재와 Drone 소유권을 영속화 전에 검증합니다."
            if not session_correlation_drift
            else "외부 입력에서 비행 세션 상관관계 검증이 누락됐습니다.",
            drift=session_correlation_drift,
        )
    )
    ai_ingest_drift = ai_inference_ingest_concurrency_policy_drift(
        root
    )
    checks.append(
        check(
            "BLOCKED" if ai_ingest_drift else "PASS",
            "ai-inference-ingest-concurrency-policy",
            "AI 추론 이벤트 수집 동시성 정책",
            "동일 세션의 AI 이벤트 멱등 조회·생성이 Flight Session 행 잠금으로 직렬화되고 V5 프레임 UNIQUE 제약이 최종 방어선으로 유지됩니다."
            if not ai_ingest_drift
            else "AI 이벤트 수집의 세션 잠금, 멱등 조회 또는 DB UNIQUE 방어가 누락됐습니다.",
            drift=ai_ingest_drift,
        )
    )
    ai_alert_creation_drift = (
        ai_alert_creation_concurrency_policy_drift(root)
    )
    checks.append(
        check(
            "BLOCKED" if ai_alert_creation_drift else "PASS",
            "ai-alert-creation-concurrency-policy",
            "AI Alert 생성 동시성 정책",
            "동일 AI 이벤트의 경보 멱등 조회·생성이 추론 이벤트 행 잠금으로 직렬화되고 V10 event UNIQUE 제약이 최종 방어선으로 유지됩니다."
            if not ai_alert_creation_drift
            else "AI 경보 생성의 이벤트 행 잠금, 멱등 조회 또는 DB UNIQUE 방어가 누락됐습니다.",
            drift=ai_alert_creation_drift,
        )
    )
    ai_snapshot_drift = ai_snapshot_concurrency_policy_drift(root)
    checks.append(
        check(
            "BLOCKED" if ai_snapshot_drift else "PASS",
            "ai-snapshot-concurrency-policy",
            "AI 추론 이벤트 스냅샷 동시성 정책",
            "스냅샷 첨부가 AI 추론 이벤트 행 잠금으로 직렬화되며 조회는 비잠금으로 유지됩니다."
            if not ai_snapshot_drift
            else "AI 스냅샷 첨부의 이벤트 행 잠금 또는 비잠금 읽기 경계가 누락됐습니다.",
            drift=ai_snapshot_drift,
        )
    )
    audit_retention_drift = audit_retention_concurrency_policy_drift(
        root
    )
    checks.append(
        check(
            "BLOCKED" if audit_retention_drift else "PASS",
            "audit-retention-concurrency-policy",
            "감사 로그 보존 정리 동시성 정책",
            "수동·예약 보존 정리가 오래된 Audit Log 행 잠금으로 직렬화되며 상태 조회는 비잠금으로 유지됩니다."
            if not audit_retention_drift
            else "감사 로그 보존 정리의 행 잠금 또는 비잠금 상태 조회 경계가 누락됐습니다.",
            drift=audit_retention_drift,
        )
    )
    lifecycle_drift = flight_session_lifecycle_policy_drift(root)
    checks.append(
        check(
            "BLOCKED" if lifecycle_drift else "PASS",
            "flight-session-lifecycle-concurrency-policy",
            "비행 세션 수명주기 동시성 정책",
            "기체별 단일 ACTIVE 세션과 세션 종료 전이가 행 잠금·DB UNIQUE 제약으로 보호됩니다."
            if not lifecycle_drift
            else "비행 세션 시작·갱신 동시성 방어가 누락됐습니다.",
            drift=lifecycle_drift,
        )
    )
    quality_assessment_drift = (
        flight_quality_assessment_concurrency_policy_drift(root)
    )
    checks.append(
        check(
            "BLOCKED" if quality_assessment_drift else "PASS",
            "flight-quality-assessment-concurrency-policy",
            "비행 품질 평가 재계산 동시성 정책",
            "수동·세션 종료·백필 재계산이 Flight Session 행 잠금으로 직렬화되고 읽기 조회는 비잠금으로 유지됩니다."
            if not quality_assessment_drift
            else "비행 품질 평가 재계산의 세션 잠금 또는 DB UNIQUE 방어가 누락됐습니다.",
            drift=quality_assessment_drift,
        )
    )
    incident_lifecycle_drift = (
        incident_lifecycle_concurrency_policy_drift(root)
    )
    checks.append(
        check(
            "BLOCKED" if incident_lifecycle_drift else "PASS",
            "incident-lifecycle-concurrency-policy",
            "Incident 수명주기 동시성 정책",
            "운영자 변경·SLA·품질·비행 게이트 자동화가 Incident 행 잠금으로 직렬화됩니다."
            if not incident_lifecycle_drift
            else "Incident 변경 경로의 행 잠금 또는 중복 방어가 누락됐습니다.",
            drift=incident_lifecycle_drift,
        )
    )
    maintenance_work_order_drift = (
        maintenance_work_order_lifecycle_concurrency_policy_drift(root)
    )
    checks.append(
        check(
            "BLOCKED" if maintenance_work_order_drift else "PASS",
            "maintenance-work-order-lifecycle-concurrency-policy",
            "정비 작업지시 수명주기 동시성 정책",
            "점검 작업 동기화·시작·완료와 SLA 재평가가 Incident→Work Order 잠금 순서 및 V19 UNIQUE 제약으로 보호됩니다."
            if not maintenance_work_order_drift
            else "정비 작업지시 전이 또는 SLA 재평가의 행 잠금·재검증·DB UNIQUE 방어가 누락됐습니다.",
            drift=maintenance_work_order_drift,
        )
    )
    maintenance_mission_control_drift = (
        maintenance_mission_control_ui_policy_drift(root)
    )
    checks.append(
        check(
            "BLOCKED"
            if maintenance_mission_control_drift
            else "PASS",
            "maintenance-mission-control-ui-policy",
            "정비 작전 현황 UI 정책",
            "작업 단계·SLA 긴급 큐와 전체 함대 비행 준비 상태가 인증 프록시 기반 관제 보드로 연결되고 30초 자동 갱신됩니다."
            if not maintenance_mission_control_drift
            else "정비 작전 현황 보드의 데이터 검증·자동 갱신·우선순위 또는 화면 연결이 누락됐습니다.",
            drift=maintenance_mission_control_drift,
        )
    )
    ai_alert_lifecycle_drift = (
        ai_alert_lifecycle_concurrency_policy_drift(root)
    )
    checks.append(
        check(
            "BLOCKED" if ai_alert_lifecycle_drift else "PASS",
            "ai-alert-lifecycle-concurrency-policy",
            "AI Alert 수명주기 동시성 정책",
            "AI 경보 확인·해결 변경이 경보 행 잠금으로 직렬화되며 읽기 조회는 비잠금으로 유지됩니다."
            if not ai_alert_lifecycle_drift
            else "AI 경보 확인·해결 경로의 행 잠금이 누락됐습니다.",
            drift=ai_alert_lifecycle_drift,
        )
    )
    geofence_event_lifecycle_drift = (
        geofence_event_lifecycle_concurrency_policy_drift(root)
    )
    checks.append(
        check(
            "BLOCKED" if geofence_event_lifecycle_drift else "PASS",
            "geofence-event-lifecycle-concurrency-policy",
            "Geofence 위반 이벤트 수명주기 동시성 정책",
            "지오펜스 변경·비활성화·위반 평가가 행 잠금으로 직렬화되고 ACTIVE 이벤트 중복이 DB UNIQUE로 차단됩니다."
            if not geofence_event_lifecycle_drift
            else "Geofence 위반 이벤트의 행 잠금 또는 ACTIVE 중복 방어가 누락됐습니다.",
            drift=geofence_event_lifecycle_drift,
        )
    )
    demo_scenario_lifecycle_drift = (
        demo_scenario_lifecycle_concurrency_policy_drift(root)
    )
    checks.append(
        check(
            "BLOCKED" if demo_scenario_lifecycle_drift else "PASS",
            "demo-scenario-lifecycle-concurrency-policy",
            "Demo Scenario 수명주기 동시성 정책",
            "탐지·에스컬레이션·해결·완료 전이가 시나리오 행 잠금으로 직렬화되며 읽기 조회는 비잠금으로 유지됩니다."
            if not demo_scenario_lifecycle_drift
            else "Demo Scenario 단계 전이의 행 잠금 또는 비잠금 읽기 경계가 누락됐습니다.",
            drift=demo_scenario_lifecycle_drift,
        )
    )
    count_drift = {
        key: {"expected": int(expected_counts.get(key, -1)), "actual": actual}
        for key, actual in actual_counts.items()
        if actual != int(expected_counts.get(key, -1))
    }
    checks.append(
        check(
            "BLOCKED" if count_drift else "PASS",
            "baseline-counts",
            "기준 수량",
            "API·테이블·Entity·Repository·FK 수가 기준과 일치합니다."
            if not count_drift
            else "기준 수량과 다른 항목이 있습니다.",
            drift=count_drift,
        )
    )

    expected_table_rows = baseline.get("tables", [])
    if not isinstance(expected_table_rows, list):
        raise ValueError("baseline tables 값이 배열이 아닙니다.")
    expected_tables = {str(item["name"]): item for item in expected_table_rows}
    missing_tables = sorted(set(expected_tables) - set(tables))
    unexpected_tables = sorted(set(tables) - set(expected_tables))
    migration_drift = [
        {
            "table": name,
            "expected": str(expected_tables[name].get("createdIn", "")),
            "actual": tables[name],
        }
        for name in sorted(set(tables) & set(expected_tables))
        if tables[name] != str(expected_tables[name].get("createdIn", ""))
    ]
    checks.append(
        check(
            "BLOCKED" if missing_tables or unexpected_tables or migration_drift else "PASS",
            "migration-tables",
            "Flyway 테이블",
            "Flyway CREATE TABLE 기준이 일치합니다."
            if not missing_tables and not unexpected_tables and not migration_drift
            else "Flyway 테이블 기준에 드리프트가 있습니다.",
            missing=missing_tables,
            unexpected=unexpected_tables,
            migrationDrift=migration_drift,
        )
    )

    mapping_drift: list[dict[str, Any]] = []
    table_matrix: list[dict[str, Any]] = []
    for name, expected in expected_tables.items():
        entity_row = entities.get(name)
        actual_entity = entity_row.get("entity") if entity_row else None
        repository_row = repositories.get(str(actual_entity)) if actual_entity else None
        actual_repository = repository_row.get("repository") if repository_row else None
        expected_entity = expected.get("entity")
        expected_repository = expected.get("repository")
        if actual_entity != expected_entity or actual_repository != expected_repository:
            mapping_drift.append(
                {
                    "table": name,
                    "expectedEntity": expected_entity,
                    "actualEntity": actual_entity,
                    "expectedRepository": expected_repository,
                    "actualRepository": actual_repository,
                }
            )
        table_matrix.append(
            {
                "table": name,
                "createdIn": tables.get(name),
                "entity": actual_entity,
                "repository": actual_repository,
                "classification": expected.get("classification"),
                "note": expected.get("note", ""),
            }
        )
    entity_unexpected = sorted(set(entities) - set(expected_tables))
    mapped_entities = {str(row.get("entity")) for row in expected_table_rows if row.get("entity")}
    repository_unexpected = sorted(set(repositories) - mapped_entities)
    checks.append(
        check(
            "BLOCKED" if mapping_drift or entity_unexpected or repository_unexpected else "PASS",
            "entity-repository-mapping",
            "Entity·Repository 매핑",
            "15개 영속 모델의 Entity·Repository 매핑이 일치합니다."
            if not mapping_drift and not entity_unexpected and not repository_unexpected
            else "Entity·Repository 매핑에 드리프트가 있습니다.",
            drift=mapping_drift,
            unexpectedEntityTables=entity_unexpected,
            unexpectedRepositoryEntities=repository_unexpected,
        )
    )

    expected_fk_rows = baseline.get("foreignKeys", [])
    if not isinstance(expected_fk_rows, list):
        raise ValueError("baseline foreignKeys 값이 배열이 아닙니다.")
    expected_fk = {foreign_key_key(item) for item in expected_fk_rows}
    actual_fk = {foreign_key_key(item) for item in foreign_keys}
    missing_fk = sorted(expected_fk - actual_fk)
    unexpected_fk = sorted(actual_fk - expected_fk)
    checks.append(
        check(
            "BLOCKED" if missing_fk or unexpected_fk else "PASS",
            "foreign-key-contract",
            "물리 FK 계약",
            "Flyway 물리 FK 12개가 기준과 일치합니다."
            if not missing_fk and not unexpected_fk
            else "물리 FK 기준에 드리프트가 있습니다.",
            missing=[".".join(value) for value in missing_fk],
            unexpected=[".".join(value) for value in unexpected_fk],
        )
    )

    flows = baseline.get("flows", [])
    if not isinstance(flows, list):
        raise ValueError("baseline flows 값이 배열이 아닙니다.")
    flow_rows, assignments, unused_patterns = assign_flows(operations, flows)
    unmapped: dict[str, list[str]] = {}
    for layer, rows in operations.items():
        unmapped[layer] = sorted(
            operation_text(item)
            for item in rows
            if f"{layer}:{operation_text(item)}" not in assignments
        )
    checks.append(
        check(
            "BLOCKED" if any(unmapped.values()) or unused_patterns else "PASS",
            "flow-operation-coverage",
            "기능 흐름별 API coverage",
            "Backend 70·Frontend 71·AI 9 operation이 기능 흐름에 연결됐습니다."
            if not any(unmapped.values()) and not unused_patterns
            else "기능 흐름에 연결되지 않은 operation 또는 사용되지 않은 패턴이 있습니다.",
            unmapped=unmapped,
            unusedPatterns=unused_patterns,
        )
    )

    assigned_tables = {
        table
        for flow in flow_rows
        for table in flow.get("tables", [])
    }
    missing_table_coverage = sorted(set(tables) - assigned_tables)
    unknown_flow_tables = sorted(assigned_tables - set(tables))
    checks.append(
        check(
            "BLOCKED" if missing_table_coverage or unknown_flow_tables else "PASS",
            "flow-table-coverage",
            "기능 흐름별 DB coverage",
            "16개 테이블이 하나 이상의 기능 흐름에 연결됐습니다."
            if not missing_table_coverage and not unknown_flow_tables
            else "기능 흐름과 테이블 연결에 누락 또는 잘못된 이름이 있습니다.",
            missing=missing_table_coverage,
            unknown=unknown_flow_tables,
        )
    )

    status = (
        "SYSTEM_TRACEABILITY_BLOCKED"
        if any(item["status"] == "BLOCKED" for item in checks)
        else "SYSTEM_TRACEABILITY_HEALTHY"
    )
    generated_at = datetime.now(timezone.utc)
    output_dir = args.output
    if output_dir is None:
        output_dir = (
            root
            / "artifacts"
            / "system-traceability-audit"
            / generated_at.strftime("audit-%Y%m%dT%H%M%SZ")
        )
    elif not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir = output_dir.resolve()

    report = {
        "schemaVersion": 1,
        "project": "visionflow",
        "scope": "SYSTEM_API_DB_TRACEABILITY",
        "generatedAt": generated_at.isoformat(),
        "status": status,
        "readOnly": True,
        "git": {
            "commit": current_git_commit(root),
            "baselineCommit": baseline.get("baselineCommit"),
        },
        "summary": {
            "counts": actual_counts,
            "flows": len(flow_rows),
            "softCorrelations": len(baseline.get("softCorrelations", [])),
        },
        "checks": checks,
        "tables": table_matrix,
        "foreignKeys": foreign_keys,
        "softCorrelations": baseline.get("softCorrelations", []),
        "flows": flow_rows,
        "assignments": assignments,
        "safety": {
            "databaseMutation": False,
            "containerMutation": False,
            "serviceRestart": False,
            "secretValuesCollected": False,
            "writesOnlyReports": True,
        },
    }
    return report, output_dir


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        values = [str(value if value not in (None, "") else "—").replace("|", "\\|") for value in row]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    counts = report["summary"]["counts"]
    checks = markdown_table(
        ["상태", "검사", "설명"],
        [[row["status"], row["title"], row["detail"]] for row in report["checks"]],
    )
    tables = markdown_table(
        ["Table", "Migration", "Entity", "Repository", "분류", "비고"],
        [
            [row["table"], row["createdIn"], row["entity"], row["repository"], row["classification"], row["note"]]
            for row in report["tables"]
        ],
    )
    foreign_keys = markdown_table(
        ["From", "To", "Migration"],
        [
            [f"{row['fromTable']}.{row['fromColumn']}", f"{row['toTable']}.{row['toColumn']}", row["source"]]
            for row in report["foreignKeys"]
        ],
    )
    flow_rows = []
    for flow in report["flows"]:
        operation_counts = flow["operations"]
        flow_rows.append(
            [
                flow["title"],
                len(operation_counts["backend"]),
                len(operation_counts["frontend"]),
                len(operation_counts["ai"]),
                ", ".join(flow["tables"]) or "—",
                ", ".join(flow["runtimeStores"]) or "—",
            ]
        )
    flows = markdown_table(
        ["기능 흐름", "Backend", "Frontend", "AI", "DB tables", "런타임 저장소"],
        flow_rows,
    )
    soft = markdown_table(
        ["상관키", "관련 테이블", "정합성 위험"],
        [
            [row["key"], ", ".join(row["tables"]), row["risk"]]
            for row in report["softCorrelations"]
        ],
    )
    return f"""# VisionFlow 시스템 API·DB 추적성 감사

- 생성 시각: `{report['generatedAt']}`
- 상태: **{report['status']}**
- API: Backend {counts['backend']} · Frontend {counts['frontend']} · AI {counts['ai']}
- 데이터: Table {counts['tables']} · Entity {counts['entities']} · Repository {counts['repositories']} · FK {counts['foreignKeys']}

## 검사 결과

{checks}

## 기능 흐름 매트릭스

{flows}

## DB 테이블 매트릭스

{tables}

## 물리 FK

{foreign_keys}

## 소프트 상관관계

{soft}

> 읽기 전용 감사입니다. DB·컨테이너·서비스·비밀값을 변경하거나 수집하지 않습니다.
"""


def render_html(report: dict[str, Any]) -> str:
    markdown = render_markdown(report)
    rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(item["status"]),
            html.escape(item["title"]),
            html.escape(item["detail"]),
        )
        for item in report["checks"]
    )
    flow_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(flow["title"]),
            len(flow["operations"]["backend"]),
            len(flow["operations"]["frontend"]),
            len(flow["operations"]["ai"]),
            html.escape(", ".join(flow["tables"]) or "—"),
        )
        for flow in report["flows"]
    )
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>VisionFlow System Traceability</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;background:#f4f7fb;color:#172033;margin:0}}main{{max-width:1280px;margin:auto;padding:28px}}section{{background:white;border:1px solid #dbe3ef;border-radius:14px;padding:20px;margin-top:18px;overflow:auto}}.hero{{background:#071126;color:white}}table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid #e5eaf2;padding:8px;text-align:left;vertical-align:top}}th{{background:#f8fafc}}code{{white-space:pre-wrap}}</style></head>
<body><main><section class="hero"><h1>VisionFlow 시스템 API·DB 추적성</h1><p>{html.escape(report['generatedAt'])}</p><strong>{html.escape(report['status'])}</strong></section>
<section><h2>검사 결과</h2><table><thead><tr><th>상태</th><th>검사</th><th>설명</th></tr></thead><tbody>{rows}</tbody></table></section>
<section><h2>기능 흐름</h2><table><thead><tr><th>흐름</th><th>Backend</th><th>Frontend</th><th>AI</th><th>DB tables</th></tr></thead><tbody>{flow_rows}</tbody></table></section>
<section><h2>Markdown 원문</h2><pre><code>{html.escape(markdown)}</code></pre></section></main></body></html>"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="VisionFlow Backend·Frontend·AI·DB 읽기 전용 시스템 추적성 감사"
    )
    parser.add_argument("--root", type=Path, default=script_dir.parent)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=script_dir / "visionflow_system_traceability_baseline.json",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_console()
    args = parse_args(argv)
    try:
        report, output_dir = audit(args)
        json_path = output_dir / "visionflow-system-traceability-audit.json"
        markdown_path = output_dir / "visionflow-system-traceability-matrix.md"
        html_path = output_dir / "visionflow-system-traceability-audit.html"
        atomic_write_text(json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        atomic_write_text(markdown_path, render_markdown(report))
        atomic_write_text(html_path, render_html(report))
    except (OSError, SyntaxError, ValueError, json.JSONDecodeError, re.error) as error:
        print(f"[FAIL] 시스템 추적성 감사를 실행하지 못했습니다: {error}", file=sys.stderr)
        return 2

    print(f"VisionFlow system traceability audit: {report['status']}")
    counts = report["summary"]["counts"]
    print(
        "Operations: "
        f"Backend={counts['backend']}, Frontend={counts['frontend']}, AI={counts['ai']}"
    )
    print(
        "Data model: "
        f"Tables={counts['tables']}, Entities={counts['entities']}, "
        f"Repositories={counts['repositories']}, ForeignKeys={counts['foreignKeys']}"
    )
    for item in report["checks"]:
        print(f"[{item['status']}] {item['key']}: {item['detail']}")
    print(f"JSON report: {json_path}")
    print(f"HTML report: {html_path}")
    print(f"Markdown matrix: {markdown_path}")
    print("Safety: read-only; reports only; no runtime or secret access")
    return 1 if report["status"] == "SYSTEM_TRACEABILITY_BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
