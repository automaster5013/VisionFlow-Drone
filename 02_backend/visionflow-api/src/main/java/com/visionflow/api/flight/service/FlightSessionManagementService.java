package com.visionflow.api.flight.service;

import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.drone.domain.Drone;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.domain.FlightSession;
import com.visionflow.api.flight.domain.FlightSessionStatus;
import com.visionflow.api.flight.dto.FlightSessionResponse;
import com.visionflow.api.flight.dto.FlightSessionStartRequest;
import com.visionflow.api.flight.dto.FlightSessionUpdateRequest;
import com.visionflow.api.flight.event.FlightSessionClosedEvent;
import com.visionflow.api.flight.exception.ActiveFlightSessionExistsException;
import com.visionflow.api.flight.repository.FlightSessionRepository;
import com.visionflow.api.maintenance.service.MaintenanceFlightGateService;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.UUID;

@Service
public class FlightSessionManagementService {

    private static final String ACTIVE_SESSION_UNIQUE_CONSTRAINT =
            "uq_flight_session_one_active_per_drone";

    private static final DateTimeFormatter DEFAULT_NAME_FORMAT =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm 비행");

    private final DroneRepository droneRepository;
    private final FlightSessionRepository sessionRepository;
    private final ApplicationEventPublisher eventPublisher;
    private final MaintenanceFlightGateService flightGateService;

    public FlightSessionManagementService(
            DroneRepository droneRepository,
            FlightSessionRepository sessionRepository,
            ApplicationEventPublisher eventPublisher,
            MaintenanceFlightGateService flightGateService
    ) {
        this.droneRepository = droneRepository;
        this.sessionRepository = sessionRepository;
        this.eventPublisher = eventPublisher;
        this.flightGateService = flightGateService;
    }

    @Transactional
    public FlightSessionResponse start(
            Long droneId,
            FlightSessionStartRequest request
    ) {
        Drone drone = droneRepository.findByIdForUpdate(droneId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "드론을 찾을 수 없습니다: " + droneId
                ));

        sessionRepository
                .findFirstByDroneIdAndStatusOrderByStartedAtDesc(
                        droneId,
                        FlightSessionStatus.ACTIVE
                )
                .ifPresent(activeSession -> {
                    throw new ActiveFlightSessionExistsException(droneId);
                });

        flightGateService.requireStartClearance(droneId);

        LocalDateTime now = LocalDateTime.now();
        String name = normalizeStartName(
                request.name(),
                drone.getName(),
                now
        );

        FlightSession session = FlightSession.start(
                UUID.randomUUID().toString(),
                droneId,
                name,
                normalizeOptionalText(
                        request.description(),
                        500,
                        "비행 세션 설명"
                ),
                normalizeOptionalText(
                        request.sourceDeviceId(),
                        100,
                        "소스 장치 ID"
                ),
                now
        );

