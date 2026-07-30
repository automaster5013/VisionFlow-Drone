package com.visionflow.api.common.security;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.common.exception.ErrorResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@RestController
@RequestMapping("/api/security")
public class OperatorSecurityController {

    private static final Logger log = LoggerFactory.getLogger(
            OperatorSecurityController.class
    );
    private static final String ANONYMOUS_ACTOR = "anonymous";

    private final OperatorCredentialRegistry credentialRegistry;
    private final OperatorSessionRegistry sessionRegistry;
    private final OperatorLoginAttemptGuard loginAttemptGuard;
    private final AuditLogService auditLogService;

    public OperatorSecurityController(
            OperatorCredentialRegistry credentialRegistry,
            OperatorSessionRegistry sessionRegistry,
            OperatorLoginAttemptGuard loginAttemptGuard,
            AuditLogService auditLogService
    ) {
        this.credentialRegistry = credentialRegistry;
        this.sessionRegistry = sessionRegistry;
        this.loginAttemptGuard = loginAttemptGuard;
        this.auditLogService = auditLogService;
    }

    @GetMapping("/me")
    public OperatorSecurityStatusResponse me(Authentication authentication) {
        if (!credentialRegistry.isEnabled()) {
            return new OperatorSecurityStatusResponse(
                    false,
                    false,
                    "local-operator",
                    "LOCAL"
            );
        }

        if (
                authentication != null
                        && authentication.getPrincipal() instanceof OperatorPrincipal principal
        ) {
            return new OperatorSecurityStatusResponse(
                    true,
                    true,
                    principal.username(),
                    principal.role().name()
            );
        }

        return new OperatorSecurityStatusResponse(
                true,
                false,
                null,
                null
        );
    }

    @PostMapping("/sessions")
    public ResponseEntity<?> createSession(HttpServletRequest request) {
        if (!credentialRegistry.isEnabled()) {
            return ResponseEntity
                    .status(HttpStatus.CONFLICT)
                    .body(
                            ErrorResponse.of(
                                    "OPERATOR_SECURITY_DISABLED",
                                    "운영자 RBAC가 비활성화되어 로그인 세션이 필요하지 않습니다."
                            )
                    );
        }

        String clientFingerprint = loginAttemptGuard.fingerprint(
                request.getRemoteAddr()
        );
        OperatorLoginAttemptGuard.AttemptDecision current =
                loginAttemptGuard.inspect(clientFingerprint);
        if (!current.allowed()) {
            return loginRateLimited(current);
        }

        String presentedKey = request.getHeader(
                OperatorAuthenticationFilter.OPERATOR_KEY_HEADER
        );
        Optional<OperatorPrincipal> resolved = credentialRegistry.resolve(presentedKey);
        if (resolved.isEmpty()) {
            OperatorLoginAttemptGuard.AttemptDecision failed =
                    loginAttemptGuard.recordFailure(clientFingerprint);
            recordAuthenticationAudit(
                    failed.allowed()
                            ? AuditAction.OPERATOR_LOGIN_FAILED
                            : AuditAction.OPERATOR_LOGIN_LOCKED,
                    clientFingerprint,
                    failed.allowed()
                            ? "운영자 로그인 실패"
                            : "운영자 로그인 일시 잠금",
                    Map.of(
                            "failureCount", failed.failureCount(),
                            "remainingAttempts", failed.remainingAttempts(),
                            "retryAfterSeconds", failed.retryAfterSeconds()
                    ),
                    ANONYMOUS_ACTOR
            );
            if (!failed.allowed()) {
                return loginRateLimited(failed);
            }
            return ResponseEntity
                    .status(HttpStatus.UNAUTHORIZED)
                    .body(
                            ErrorResponse.of(
                                    "INVALID_OPERATOR_KEY",
                                    "운영자 인증 키가 올바르지 않습니다."
                            )
                    );
        }

        OperatorPrincipal principal = resolved.get();
        loginAttemptGuard.recordSuccess(clientFingerprint);
        OperatorSession session = sessionRegistry.issue(
                principal,
                clientFingerprint
        );
        recordAuthenticationAudit(
                AuditAction.OPERATOR_LOGIN_SUCCEEDED,
                session.sessionId().toString(),
                "운영자 로그인 성공",
                Map.of(
                        "role", principal.role().name(),
                        "clientFingerprint", clientFingerprint,
                        "expiresAt", session.expiresAt().toString()
                ),
                principal.username()
        );
        return ResponseEntity.ok(OperatorSessionResponse.from(session));
    }

    @GetMapping("/sessions")
    public List<OperatorSessionSummary> findSessions(
            HttpServletRequest request
    ) {
        return sessionRegistry.findAll(
                request.getHeader(
                        OperatorAuthenticationFilter.OPERATOR_SESSION_HEADER
                )
        );
    }

