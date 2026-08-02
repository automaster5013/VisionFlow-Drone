package com.visionflow.api.flight.exception;

import com.visionflow.api.common.exception.BusinessException;
import org.springframework.http.HttpStatus;

public class ActiveFlightSessionExistsException extends BusinessException {

    public ActiveFlightSessionExistsException(Long droneId) {
        super(
                HttpStatus.CONFLICT,
                "ACTIVE_FLIGHT_SESSION_EXISTS",
                "이미 진행 중인 비행 세션이 있습니다. droneId=" + droneId
        );
    }
}