        try {
            return FlightSessionResponse.from(
                    sessionRepository.saveAndFlush(session)
            );
        } catch (DataIntegrityViolationException exception) {
            if (isActiveSessionUniquenessViolation(exception)) {
                throw new ActiveFlightSessionExistsException(droneId);
            }

            throw exception;
        }
    }

    @Transactional(readOnly = true)
    public FlightSessionResponse find(Long droneId, String sessionId) {
        return FlightSessionResponse.from(
                findManagedSession(droneId, sessionId)
        );
    }

    @Transactional
    public FlightSessionResponse update(
            Long droneId,
            String sessionId,
            FlightSessionUpdateRequest request
    ) {
        if (request.name() == null && request.description() == null) {
            throw new IllegalArgumentException(
                    "수정할 세션명 또는 설명을 입력해 주세요."
            );
        }

        FlightSession session = findManagedSessionForUpdate(
                droneId,
                sessionId
        );

        if (request.name() != null) {
            session.rename(normalizeRequiredName(request.name()));
        }

        if (request.description() != null) {
            session.changeDescription(normalizeOptionalText(
                    request.description(),
                    500,
                    "비행 세션 설명"
            ));
        }

        return FlightSessionResponse.from(session);
    }

    @Transactional
    public FlightSessionResponse complete(
            Long droneId,
            String sessionId
    ) {
        FlightSession session = findManagedSessionForUpdate(
                droneId,
                sessionId
        );
        boolean transitioned =
                session.getStatus() != FlightSessionStatus.COMPLETED;
        session.complete(LocalDateTime.now());

        if (transitioned) {
            publishClosedEvent(session);
        }

        return FlightSessionResponse.from(session);
    }

    @Transactional
    public FlightSessionResponse abort(
            Long droneId,
            String sessionId
    ) {
        FlightSession session = findManagedSessionForUpdate(
                droneId,
                sessionId
        );
        boolean transitioned =
                session.getStatus() != FlightSessionStatus.ABORTED;
        session.abort(LocalDateTime.now());

        if (transitioned) {
            publishClosedEvent(session);
        }

        return FlightSessionResponse.from(session);
    }

    private void publishClosedEvent(FlightSession session) {
        eventPublisher.publishEvent(new FlightSessionClosedEvent(
                session.getDroneId(),
                session.getSessionId(),
                session.getStatus()
        ));
    }

    private boolean isActiveSessionUniquenessViolation(
            DataIntegrityViolationException exception
    ) {
        Throwable current = exception;

        while (current != null) {
            String message = current.getMessage();
            if (message != null
                    && message.contains(ACTIVE_SESSION_UNIQUE_CONSTRAINT)) {
                return true;
            }
            current = current.getCause();
        }

        return false;
    }

    private FlightSession findManagedSession(
            Long droneId,
            String sessionId
    ) {
        String normalizedSessionId = normalizeSessionId(sessionId);

        return sessionRepository
                .findBySessionIdAndDroneId(
                        normalizedSessionId,
                        droneId
                )
                .orElseThrow(() -> new ResourceNotFoundException(
                        "관리 비행 세션을 찾을 수 없습니다: "
                                + normalizedSessionId
                ));
    }

    private FlightSession findManagedSessionForUpdate(
            Long droneId,
            String sessionId
    ) {
        String normalizedSessionId = normalizeSessionId(sessionId);

        return sessionRepository
                .findBySessionIdAndDroneIdForUpdate(
                        normalizedSessionId,
                        droneId
                )
                .orElseThrow(() -> new ResourceNotFoundException(
                        "관리 비행 세션을 찾을 수 없습니다: "
                                + normalizedSessionId
                ));
    }

    private String normalizeStartName(
            String value,
            String droneName,
            LocalDateTime startedAt
    ) {
        if (value == null || value.isBlank()) {
            return droneName + " " + startedAt.format(DEFAULT_NAME_FORMAT);
        }

        return normalizeRequiredName(value);
    }

    private String normalizeRequiredName(String value) {
        String normalized = value.trim();

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(
                    "비행 세션명은 비어 있을 수 없습니다."
            );
        }

        if (normalized.length() > 120) {
            throw new IllegalArgumentException(
                    "비행 세션명은 120자 이하여야 합니다."
            );
        }

        return normalized;
    }

    private String normalizeOptionalText(
            String value,
            int maximumLength,
            String fieldName
    ) {
        if (value == null) {
            return null;
        }

        String normalized = value.trim();

        if (normalized.length() > maximumLength) {
            throw new IllegalArgumentException(
                    fieldName + "는 " + maximumLength
                            + "자 이하여야 합니다."
            );
        }

        return normalized.isEmpty() ? null : normalized;
    }

    private String normalizeSessionId(String sessionId) {
        if (sessionId == null) {
            throw new IllegalArgumentException(
                    "비행 세션 ID는 필수입니다."
            );
        }

        String normalized = sessionId.trim();

        if (normalized.isEmpty() || normalized.length() > 36) {
            throw new IllegalArgumentException(
                    "비행 세션 ID는 1~36자여야 합니다."
            );
        }

        return normalized;
    }
}
