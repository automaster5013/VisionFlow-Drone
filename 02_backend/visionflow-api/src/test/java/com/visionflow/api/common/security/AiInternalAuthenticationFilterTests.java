package com.visionflow.api.common.security;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import tools.jackson.databind.json.JsonMapper;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class AiInternalAuthenticationFilterTests {

    private static final String VALID_KEY =
            "stage2-test-ai-internal-key-0123456789abcdef";

    private final OperatorSecurityErrorWriter errorWriter =
            new OperatorSecurityErrorWriter(
                    JsonMapper.builder().build()
            );

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void protectedEventWriteRejectsMissingKeyWhenEnabled() throws Exception {
        AiInternalAuthenticationFilter filter = filter(true);
        MockHttpServletRequest request =
                new MockHttpServletRequest("POST", "/api/ai/events");
        request.setServletPath("/api/ai/events");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        assertThat(response.getStatus()).isEqualTo(401);
        assertThat(response.getContentAsString())
                .contains("AI_INTERNAL_AUTHENTICATION_REQUIRED");
    }

    @Test
    void protectedEventWriteAcceptsValidKey() throws Exception {
        AiInternalAuthenticationFilter filter = filter(true);
        MockHttpServletRequest request =
                new MockHttpServletRequest("POST", "/api/ai/events");
        request.setServletPath("/api/ai/events");
        request.addHeader(
                AiInternalAuthenticationFilter.AI_INTERNAL_KEY_HEADER,
                VALID_KEY
        );
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        assertThat(response.getStatus()).isEqualTo(200);
        assertThat(
                SecurityContextHolder.getContext()
                        .getAuthentication()
                        .getAuthorities()
        )
                .extracting(authority -> authority.getAuthority())
                .containsExactly(
                        AiInternalAuthenticationFilter.AI_INTERNAL_AUTHORITY
                );
    }

    @Test
    void disabledInternalSecurityStillMarksMachineWriteAsAiInternal()
            throws Exception {
        AiInternalAuthenticationFilter filter = filter(false);
        MockHttpServletRequest request =
                new MockHttpServletRequest("POST", "/api/ai/events");
        request.setServletPath("/api/ai/events");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        assertThat(
                SecurityContextHolder.getContext()
                        .getAuthentication()
                        .getAuthorities()
        )
                .extracting(authority -> authority.getAuthority())
                .containsExactly(
                        AiInternalAuthenticationFilter.AI_INTERNAL_AUTHORITY
                );
    }

    @Test
    void snapshotPutPreservesOperatorAuthenticationForManualPath()
            throws Exception {
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(
                        "operator",
                        null,
                        List.of(
                                new SimpleGrantedAuthority("ROLE_OPERATOR")
                        )
                )
        );

        AiInternalAuthenticationFilter filter = filter(true);
        MockHttpServletRequest request = new MockHttpServletRequest(
                "PUT",
                "/api/ai/events/123/snapshot"
        );
        request.setServletPath("/api/ai/events/123/snapshot");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        assertThat(response.getStatus()).isEqualTo(200);
        assertThat(
                SecurityContextHolder.getContext()
                        .getAuthentication()
                        .getAuthorities()
        )
                .extracting(authority -> authority.getAuthority())
                .containsExactly("ROLE_OPERATOR");
    }

    @Test
    void unrelatedReadDoesNotRequireInternalKey() throws Exception {
        AiInternalAuthenticationFilter filter = filter(true);
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", "/api/health");
        request.setServletPath("/api/health");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        assertThat(response.getStatus()).isEqualTo(200);
        assertThat(
                SecurityContextHolder.getContext().getAuthentication()
        ).isNull();
    }

    private AiInternalAuthenticationFilter filter(boolean enabled) {
        return new AiInternalAuthenticationFilter(
                new AiInternalCredentialRegistry(
                        enabled,
                        enabled ? VALID_KEY : ""
                ),
                errorWriter
        );
    }
}
