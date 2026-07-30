package com.visionflow.api.maintenance.exception;

import com.visionflow.api.common.exception.BusinessException;
import org.springframework.http.HttpStatus;

public class FlightClearanceRequiredException
        extends BusinessException {

    public FlightClearanceRequiredException(String message) {
        super(
                HttpStatus.CONFLICT,
                "DRONE_FLIGHT_CLEARANCE_REQUIRED",
                message
        );
    }
}
