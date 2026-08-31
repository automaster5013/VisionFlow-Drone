package com.visionflow.api.common.security;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.common.exception.ErrorResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;
import java.util.Optional;

@RestController
@RequestMapping("/api/security")
public class OperatorPasswordController {

    private static final Logger log = LoggerFactory.getLogger(
            OperatorPasswordController.class
    );

    private final OperatorUserAuthenticationService userAuthenticationService;
    private final OperatorSessionRegistry sessionRegistry;
    private final OperatorInitialCredentialStore credentialStore;
    private final OperatorLoginAttemptGuard loginAttemptGuard;
    private final AuditLogService auditLogService;

    public OperatorPasswordController(
            OperatorUserAuthenticationService userAuthenticationService,
            OperatorSessionRegistry sessionRegistry,
            OperatorInitialCredentialStore credentialStore,
            OperatorLoginAttemptGuard loginAttemptGuard,
            AuditLogService auditLogService
    ) {
        this.userAuthenticationService = userAuthenticationService;
        this.sessionRegistry = sessionRegistry;
        this.credentialStore = credentialStore;
        this.loginAttemptGuard = loginAttemptGuard;
        this.auditLogService = auditLogService;
    }

    @PostMapping("/password")
    public ResponseEntity<?> changeInitialPassword(
            @Valid @RequestBody OperatorPasswordChangeRequest request,
            Authentication authentication,
            HttpServletRequest servletRequest
    ) {
        OperatorPrincipal principal = authentication != null
                && authentication.getPrincipal() instanceof OperatorPrincipal value
                ? value
                : null;
        if (principal == null) {
            return ResponseEntity
                    .status(HttpStatus.UNAUTHORIZED)
                    .body(
                            ErrorResponse.of(
                                    "OPERATOR_AUTHENTICATION_REQUIRED",
                                    "비밀번호를 변경하려면 운영자 로그인이 필요합니다."
                            )
                    );
        }
        if (!principal.passwordChangeRequired()) {
            return ResponseEntity
                    .status(HttpStatus.CONFLICT)
                    .body(
                            ErrorResponse.of(
                                    "OPERATOR_PASSWORD_CHANGE_NOT_REQUIRED",
                                    "이 계정은 초기 비밀번호 변경이 필요하지 않습니다."
                            )
                    );
        }

        Optional<OperatorPrincipal> changed;
        try {
            changed = userAuthenticationService.changeInitialPassword(
                    principal.username(),
                    request.newPassword()
            );
        } catch (IllegalArgumentException error) {
            return ResponseEntity
                    .badRequest()
                    .body(
                            ErrorResponse.of(
                                    "INVALID_OPERATOR_PASSWORD",
                                    error.getMessage()
                            )
                    );
        }
        if (changed.isEmpty()) {
            return ResponseEntity
                    .status(HttpStatus.CONFLICT)
                    .body(
                            ErrorResponse.of(
                                    "OPERATOR_PASSWORD_CHANGE_UNAVAILABLE",
                                    "현재 계정의 초기 비밀번호를 변경할 수 없습니다."
                            )
                    );
        }

        sessionRegistry.revokeAllForUsername(principal.username());
        String clientFingerprint = loginAttemptGuard.fingerprint(
                servletRequest.getRemoteAddr()
        );
        OperatorSession replacement = sessionRegistry.issue(
                changed.get(),
                clientFingerprint
        );
        credentialStore.removeCredential(principal.username());
        recordAudit(
                replacement,
                changed.get(),
                clientFingerprint
        );
        return ResponseEntity.ok(OperatorSessionResponse.from(replacement));
    }

    private void recordAudit(
            OperatorSession session,
            OperatorPrincipal principal,
            String clientFingerprint
    ) {
        try {
            auditLogService.recordAuthenticationEvent(
                    AuditAction.OPERATOR_PASSWORD_CHANGED,
                    session.sessionId().toString(),
                    "운영자 초기 비밀번호 변경",
                    Map.of(
                            "role", principal.role().name(),
                            "clientFingerprint", clientFingerprint,
                            "expiresAt", session.expiresAt().toString()
                    ),
                    principal.username()
            );
        } catch (RuntimeException error) {
            log.warn("운영자 비밀번호 변경 감사 로그 기록 실패", error);
        }
    }
}
