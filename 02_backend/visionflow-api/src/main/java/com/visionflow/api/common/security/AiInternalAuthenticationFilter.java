package com.visionflow.api.common.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;
import java.util.Set;

public class AiInternalAuthenticationFilter extends OncePerRequestFilter {

    public static final String AI_INTERNAL_KEY_HEADER = "X-VisionFlow-AI-Key";
    public static final String AI_INTERNAL_AUTHORITY = "ROLE_AI_INTERNAL";

    private static final Set<String> OPERATOR_AUTHORITIES = Set.of(
            "ROLE_VIEWER",
            "ROLE_OPERATOR",
            "ROLE_ADMIN"
    );

    private final AiInternalCredentialRegistry credentialRegistry;
    private final OperatorSecurityErrorWriter errorWriter;

    public AiInternalAuthenticationFilter(
            AiInternalCredentialRegistry credentialRegistry,
            OperatorSecurityErrorWriter errorWriter
    ) {
        this.credentialRegistry = credentialRegistry;
        this.errorWriter = errorWriter;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        if (!isProtectedAiIngestRequest(request)) {
            filterChain.doFilter(request, response);
            return;
        }

        if (isSnapshotUpload(request) && hasOperatorAuthentication()) {
            filterChain.doFilter(request, response);
            return;
        }

        if (!credentialRegistry.isEnabled()) {
            establishAiInternalAuthentication();
            filterChain.doFilter(request, response);
            return;
        }

        String presentedKey = request.getHeader(AI_INTERNAL_KEY_HEADER);
        if (!credentialRegistry.matches(presentedKey)) {
            errorWriter.write(
                    response,
                    HttpStatus.UNAUTHORIZED.value(),
                    "AI_INTERNAL_AUTHENTICATION_REQUIRED",
                    "AI 내부 서비스 인증이 필요합니다."
            );
            return;
        }

        establishAiInternalAuthentication();
        filterChain.doFilter(request, response);
    }

    private void establishAiInternalAuthentication() {
        UsernamePasswordAuthenticationToken authentication =
                new UsernamePasswordAuthenticationToken(
                        "visionflow-ai",
                        null,
                        List.of(new SimpleGrantedAuthority(AI_INTERNAL_AUTHORITY))
                );
        SecurityContextHolder.getContext().setAuthentication(authentication);
    }

    private boolean hasOperatorAuthentication() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        return authentication.getAuthorities()
                .stream()
                .map(authority -> authority.getAuthority())
                .anyMatch(OPERATOR_AUTHORITIES::contains);
    }

    private boolean isProtectedAiIngestRequest(HttpServletRequest request) {
        String method = request.getMethod();
        String path = request.getServletPath();

        return (HttpMethod.POST.matches(method)
                        && "/api/ai/events".equals(path))
                || isSnapshotUpload(request)
                || (HttpMethod.POST.matches(method)
                        && "/api/ai/phase3/events".equals(path))
                || (HttpMethod.PUT.matches(method)
                        && path.matches("^/api/ai/phase3/events/[^/]+/depth$"));
    }

    private boolean isSnapshotUpload(HttpServletRequest request) {
        return HttpMethod.PUT.matches(request.getMethod())
                && request.getServletPath().matches("^/api/ai/events/[^/]+/snapshot$");
    }
}
