package com.visionflow.api.common.exception;

import jakarta.validation.ConstraintViolationException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import java.util.LinkedHashMap;
import java.util.Map;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log =
            LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ErrorResponse> handleBusinessException(
            BusinessException exception
    ) {
        return ResponseEntity
                .status(exception.getStatus())
                .body(
                        ErrorResponse.of(
                                exception.getCode(),
                                exception.getMessage()
                        )
                );
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidationException(
            MethodArgumentNotValidException exception
    ) {
        Map<String, String> errors = new LinkedHashMap<>();

        for (FieldError fieldError
                : exception.getBindingResult().getFieldErrors()) {

            errors.putIfAbsent(
                    fieldError.getField(),
                    fieldError.getDefaultMessage()
            );
        }

        return ResponseEntity
                .badRequest()
                .body(ErrorResponse.validation(errors));
    }

    @ExceptionHandler(ConstraintViolationException.class)
    public ResponseEntity<ErrorResponse> handleConstraintViolation(
            ConstraintViolationException exception
    ) {
        Map<String, String> errors = new LinkedHashMap<>();

        exception.getConstraintViolations().forEach(violation ->
                errors.putIfAbsent(
                        violation.getPropertyPath().toString(),
                        violation.getMessage()
                )
        );

        return ResponseEntity
                .badRequest()
                .body(ErrorResponse.validation(errors));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ErrorResponse> handleUnreadableMessage(
            HttpMessageNotReadableException exception
    ) {
        return ResponseEntity
                .badRequest()
                .body(
                        ErrorResponse.of(
                                "INVALID_REQUEST_BODY",
                                "요청 본문 형식이 올바르지 않습니다."
                        )
                );
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<ErrorResponse> handleDataIntegrityViolation(
            DataIntegrityViolationException exception
    ) {
        log.warn("Database constraint violation", exception);

        return ResponseEntity
                .status(HttpStatus.CONFLICT)
                .body(
                        ErrorResponse.of(
                                "DATA_INTEGRITY_VIOLATION",
                                "중복 데이터 또는 데이터베이스 제약조건 위반이 발생했습니다."
                        )
                );
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleUnexpectedException(
            Exception exception
    ) {
        log.error("Unexpected server error", exception);

        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(
                        ErrorResponse.of(
                                "INTERNAL_SERVER_ERROR",
                                "서버 내부 오류가 발생했습니다."
                        )
                );
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ErrorResponse> handleTypeMismatch(
            MethodArgumentTypeMismatchException exception
    ) {
        String parameterName = exception.getName();

        String message =
                parameterName + " 파라미터 값이 올바르지 않습니다.";

        if ("status".equals(parameterName)) {
            message =
                    "status는 OFFLINE, ONLINE, FLYING, CHARGING, "
                            + "MAINTENANCE, ERROR 중 하나여야 합니다.";
        }

        return ResponseEntity
                .badRequest()
                .body(
                        ErrorResponse.of(
                                "INVALID_PARAMETER",
                                message
                        )
                );
    }
}