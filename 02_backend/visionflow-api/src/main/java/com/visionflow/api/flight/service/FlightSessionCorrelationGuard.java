package com.visionflow.api.flight.service;

import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.flight.domain.FlightSession;
import com.visionflow.api.flight.exception.FlightSessionDroneMismatchException;
import com.visionflow.api.flight.repository.FlightSessionRepository;
import org.springframework.stereotype.Service;

import java.util.Objects;

@Service
public class FlightSessionCorrelationGuard {

    private final FlightSessionRepository sessionRepository;

    public FlightSessionCorrelationGuard(
            FlightSessionRepository sessionRepository
    ) {
        this.sessionRepository = sessionRepository;
    }

    public String requireOwnedSession(
            String sessionId,
            Long droneId
    ) {
        String normalizedSessionId = normalizeRequired(sessionId);
        FlightSession session = sessionRepository
                .findById(normalizedSessionId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "비행 세션을 찾을 수 없습니다: "
                                + normalizedSessionId
                ));

        if (!Objects.equals(session.getDroneId(), droneId)) {
            throw new FlightSessionDroneMismatchException(
                    "비행 세션이 요청한 드론에 속하지 않습니다. "
                            + "sessionId="
                            + normalizedSessionId
                            + ", droneId="
                            + droneId
            );
        }

        return normalizedSessionId;
    }

    public String requireOwnedSessionForUpdate(
            String sessionId,
            Long droneId
    ) {
        String normalizedSessionId = normalizeRequired(sessionId);
        return sessionRepository
                .findBySessionIdAndDroneIdForUpdate(
                        normalizedSessionId,
                        droneId
                )
                .map(FlightSession::getSessionId)
                .orElseGet(() -> requireOwnedSession(
                        normalizedSessionId,
                        droneId
                ));
    }

    public String requireOptionalOwnedSession(
            String sessionId,
            Long droneId
    ) {
        String normalizedSessionId = normalizeOptional(sessionId);
        return normalizedSessionId == null
                ? null
                : requireOwnedSession(normalizedSessionId, droneId);
    }

    private String normalizeRequired(String value) {
        String normalized = normalizeOptional(value);
        if (normalized == null) {
            throw new ResourceNotFoundException(
                    "비행 세션 ID가 필요합니다."
            );
        }
        return normalized;
    }

    private String normalizeOptional(String value) {
        if (value == null) {
            return null;
        }
        String normalized = value.trim();
        return normalized.isEmpty() ? null : normalized;
    }
}
