package com.visionflow.api.common.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;
import java.util.Optional;

public class OperatorAuthenticationFilter extends OncePerRequestFilter {

    public static final String OPERATOR_KEY_HEADER = "X-VisionFlow-Operator-Key";
    public static final String OPERATOR_SESSION_HEADER =
            "X-VisionFlow-Operator-Session";

    private final OperatorCredentialRegistry credentialRegistry;
    private final OperatorSessionRegistry sessionRegistry;
    private final OperatorSecurityErrorWriter errorWriter;

    public OperatorAuthenticationFilter(
            OperatorCredentialRegistry credentialRegistry,
            OperatorSessionRegistry sessionRegistry,
            OperatorSecurityErrorWriter errorWriter
    ) {
        this.credentialRegistry = credentialRegistry;
        this.sessionRegistry = sessionRegistry;
        this.errorWriter = errorWriter;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        if (!credentialRegistry.isEnabled()) {
            filterChain.doFilter(request, response);
            return;
        }

        if (isSessionCreationRequest(request)) {
            filterChain.doFilter(request, response);
            return;
        }

        String presentedSession = request.getHeader(OPERATOR_SESSION_HEADER);
        String presentedKey = request.getHeader(OPERATOR_KEY_HEADER);
        if (
                (presentedSession == null || presentedSession.isBlank())
                        && (presentedKey == null || presentedKey.isBlank())
        ) {
            filterChain.doFilter(request, response);
            return;
        }

        Optional<OperatorPrincipal> resolved;
        String invalidCode;
        String invalidMessage;
        if (presentedSession != null && !presentedSession.isBlank()) {
            resolved = sessionRegistry.resolve(presentedSession);
            invalidCode = "INVALID_OPERATOR_SESSION";
            invalidMessage = "운영자 로그인 세션이 만료되었거나 올바르지 않습니다.";
        } else {
            resolved = credentialRegistry.resolve(presentedKey);
            invalidCode = "INVALID_OPERATOR_KEY";
            invalidMessage = "운영자 인증 키가 올바르지 않습니다.";
        }
        if (resolved.isEmpty()) {
            errorWriter.write(
                    response,
                    HttpStatus.UNAUTHORIZED.value(),
                    invalidCode,
                    invalidMessage
            );
            return;
        }

        OperatorPrincipal principal = resolved.get();
        UsernamePasswordAuthenticationToken authentication =
                new UsernamePasswordAuthenticationToken(
                        principal,
                        null,
                        List.of(new SimpleGrantedAuthority(principal.role().authority()))
                );
        SecurityContextHolder.getContext().setAuthentication(authentication);
        if (
                principal.passwordChangeRequired()
                        && !isPasswordChangeAllowedRequest(request)
        ) {
            errorWriter.write(
                    response,
                    HttpStatus.FORBIDDEN.value(),
                    "OPERATOR_PASSWORD_CHANGE_REQUIRED",
                    "초기 비밀번호를 변경한 후 VisionFlow 기능을 사용할 수 있습니다."
            );
            return;
        }
        filterChain.doFilter(request, response);
    }

    private boolean isPasswordChangeAllowedRequest(HttpServletRequest request) {
        String path = request.getServletPath();
        return (HttpMethod.POST.matches(request.getMethod())
                        && "/api/security/password".equals(path))
                || (HttpMethod.GET.matches(request.getMethod())
                        && "/api/security/me".equals(path))
                || (HttpMethod.DELETE.matches(request.getMethod())
                        && "/api/security/sessions/current".equals(path));
    }

    private boolean isSessionCreationRequest(HttpServletRequest request) {
        return HttpMethod.POST.matches(request.getMethod())
                && "/api/security/sessions".equals(request.getServletPath());
    }
}
