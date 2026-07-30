package com.visionflow.api.common.exception;

import org.springframework.http.HttpStatus;

public class DuplicateResourceException extends BusinessException {

    public DuplicateResourceException(String message) {
        super(
                HttpStatus.CONFLICT,
                "DUPLICATE_RESOURCE",
                message
        );
    }
}