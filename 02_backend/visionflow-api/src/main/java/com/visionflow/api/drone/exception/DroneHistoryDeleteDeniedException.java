package com.visionflow.api.drone.exception;

import com.visionflow.api.common.exception.BusinessException;
import org.springframework.http.HttpStatus;

public class DroneHistoryDeleteDeniedException
        extends BusinessException {

    public DroneHistoryDeleteDeniedException(String message) {
        super(
                HttpStatus.CONFLICT,
                "DRONE_HISTORY_DELETE_DENIED",
                message
        );
    }
}
