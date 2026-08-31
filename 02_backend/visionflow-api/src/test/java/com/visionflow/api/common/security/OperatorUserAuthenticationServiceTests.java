package com.visionflow.api.common.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class OperatorUserAuthenticationServiceTests {

    private OperatorUserRepository userRepository;
    private PasswordEncoder passwordEncoder;
    private OperatorUserAuthenticationService service;

    @BeforeEach
    void setUp() {
        userRepository = mock(OperatorUserRepository.class);
        passwordEncoder = new BCryptPasswordEncoder(4);
        service = new OperatorUserAuthenticationService(
                userRepository,
                passwordEncoder
        );
    }

    @Test
    void authenticatesEnabledUserAndReturnsDatabaseRole() {
        OperatorUser user = OperatorUser.create(
                "operator01",
                passwordEncoder.encode("correct-horse-battery-staple"),
                OperatorRole.OPERATOR
        );
        when(userRepository.findByUsernameIgnoreCase("operator01"))
                .thenReturn(Optional.of(user));

        Optional<OperatorPrincipal> result = service.authenticate(
                " operator01 ",
                "correct-horse-battery-staple"
        );

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().username()).isEqualTo("operator01");
        assertThat(result.orElseThrow().role()).isEqualTo(OperatorRole.OPERATOR);
        assertThat(result.orElseThrow().passwordChangeRequired()).isTrue();
        assertThat(user.getLastLoginAt()).isNotNull();
    }

    @Test
    void changesInitialPasswordAndClearsRotationRequirement() {
        OperatorUser user = OperatorUser.create(
                "operator01",
                passwordEncoder.encode("temporary-password-value"),
                OperatorRole.OPERATOR
        );
        when(userRepository.findByUsernameIgnoreCase("operator01"))
                .thenReturn(Optional.of(user));

        Optional<OperatorPrincipal> result = service.changeInitialPassword(
                "operator01",
                "replacement-password-2026"
        );

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().passwordChangeRequired()).isFalse();
        assertThat(user.isPasswordChangeRequired()).isFalse();
        assertThat(
                passwordEncoder.matches(
                        "replacement-password-2026",
                        user.getPasswordHash()
                )
        ).isTrue();
    }

    @Test
    void rejectsIncorrectPassword() {
        OperatorUser user = OperatorUser.create(
                "viewer01",
                passwordEncoder.encode("viewer-correct-password"),
                OperatorRole.VIEWER
        );
        when(userRepository.findByUsernameIgnoreCase("viewer01"))
                .thenReturn(Optional.of(user));

        Optional<OperatorPrincipal> result = service.authenticate(
                "viewer01",
                "wrong-password"
        );

        assertThat(result).isEmpty();
        assertThat(user.getLastLoginAt()).isNull();
    }

    @Test
    void rejectsUnknownUser() {
        when(userRepository.findByUsernameIgnoreCase("missing"))
                .thenReturn(Optional.empty());

        Optional<OperatorPrincipal> result = service.authenticate(
                "missing",
                "some-password"
        );

        assertThat(result).isEmpty();
    }
}