    @DeleteMapping("/sessions/{sessionId}")
    public ResponseEntity<?> revokeSession(
            @PathVariable UUID sessionId,
            Authentication authentication,
            HttpServletRequest request
    ) {
        OperatorPrincipal administrator = authentication != null
                && authentication.getPrincipal() instanceof OperatorPrincipal value
                ? value
                : null;
        if (credentialRegistry.isEnabled() && administrator == null) {
            return ResponseEntity
                    .status(HttpStatus.UNAUTHORIZED)
                    .body(
                            ErrorResponse.of(
                                    "OPERATOR_AUTHENTICATION_REQUIRED",
                                    "활성 세션을 종료하려면 ADMIN 인증이 필요합니다."
                            )
                    );
        }

        String currentToken = request.getHeader(
                OperatorAuthenticationFilter.OPERATOR_SESSION_HEADER
        );
        Optional<OperatorSessionSummary> current = sessionRegistry.findByToken(
                currentToken
        );
        if (
                current.isPresent()
                        && current.get().sessionId().equals(sessionId)
        ) {
            return ResponseEntity
                    .status(HttpStatus.CONFLICT)
                    .body(
                            ErrorResponse.of(
                                    "CURRENT_OPERATOR_SESSION_REVOKE_DENIED",
                                    "현재 사용 중인 세션은 로그아웃 버튼으로 종료하세요."
                            )
                    );
        }

        Optional<OperatorSessionSummary> revoked = sessionRegistry.revokeById(
                sessionId
        );
        if (revoked.isEmpty()) {
            return ResponseEntity
                    .status(HttpStatus.NOT_FOUND)
                    .body(
                            ErrorResponse.of(
                                    "OPERATOR_SESSION_NOT_FOUND",
                                    "활성 운영자 세션을 찾을 수 없습니다."
                            )
                    );
        }

        OperatorSessionSummary target = revoked.get();
        String actor = administrator == null
                ? "local-operator"
                : administrator.username();
        recordAuthenticationAudit(
                AuditAction.OPERATOR_SESSION_REVOKED,
                target.sessionId().toString(),
                "운영자 세션 강제 종료",
                Map.of(
                        "targetUsername", target.username(),
                        "targetRole", target.role().name(),
                        "issuedAt", target.issuedAt().toString()
                ),
                actor
        );
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/sessions/others")
    public ResponseEntity<?> revokeOtherSessions(
            @RequestParam(defaultValue = "false") boolean confirm,
            Authentication authentication,
            HttpServletRequest request
    ) {
        OperatorPrincipal administrator = authentication != null
                && authentication.getPrincipal() instanceof OperatorPrincipal value
                ? value
                : null;
        if (credentialRegistry.isEnabled() && administrator == null) {
            return ResponseEntity
                    .status(HttpStatus.UNAUTHORIZED)
                    .body(
                            ErrorResponse.of(
                                    "OPERATOR_AUTHENTICATION_REQUIRED",
                                    "다른 세션을 일괄 종료하려면 ADMIN 인증이 필요합니다."
                            )
                    );
        }
        if (!confirm) {
            return ResponseEntity
                    .badRequest()
                    .body(
                            ErrorResponse.of(
                                    "OPERATOR_BULK_SESSION_REVOKE_CONFIRMATION_REQUIRED",
                                    "다른 활성 세션을 모두 종료하려면 confirm=true가 필요합니다."
                            )
                    );
        }

        String currentToken = request.getHeader(
                OperatorAuthenticationFilter.OPERATOR_SESSION_HEADER
        );
        boolean currentSessionPreserved = sessionRegistry
                .findByToken(currentToken)
                .isPresent();
        List<OperatorSessionSummary> revoked = sessionRegistry.revokeAllExcept(
                currentToken
        );
        String actor = administrator == null
                ? "local-operator"
                : administrator.username();
        recordAuthenticationAudit(
                AuditAction.OPERATOR_SESSIONS_BULK_REVOKED,
                "bulk-" + UUID.randomUUID(),
                "운영자 다른 세션 일괄 종료",
                Map.of(
                        "revokedCount", revoked.size(),
                        "currentSessionPreserved", currentSessionPreserved
                ),
                actor
        );
        return ResponseEntity.ok(
                new OperatorBulkSessionRevocationResponse(
                        revoked.size(),
                        currentSessionPreserved
                )
        );
    }

    @DeleteMapping("/sessions/current")
    public ResponseEntity<Void> revokeCurrentSession(
            Authentication authentication,
            HttpServletRequest request
    ) {
        OperatorPrincipal principal = authentication != null
                && authentication.getPrincipal() instanceof OperatorPrincipal value
                ? value
                : null;
        if (credentialRegistry.isEnabled() && principal == null) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }

        Optional<OperatorSessionSummary> revoked = sessionRegistry.revoke(
                request.getHeader(
                        OperatorAuthenticationFilter.OPERATOR_SESSION_HEADER
                )
        );
        if (principal != null) {
            recordAuthenticationAudit(
                    AuditAction.OPERATOR_LOGOUT,
                    revoked
                            .map(value -> value.sessionId().toString())
                            .orElse(principal.username()),
                    "운영자 로그아웃",
                    Map.of("role", principal.role().name()),
                    principal.username()
            );
        }
        return ResponseEntity.noContent().build();
    }

    private ResponseEntity<ErrorResponse> loginRateLimited(
            OperatorLoginAttemptGuard.AttemptDecision decision
    ) {
        return ResponseEntity
                .status(HttpStatus.TOO_MANY_REQUESTS)
                .header(
                        HttpHeaders.RETRY_AFTER,
                        String.valueOf(decision.retryAfterSeconds())
                )
                .body(
                        ErrorResponse.of(
                                "OPERATOR_LOGIN_RATE_LIMITED",
                                "로그인 시도가 일시적으로 잠겼습니다. 잠시 후 다시 시도하세요."
                        )
                );
    }

    private void recordAuthenticationAudit(
            AuditAction action,
            String entityId,
            String summary,
            Map<String, ?> details,
            String actor
    ) {
        try {
            auditLogService.recordAuthenticationEvent(
                    action,
                    entityId,
                    summary,
                    details,
                    actor
            );
        } catch (RuntimeException error) {
            log.warn("운영자 인증 감사 로그 저장 실패: {}", action, error);
        }
    }
}
