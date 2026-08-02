package com.visionflow.api.flight.exception;

import com.visionflow.api.common.exception.BusinessException;
import org.springframework.http.HttpStatus;

public class FlightSessionDroneMismatchException extends BusinessException {

    public FlightSessionDroneMismatchException(String message) {
        super(
                HttpStatus.CONFLICT,
                "FLIGHT_SESSION_DRONE_MISMATCH",
                message
        );
    }
}
