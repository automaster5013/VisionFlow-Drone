package com.visionflow.api.common.security;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Optional;

@Service
public class OperatorUserAuthenticationService {

    private static final Logger log = LoggerFactory.getLogger(
            OperatorUserAuthenticationService.class
    );
    private static final int MAXIMUM_USERNAME_LENGTH = 100;
    private static final int MAXIMUM_PASSWORD_LENGTH = 4096;
    private static final int MINIMUM_NEW_PASSWORD_LENGTH = 15;
    private static final int MAXIMUM_NEW_PASSWORD_LENGTH = 128;

    private final OperatorUserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final String dummyPasswordHash;

    public OperatorUserAuthenticationService(
            OperatorUserRepository userRepository,
            PasswordEncoder passwordEncoder
    ) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.dummyPasswordHash = passwordEncoder.encode(
                "visionflow-invalid-user-dummy-password"
        );
    }

    @Transactional
    public Optional<OperatorPrincipal> authenticate(
            String rawUsername,
            String rawPassword
    ) {
        String username = rawUsername == null ? "" : rawUsername.trim();
        String password = rawPassword == null ? "" : rawPassword;
        if (
                username.isEmpty()
                        || username.length() > MAXIMUM_USERNAME_LENGTH
                        || username.chars().anyMatch(Character::isISOControl)
                        || password.isEmpty()
                        || password.length() > MAXIMUM_PASSWORD_LENGTH
        ) {
            passwordEncoder.matches(password, dummyPasswordHash);
            return Optional.empty();
        }

        Optional<OperatorUser> candidate =
                userRepository.findByUsernameIgnoreCase(username);
        String passwordHash = candidate
                .map(OperatorUser::getPasswordHash)
                .orElse(dummyPasswordHash);

        boolean matches;
        try {
            matches = passwordEncoder.matches(password, passwordHash);
        } catch (IllegalArgumentException error) {
            log.warn(
                    "운영자 비밀번호 해시 검증 실패: username={}",
                    username,
                    error
            );
            return Optional.empty();
        }

        if (candidate.isEmpty() || !matches || !candidate.get().isEnabled()) {
            return Optional.empty();
        }

        OperatorUser user = candidate.get();
        user.markLogin(LocalDateTime.now(ZoneOffset.UTC));
        return Optional.of(toPrincipal(user));
    }

    @Transactional
    public Optional<OperatorPrincipal> changeInitialPassword(
            String rawUsername,
            String newPassword
    ) {
        String username = rawUsername == null ? "" : rawUsername.trim();
        validateNewPassword(newPassword);

        Optional<OperatorUser> candidate =
                userRepository.findByUsernameIgnoreCase(username);
        if (
                candidate.isEmpty()
                        || !candidate.get().isEnabled()
                        || !candidate.get().isPasswordChangeRequired()
        ) {
            return Optional.empty();
        }

        OperatorUser user = candidate.get();
        if (passwordEncoder.matches(newPassword, user.getPasswordHash())) {
            throw new IllegalArgumentException(
                    "현재 임시 비밀번호와 다른 새 비밀번호를 사용하세요."
            );
        }

        user.changePassword(passwordEncoder.encode(newPassword));
        userRepository.saveAndFlush(user);
        return Optional.of(toPrincipal(user));
    }

    private void validateNewPassword(String password) {
        int length = password == null ? 0 : password.length();
        if (
                length < MINIMUM_NEW_PASSWORD_LENGTH
                        || length > MAXIMUM_NEW_PASSWORD_LENGTH
        ) {
            throw new IllegalArgumentException(
                    "새 비밀번호는 15~128자로 입력하세요."
            );
        }
    }

    private OperatorPrincipal toPrincipal(OperatorUser user) {
        return new OperatorPrincipal(
                user.getUsername(),
                user.getRole(),
                user.isPasswordChangeRequired()
        );
    }
}
