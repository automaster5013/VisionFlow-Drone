package com.visionflow.api.common.config;

import com.visionflow.api.common.security.OperatorAuthenticationFilter;
import com.visionflow.api.common.security.OperatorCredentialRegistry;
import com.visionflow.api.common.security.OperatorSecurityErrorWriter;
import com.visionflow.api.common.security.OperatorSessionRegistry;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.authentication.AnonymousAuthenticationFilter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    public SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OperatorCredentialRegistry credentialRegistry,
            OperatorSessionRegistry sessionRegistry,
            OperatorSecurityErrorWriter errorWriter
    ) throws Exception {

        http
                .csrf(csrf -> csrf.disable())

                .sessionManagement(session ->
                        session.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS
                        )
                )

                .authorizeHttpRequests(authorize -> {
                    if (!credentialRegistry.isEnabled()) {
                        authorize
                                .requestMatchers(
                                        "/api/health",
                                        "/api/drones/**",
                                        "/api/geofences/**",
                                        "/api/dashboard/**",
                                        "/api/incidents/**",
                                        "/api/maintenance/**",
                                        "/api/flight-quality/**",
                                        "/api/audit-logs/**",
                                        "/api/security/**",
                                        "/api/demo/**",
                                        "/actuator/health",
                                        "/ws",
                                        "/ws/**",
                                        "/api/ai/**"
                                )
                                .permitAll()
                                .anyRequest()
                                .authenticated();
                        return;
                    }

                    authorize
                            .requestMatchers(
                                    "/api/health",
                                    "/api/security/me",
                                    "/actuator/health",
                                    "/ws",
                                    "/ws/**"
                            )
                            .permitAll()
                            .requestMatchers(
                                    HttpMethod.POST,
                                    "/api/security/sessions",
                                    "/api/security/pairings/*/claim",
                                    "/api/security/pairings/*/exchange"
                            )
                            .permitAll()
                            .requestMatchers(
                                    HttpMethod.POST,
                                    "/api/security/password"
                            )
                            .hasAnyRole("VIEWER", "OPERATOR", "ADMIN")
                            .requestMatchers(
                                    HttpMethod.POST,
                                    "/api/security/pairings",
                                    "/api/security/pairings/*/approve"
                            )
                            .hasAnyRole("VIEWER", "OPERATOR", "ADMIN")
                            .requestMatchers(
                                    HttpMethod.GET,
                                    "/api/security/pairings/*"
                            )
                            .hasAnyRole("VIEWER", "OPERATOR", "ADMIN")
                            .requestMatchers(
                                    HttpMethod.DELETE,
                                    "/api/security/pairings/*"
                            )
                            .hasAnyRole("VIEWER", "OPERATOR", "ADMIN")
                            .requestMatchers(
                                    HttpMethod.DELETE,
                                    "/api/security/sessions/current"
                            )
                            .permitAll()
                            .requestMatchers(
                                    HttpMethod.GET,
                                    "/api/security/sessions"
                            )
                            .hasRole("ADMIN")
                            .requestMatchers(
                                    HttpMethod.DELETE,
                                    "/api/security/sessions/*"
                            )
                            .hasRole("ADMIN")
                            .requestMatchers(
                                    HttpMethod.GET,
                                    "/api/audit-logs/export"
                            )
                            .hasAnyRole("VIEWER", "OPERATOR", "ADMIN")
                            .requestMatchers(
                                    HttpMethod.GET,
                                    "/api/audit-logs",
                                    "/api/audit-logs/retention"
                            )
                            .hasRole("ADMIN")
                            .requestMatchers(
                                    HttpMethod.GET,
                                    "/api/ai/alerts/**",
                                    "/api/ai/events/**",
                                    "/api/ai/phase3/events/**",
                                    "/api/incidents/**"
                            )
                            .hasAnyRole("VIEWER", "OPERATOR", "ADMIN")
                            .requestMatchers(
                                    HttpMethod.GET,
                                    "/api/dashboard/**",
                                    "/api/drones/**",
                                    "/api/flight-quality/**",
                                    "/api/geofences/**",
                                    "/api/maintenance/**"
                            )
                            .hasAnyRole("VIEWER", "OPERATOR", "ADMIN")
                            .requestMatchers(HttpMethod.GET, "/api/**")
                            .permitAll()
                            .requestMatchers(
                                    HttpMethod.PATCH,
                                    "/api/drones/*/telemetry"
                            )
                            .permitAll()
                            .requestMatchers(HttpMethod.POST, "/api/ai/events")
                            .permitAll()
                            .requestMatchers(
                                    HttpMethod.PUT,
                                    "/api/ai/events/*/snapshot"
                            )
                           .permitAll()
                           .requestMatchers(
                                    HttpMethod.POST,
                                    "/api/ai/phase3/events"
                           )
                          .permitAll()
                          .requestMatchers(
                                    HttpMethod.PUT,
                                    "/api/ai/phase3/events/*/depth"
                           )
                           .permitAll()
                           .requestMatchers(
                                    HttpMethod.DELETE,
                                    "/api/ai/events/*/snapshot"
                            )
                            .hasAnyRole("OPERATOR", "ADMIN")
                           .requestMatchers(
                                    HttpMethod.DELETE,
                                    "/api/drones/*"
                            )
                            .hasRole("ADMIN")
                            .requestMatchers(
                                    HttpMethod.POST,
                                    "/api/audit-logs/retention/cleanup"
                            )
                            .hasRole("ADMIN")
                            .requestMatchers(
                                    HttpMethod.PATCH,
                                    "/api/ai/alerts/**"
                            )
                            .hasAnyRole("OPERATOR", "ADMIN")
                            .requestMatchers(
                                    HttpMethod.POST,
                                    "/api/demo/**",
                                    "/api/drones/**",
                                    "/api/geofences/**",
                                    "/api/incidents/**",
                                    "/api/flight-quality/**"
                            )
                            .hasAnyRole("OPERATOR", "ADMIN")
                            .requestMatchers(
                                    HttpMethod.PUT,
                                    "/api/drones/**",
                                    "/api/geofences/**"
                            )
                            .hasAnyRole("OPERATOR", "ADMIN")
                            .requestMatchers(
                                    HttpMethod.PATCH,
                                    "/api/drones/**",
                                    "/api/geofences/**",
                                    "/api/incidents/**",
                                    "/api/maintenance/**"
                            )
                            .hasAnyRole("OPERATOR", "ADMIN")
                            .anyRequest()
                            .denyAll();
                })

                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint((request, response, exception) ->
                                errorWriter.write(
                                        response,
                                        HttpStatus.UNAUTHORIZED.value(),
                                        "OPERATOR_AUTHENTICATION_REQUIRED",
                                        "이 작업에는 운영자 인증 키가 필요합니다."
                                )
                        )
                        .accessDeniedHandler((request, response, exception) ->
                                errorWriter.write(
                                        response,
                                        HttpStatus.FORBIDDEN.value(),
                                        "OPERATOR_PERMISSION_DENIED",
                                        "현재 운영자 역할로는 이 작업을 실행할 수 없습니다."
                                )
                        )
                )

                .addFilterBefore(
                        new OperatorAuthenticationFilter(
                                credentialRegistry,
                                sessionRegistry,
                                errorWriter
                        ),
                        AnonymousAuthenticationFilter.class
                )

                .httpBasic(httpBasic ->
                        httpBasic.disable()
                )

                .formLogin(formLogin ->
                        formLogin.disable()
                );

        return http.build();
    }
}
